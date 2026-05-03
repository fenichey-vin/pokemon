import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
    )
}


def fetch_price(card):
    """
    Try PriceCharting scrape first, then fall back to TCG API.
    Persists the updated price to the card row and returns the price (or None).
    """
    price = None

    if card.card_name:
        price = _pricecharting(card.card_name, card.set_name)

    if price is None and card.tcg_card_id:
        from app.services.tcg import get_card
        try:
            data = get_card(
                card.tcg_card_id,
                prefer_reverse=getattr(card, "is_reverse_holo", False),
            )
            price = data.get("market_price")
        except Exception:
            pass

    if price is not None:
        from app import db
        card.market_price = price
        card.price_fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
        card.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()

    return price


def _pricecharting(card_name, set_name=None):
    q = f"{card_name} {set_name}" if set_name else card_name
    try:
        resp = requests.get(
            "https://www.pricecharting.com/search-products",
            params={"q": q, "type": "pokemon"},
            headers=_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        link = soup.select_one(
            "#games_table tbody tr td.title a, "
            "table.data-table tbody tr td.title a"
        )
        if not link:
            return None

        href = link.get("href", "")
        if not href.startswith("/"):
            return None

        prod = requests.get(
            f"https://www.pricecharting.com{href}",
            headers=_HEADERS,
            timeout=10,
        )
        prod.raise_for_status()
        psoup = BeautifulSoup(prod.text, "lxml")

        for sel in ("#used_price .price", "#complete-price .price", "span.price"):
            el = psoup.select_one(sel)
            if el:
                text = el.get_text(strip=True).lstrip("$").replace(",", "")
                try:
                    return float(text)
                except ValueError:
                    continue
    except Exception:
        pass

    return None
