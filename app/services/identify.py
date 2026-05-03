import base64
import json
import os
import re
import anthropic
from flask import current_app


THUMBS_DIR = "/home/pokemon/app/static/thumbs"
_MODEL = "claude-haiku-4-5"

_OCR_SYSTEM = (
    "You are a Pokemon card OCR engine. Extract only text that is "
    "literally printed on the card. Do not guess or infer anything."
)

_OCR_PROMPT = (
    "Extract these specific fields from this Pokemon card image.\n"
    "Look carefully at the bottom area of the card for the card number.\n"
    "Respond in JSON only, no markdown, no explanation:\n"
    "{\n"
    '  "card_name": "exact name printed at top of card",\n'
    '  "card_number": "the X/YYY number printed at bottom (e.g. 015/078)",\n'
    '  "set_code": "2-4 letter set code if visible (e.g. SVI, PAL, GO)",\n'
    '  "total_in_set": "the YYY part of X/YYY",\n'
    '  "copyright_year": "year from copyright line at bottom",\n'
    '  "hp": "HP number if visible",\n'
    '  "confidence": "high/medium/low based on image clarity"\n'
    "}"
)

_REVERSE_HOLO_SYSTEM = "You are a Pokemon card grading expert examining card scans."

_REVERSE_HOLO_PROMPT = (
    "Look carefully at this Pokemon card scan. Determine if this is "
    "a REVERSE HOLO variant.\n\n"
    "In a reverse holo card:\n"
    "- The artwork/illustration area is FLAT/MATTE (no sparkle)\n"
    "- The BORDER, text areas, and card background OUTSIDE the art box "
    "have a holographic sparkle/rainbow shimmer pattern\n"
    "- This is the OPPOSITE of a regular holo card where only the art sparkles\n\n"
    "In a normal non-holo card:\n"
    "- Everything is flat/matte\n\n"
    "In a regular holo card:\n"
    "- Only the artwork area sparkles\n\n"
    "Respond JSON only:\n"
    "{\n"
    '  "is_reverse_holo": true/false,\n'
    '  "confidence": "high/medium/low",\n'
    '  "reasoning": "one sentence explanation"\n'
    "}"
)


def ocr_card(scan_number):
    """Run Claude OCR on the card image.

    Tries full-resolution Drive download first; falls back to thumbnail.
    Temp files are always cleaned up.
    Returns parsed dict or None.
    """
    from app.models import Card
    from app.services.drive import download_full_temp, delete_temp

    img_path = None
    used_temp = False

    card = Card.query.filter_by(scan_number=scan_number).first()
    if card and card.drive_file_id_front:
        try:
            img_path = download_full_temp(card.drive_file_id_front, scan_number)
            used_temp = True
        except Exception as e:
            current_app.logger.warning(
                "Full-res download failed for %s, falling back to thumbnail: %s", scan_number, e
            )

    if img_path is None:
        thumb_path = os.path.join(THUMBS_DIR, f"{scan_number}.jpg")
        if not os.path.exists(thumb_path):
            return None
        img_path = thumb_path

    try:
        with open(img_path, "rb") as fh:
            image_b64 = base64.standard_b64encode(fh.read()).decode()

        client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model=_MODEL,
            max_tokens=512,
            system=_OCR_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64},
                    },
                    {"type": "text", "text": _OCR_PROMPT},
                ],
            }],
        )

        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            current_app.logger.warning("OCR JSON parse failed for %s: %s", scan_number, raw[:120])
            return None

    finally:
        if used_temp:
            delete_temp(scan_number)


def detect_reverse_holo(scan_number):
    """Run Claude reverse holo detection on the card image.

    Downloads full-res or falls back to thumbnail.
    Returns dict with is_reverse_holo, confidence, reasoning — or None on failure.
    """
    from app.models import Card
    from app.services.drive import download_full_temp, delete_temp

    img_path = None
    used_temp = False

    card = Card.query.filter_by(scan_number=scan_number).first()
    if card and card.drive_file_id_front:
        try:
            img_path = download_full_temp(card.drive_file_id_front, scan_number)
            used_temp = True
        except Exception as e:
            current_app.logger.warning(
                "Full-res download failed for %s RH detection: %s", scan_number, e
            )

    if img_path is None:
        thumb_path = os.path.join(THUMBS_DIR, f"{scan_number}.jpg")
        if not os.path.exists(thumb_path):
            return None
        img_path = thumb_path

    try:
        with open(img_path, "rb") as fh:
            image_b64 = base64.standard_b64encode(fh.read()).decode()

        client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model=_MODEL,
            max_tokens=256,
            system=_REVERSE_HOLO_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64},
                    },
                    {"type": "text", "text": _REVERSE_HOLO_PROMPT},
                ],
            }],
        )

        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            parsed = json.loads(raw)
            return {
                "is_reverse_holo": bool(parsed.get("is_reverse_holo", False)),
                "confidence": str(parsed.get("confidence", "low")),
                "reasoning": str(parsed.get("reasoning", "")),
            }
        except json.JSONDecodeError:
            current_app.logger.warning(
                "Reverse holo JSON parse failed for %s: %s", scan_number, raw[:120]
            )
            return None

    finally:
        if used_temp:
            delete_temp(scan_number)


def card_num_stripped(num_str):
    """Strip leading zeros from a card number: '015/078' → '15', 'TG01' → 'TG01'."""
    if not num_str:
        return ""
    part = num_str.split("/")[0].strip() if "/" in num_str else num_str.strip()
    try:
        return str(int(part))
    except ValueError:
        return part


def score_result_with_reasons(result, ocr):
    """Score a TCG result against OCR data. Returns (score, [reason, ...])."""
    score = 0
    reasons = []

    ocr_num = card_num_stripped(ocr.get("card_number") or "")
    ocr_name = (ocr.get("card_name") or "").strip().lower()
    ocr_set_code = (ocr.get("set_code") or "").strip().upper()
    ocr_total = (ocr.get("total_in_set") or "").strip()
    ocr_hp = (ocr.get("hp") or "").strip()

    res_num = card_num_stripped(result.get("set_number") or "")
    res_name = (result.get("card_name") or "").strip().lower()
    res_ptcgo = (result.get("set_ptcgo_code") or "").strip().upper()
    res_total = str(result.get("set_total") or "").strip()
    res_hp = str(result.get("hp") or "").strip()

    if ocr_num and res_num and ocr_num == res_num:
        score += 3
        reasons.append("Exact card number")
    if ocr_set_code and res_ptcgo and ocr_set_code == res_ptcgo:
        score += 2
        reasons.append("Set code match")
    if ocr_name and res_name:
        if ocr_name == res_name or ocr_name in res_name or res_name in ocr_name:
            score += 1
            reasons.append("Name match")
    if ocr_total and res_total and ocr_total == res_total:
        score += 1
        reasons.append("Set total match")
    if ocr_hp and res_hp and ocr_hp == res_hp:
        score += 1
        reasons.append("HP match")

    return score, reasons


def score_result(result, ocr):
    """Score a parsed TCG result dict against OCR data. Returns int."""
    score = 0

    ocr_num = card_num_stripped(ocr.get("card_number") or "")
    ocr_name = (ocr.get("card_name") or "").strip().lower()
    ocr_set_code = (ocr.get("set_code") or "").strip().upper()
    ocr_total = (ocr.get("total_in_set") or "").strip()
    ocr_hp = (ocr.get("hp") or "").strip()

    res_num = card_num_stripped(result.get("set_number") or "")
    res_name = (result.get("card_name") or "").strip().lower()
    res_ptcgo = (result.get("set_ptcgo_code") or "").strip().upper()
    res_total = str(result.get("set_total") or "").strip()
    res_hp = str(result.get("hp") or "").strip()

    if ocr_num and res_num and ocr_num == res_num:
        score += 3

    if ocr_set_code and res_ptcgo and ocr_set_code == res_ptcgo:
        score += 2

    if ocr_name and res_name:
        if ocr_name == res_name or ocr_name in res_name or res_name in ocr_name:
            score += 1

    if ocr_total and res_total and ocr_total == res_total:
        score += 1

    if ocr_hp and res_hp and ocr_hp == res_hp:
        score += 1

    return score


def best_match(ocr):
    """Run TCG searches in priority order. Returns (result, score) or (None, 0)."""
    from app.services.tcg import search_cards_q

    card_name = (ocr.get("card_name") or "").strip()
    card_number_raw = (ocr.get("card_number") or "").strip()
    set_code = (ocr.get("set_code") or "").strip()
    num_stripped = card_num_stripped(card_number_raw)

    candidates = []

    # Priority 1: number + set code
    if num_stripped and set_code:
        try:
            candidates.extend(search_cards_q(f"number:{num_stripped} set.ptcgoCode:{set_code}"))
        except Exception as e:
            current_app.logger.warning("TCG P1 query failed: %s", e)

    # Priority 2: name + number
    if card_name and num_stripped and not candidates:
        try:
            candidates.extend(search_cards_q(f'name:"{card_name}" number:{num_stripped}'))
        except Exception as e:
            current_app.logger.warning("TCG P2 query failed: %s", e)

    # Priority 3: name only, optionally filtered to matching number
    if card_name and not candidates:
        try:
            results = search_cards_q(f'name:"{card_name}"')
            if num_stripped:
                filtered = [r for r in results if card_num_stripped(r.get("set_number") or "") == num_stripped]
                candidates.extend(filtered if filtered else results)
            else:
                candidates.extend(results)
        except Exception as e:
            current_app.logger.warning("TCG P3 query failed: %s", e)

    if not candidates:
        return None, 0

    best = None
    best_score = 0
    for result in candidates:
        s = score_result(result, ocr)
        if s > best_score:
            best_score = s
            best = result

    return best, best_score


def identify_card(scan_number):
    """
    OCR-extract card fields, search TCG API with scoring, persist if matched.
    Returns result dict with ocr, matched, score, and identification_status.
    """
    from app.models import Card
    from app import db
    from app.services.tcg import get_card, assign_card

    card = Card.query.filter_by(scan_number=scan_number).first()
    if not card:
        return {"scan_number": scan_number, "matched": False, "error": "Card not in DB"}

    ocr = ocr_card(scan_number)
    if not ocr:
        return {"scan_number": scan_number, "matched": False, "error": "No thumbnail or OCR failed"}

    card_name = (ocr.get("card_name") or "").strip()
    card_number = (ocr.get("card_number") or "").strip()
    set_code = (ocr.get("set_code") or "").strip()
    confidence = ocr.get("confidence", "low")

    if not card_name and not card_number:
        return {
            "scan_number": scan_number,
            "matched": False,
            "confidence": confidence,
            "ocr": ocr,
            "error": "OCR found no name or number",
        }

    match, score = best_match(ocr)

    rh_result = None
    try:
        rh_result = detect_reverse_holo(scan_number)
        if rh_result:
            card.is_reverse_holo = rh_result["is_reverse_holo"]
            card.reverse_holo_confirmed = False
    except Exception as e:
        current_app.logger.warning("RH detection failed for %s: %s", scan_number, e)

    if match and score >= 3:
        try:
            full = get_card(match["tcg_card_id"])
            assign_card(card, full)
            card.identification_status = "AI Identified"
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return {"scan_number": scan_number, "matched": False, "error": str(e), "ocr": ocr}

        return {
            "scan_number": scan_number,
            "card_name": card_name,
            "card_number": card_number,
            "set_code": set_code,
            "confidence": confidence,
            "matched": True,
            "tcg_card_id": match["tcg_card_id"],
            "score": score,
            "identification_status": "AI Identified",
            "ocr": ocr,
            "reverse_holo": rh_result,
        }

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    return {
        "scan_number": scan_number,
        "card_name": card_name,
        "card_number": card_number,
        "set_code": set_code,
        "confidence": confidence,
        "matched": False,
        "score": score,
        "ocr": ocr,
        "reverse_holo": rh_result,
    }
