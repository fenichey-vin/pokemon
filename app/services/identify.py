import base64
import json
import os
import re
import anthropic
from flask import current_app


THUMBS_DIR = "/home/pokemon/app/static/thumbs"
_MODEL = "claude-haiku-4-5"


def identify_card(scan_number):
    """
    Vision-identify a card from its stored thumbnail.
    Returns dict with matched, pokemon_name, confidence, tcg_card_id (if matched).
    """
    thumb_path = os.path.join(THUMBS_DIR, f"{scan_number}.jpg")
    if not os.path.exists(thumb_path):
        return {"scan_number": scan_number, "matched": False, "error": "No thumbnail"}

    with open(thumb_path, "rb") as fh:
        image_b64 = base64.standard_b64encode(fh.read()).decode()

    client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=_MODEL,
        max_tokens=512,
        system=(
            "You are a Pokemon card identification expert. "
            "Analyze the card image and respond with ONLY a JSON object "
            "(no markdown, no extra text) containing exactly these fields: "
            '{"pokemon_name": string, "set_name": string, "card_number": string, '
            '"confidence": "high" | "medium" | "low"}'
        ),
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": "Identify this Pokemon card."},
                ],
            }
        ],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        ai = json.loads(raw)
    except json.JSONDecodeError:
        return {"scan_number": scan_number, "matched": False, "error": f"Bad JSON: {raw[:120]}"}

    pokemon_name = ai.get("pokemon_name", "")
    set_name = ai.get("set_name", "")
    card_number = ai.get("card_number", "")
    confidence = ai.get("confidence", "low")

    from app.models import Card
    from app import db
    from app.services.tcg import search_cards, get_card, assign_card

    card = Card.query.filter_by(scan_number=scan_number).first()
    if not card:
        return {"scan_number": scan_number, "matched": False, "error": "Card not in DB"}

    results = search_cards(pokemon_name) if pokemon_name else []
    match = None

    if card_number and results:
        for r in results:
            if (r.get("set_number") or "").lower() == card_number.lower():
                match = r
                break

    if match is None and set_name and results:
        for r in results:
            if set_name.lower() in (r.get("set_name") or "").lower():
                match = r
                break

    if match is None and results:
        match = results[0]

    if match:
        try:
            full = get_card(match["tcg_card_id"])
            assign_card(card, full)
            db.session.commit()
            return {
                "scan_number": scan_number,
                "pokemon_name": pokemon_name,
                "confidence": confidence,
                "matched": True,
                "tcg_card_id": match["tcg_card_id"],
            }
        except Exception as e:
            return {"scan_number": scan_number, "matched": False, "error": str(e)}

    return {
        "scan_number": scan_number,
        "pokemon_name": pokemon_name,
        "confidence": confidence,
        "matched": False,
    }
