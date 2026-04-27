import io
import os
import re
from datetime import datetime
from flask import current_app
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SCAN_RE = re.compile(r"^Pokemon_(\d{4})(_b)?\.(jpg|png)$", re.IGNORECASE)
THUMBS_DIR = "/home/pokemon/app/static/thumbs"


def _get_service():
    sa_file = current_app.config["SERVICE_ACCOUNT_JSON"]
    creds = service_account.Credentials.from_service_account_file(sa_file, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def download_thumbnail(drive_file_id, scan_number):
    """Download a Drive file, resize to max 300px wide, save as JPEG."""
    service = _get_service()

    media_request = service.files().get_media(fileId=drive_file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, media_request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    buf.seek(0)
    img = Image.open(buf).convert("RGB")
    img = img.rotate(180)

    max_width = 300
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

    os.makedirs(THUMBS_DIR, exist_ok=True)
    dest = os.path.join(THUMBS_DIR, f"{scan_number}.jpg")
    img.save(dest, "JPEG", quality=60, optimize=True)
    return dest


def sync_drive():
    from app.models import Card
    from app import db

    folder_id = current_app.config["GOOGLE_DRIVE_FOLDER_ID"]
    service = _get_service()

    files = []
    page_token = None
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "nextPageToken, files(id, name, createdTime)",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token
        resp = service.files().list(**params).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    scans = {}
    for f in files:
        m = SCAN_RE.match(f["name"])
        if not m:
            continue
        num = m.group(1)
        is_back = m.group(2) is not None
        scans.setdefault(num, {})
        if is_back:
            scans[num]["back"] = f
        else:
            scans[num]["front"] = f

    created = 0
    skipped = 0
    thumb_errors = 0
    for num, entry in scans.items():
        if "front" not in entry:
            continue
        existing = Card.query.filter_by(scan_number=num).first()
        if existing:
            skipped += 1
            continue

        front = entry["front"]
        back = entry.get("back")

        created_time = front.get("createdTime")
        date_scanned = None
        if created_time:
            try:
                date_scanned = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
            except ValueError:
                pass

        try:
            download_thumbnail(front["id"], num)
        except Exception as e:
            current_app.logger.error("thumbnail download failed for scan %s: %s", num, e)
            thumb_errors += 1

        card = Card(
            scan_number=num,
            drive_file_id_front=front["id"],
            drive_file_id_back=back["id"] if back else None,
            thumbnail_url=f"/static/thumbs/{num}.jpg",
            date_scanned=date_scanned,
            identified=False,
        )
        db.session.add(card)
        created += 1

    db.session.commit()
    msg = f"Sync complete: {created} new cards added, {skipped} already in catalog."
    if thumb_errors:
        msg += f" {thumb_errors} thumbnail(s) failed (check logs)."
    return msg
