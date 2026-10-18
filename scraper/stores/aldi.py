"""ALDI SUISSE: weekly promotions (Aktionen) from aldi-suisse.ch.

Promotions are grouped by start date (/de/aktionen-und-angebote/<YYYY-MM-DD>) and each
date has themes (?theme=Haushalt). Product data is embedded in each page's Nuxt payload.
"""

import asyncio
from datetime import date, timedelta
from urllib.parse import quote_plus

from scraper.health import is_staple
from scraper.nuxt import read_payload

# ALDI SUISSE has the same promotions and prices in every store (Buchs SG included).
STORE = {"id": "aldi", "name": "ALDI SUISSE", "url": "https://www.aldi-suisse.ch/de/aktionen-und-angebote",
         "scope": "national (gleich in Buchs SG)"}
BASE = "https://www.aldi-suisse.ch"
IMG_WIDTH = 400
DELAY_S = 1.5  # be polite between page loads
# Promotions that started up to this many days ago are still "this week".
LOOKBACK_DAYS = 7
LOOKAHEAD_DAYS = 7
# Categories whose regular prices we track every week, even off promotion: Magerquark (Magerquark-Radar)
# and the products of the "Bester Preis" comparison (eggs, chicken breast, minced meat). ALDI doesn't list
# its fresh fruit & vegetables online, so those only show up when they are on promotion.
STAPLES = [
    "https://www.aldi-suisse.ch/de/produkte/milchprodukte-eier/joghurts-quark-desserts/k/158816141843305903",
    "https://www.aldi-suisse.ch/de/produkte/milchprodukte-eier/eier/k/158816141843305902",
    "https://www.aldi-suisse.ch/de/produkte/fleisch/gefluegel/k/158816141843304202",
    "https://www.aldi-suisse.ch/de/produkte/fleisch/rind-kalb/k/158816141843304207",
]


async def _load(page, url):
    await asyncio.sleep(DELAY_S)
    resp = await page.goto(url, wait_until="domcontentloaded")
    if not resp or resp.status != 200:
        raise RuntimeError(f"{url} -> HTTP {resp.status if resp else '??'}")
    return await read_payload(page)


async def _products(page, url):
    """All products of a listing, following ?page=N when there are more than one page."""
    payload = await _load(page, url)
    items = list(payload["products"] or [])
    pag = payload["pagination"] or {}
    total, limit = pag.get("totalCount", len(items)), pag.get("limit") or 60
    pages = -(-total // limit)
    sep = "&" if "?" in url else "?"
    for n in range(2, pages + 1):
        items += (await _load(page, f"{url}{sep}page={n}"))["products"] or []
    return items


def _image(p):
    for a in p.get("assets") or []:
        if a.get("url"):
            return a["url"].replace("{width}", str(IMG_WIDTH)).replace("{slug}", p.get("urlSlugText") or "p")
    return None


def _offer(p, promo, themes, regular=False):
    price = p.get("price") or {}
    return {
        "regular": regular,
        "id": f"aldi-{p['sku']}",
        "store": "aldi",
        "name": p.get("name"),
        "brand": p.get("brandName"),
        "size": p.get("sellingSize"),
        "price": (price.get("amountRelevant") or price.get("amount") or 0) / 100,
        "priceDisplay": price.get("amountRelevantDisplay"),
        "wasPriceDisplay": price.get("wasPriceDisplay"),
        "savingsDisplay": price.get("savingsDisplay"),
        "unitPriceDisplay": price.get("comparisonDisplay"),
        "validFrom": p.get("onSaleDate") or promo["onSaleDateFrom"],
        "validFromDisplay": promo["title"],
        "categories": sorted(themes),
        "image": _image(p),
        "url": f"{BASE}/de/produkt/{p.get('urlSlugText')}-{p['sku']}" if p.get("urlSlugText") else STORE["url"],
    }


async def fetch(browser, today=None):
    today = today or date.today()
    page = await browser.new_page(locale="de-CH")
    try:
        promos = (await _load(page, STORE["url"]))["promotions"] or []
        lo, hi = today - timedelta(days=LOOKBACK_DAYS), today + timedelta(days=LOOKAHEAD_DAYS)
        promos = [pr for pr in promos if lo <= date.fromisoformat(pr["onSaleDateFrom"]) <= hi]

        offers = {}
        for promo in promos:
            base = f"{STORE['url']}/{promo['key']}"
            for p in await _products(page, base):
                offers.setdefault(p["sku"], (p, promo, set()))
            for theme in promo.get("themes") or []:
                for p in await _products(page, f"{base}?theme={quote_plus(theme['key'])}"):
                    offers.setdefault(p["sku"], (p, promo, set()))[2].add(theme["title"])
        result = [_offer(p, promo, themes) for p, promo, themes in offers.values()]

        regular = {"onSaleDateFrom": today.isoformat(), "title": "Dauerpreis"}
        seen = set(offers)
        for url in STAPLES:
            for p in await _products(page, url):
                o = _offer(p, regular, set(), regular=True)
                if p["sku"] not in seen and is_staple(o):
                    seen.add(p["sku"])
                    result.append(o)
        return result
    finally:
        await page.close()
