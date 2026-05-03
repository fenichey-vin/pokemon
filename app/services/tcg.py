from datetime import datetime, timezone
import requests
from flask import current_app


BASE_URL = "https://api.pokemontcg.io/v2"


def _headers():
    key = current_app.config.get("POKEMON_TCG_API_KEY")
    if key:
        return {"X-Api-Key": key}
    return {}


def search_cards(query):
    """Search TCG API by card name. Returns list of card dicts."""
    resp = requests.get(
        f"{BASE_URL}/cards",
        params={"q": f'name:"{query}"', "pageSize": 20},
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    return [_parse_card(c) for c in resp.json().get("data", [])]


def search_cards_q(q, page_size=20):
    """Search TCG API with a raw query string. Returns list of card dicts."""
    resp = requests.get(
        f"{BASE_URL}/cards",
        params={"q": q, "pageSize": page_size},
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    return [_parse_card(c) for c in resp.json().get("data", [])]


def get_card(card_id, prefer_reverse=False):
    """Fetch a single card by TCG ID."""
    resp = requests.get(
        f"{BASE_URL}/cards/{card_id}",
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    return _parse_card(resp.json().get("data", {}), prefer_reverse=prefer_reverse)


def _parse_price(card, prefer_reverse=False):
    prices = card.get("tcgplayer", {}).get("prices", {})
    if prefer_reverse:
        tier_order = ("reverseHolofoil", "holofoil", "normal", "1stEditionHolofoil")
    else:
        tier_order = ("holofoil", "reverseHolofoil", "normal", "1stEditionHolofoil")
    for tier in tier_order:
        p = prices.get(tier, {})
        mid = p.get("mid") or p.get("market")
        if mid:
            return float(mid)

    cm = card.get("cardmarket", {}).get("prices", {})
    avg = cm.get("averageSellPrice") or cm.get("avg1")
    if avg:
        return float(avg)
    return None


def _parse_card(card, prefer_reverse=False):
    tcg_set = card.get("set", {})
    return {
        "tcg_card_id": card.get("id"),
        "card_name": card.get("name"),
        "set_name": tcg_set.get("name"),
        "set_number": card.get("number"),
        "set_ptcgo_code": tcg_set.get("ptcgoCode"),
        "set_total": str(tcg_set.get("total") or ""),
        "hp": str(card.get("hp") or ""),
        "release_date": tcg_set.get("releaseDate"),
        "tcg_image_url": card.get("images", {}).get("large"),
        "market_price": _parse_price(card, prefer_reverse=prefer_reverse),
    }


def assign_card(db_card, tcg_data):
    """Apply TCG data to a Card model instance."""
    db_card.tcg_card_id = tcg_data["tcg_card_id"]
    db_card.card_name = tcg_data["card_name"]
    db_card.set_name = tcg_data["set_name"]
    db_card.set_number = tcg_data["set_number"]
    db_card.release_date = tcg_data["release_date"]
    db_card.tcg_image_url = tcg_data["tcg_image_url"]
    db_card.market_price = tcg_data["market_price"]
    db_card.price_fetched_at = datetime.now(timezone.utc).replace(tzinfo=None) if tcg_data["market_price"] else None
    db_card.identified = True
    db_card.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)


def refresh_all_prices():
    """Refresh market prices for all identified cards."""
    from app.models import Card
    from app import db

    cards = Card.query.filter_by(identified=True).all()
    updated = 0
    for card in cards:
        if not card.tcg_card_id:
            continue
        try:
            data = get_card(card.tcg_card_id, prefer_reverse=getattr(card, "is_reverse_holo", False))
            if data["market_price"] is not None:
                card.market_price = data["market_price"]
                card.price_fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
                card.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                updated += 1
        except Exception:
            pass

    db.session.commit()
    return f"Price refresh complete: {updated} cards updated."
