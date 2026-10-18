"""ALDI SUISSE: weekly promotions (Aktionen) from aldi-suisse.ch.

Promotions are grouped by start date (/de/aktionen-und-angebote/<YYYY-MM-DD>) and each
date has themes (?theme=Haushalt). Product data is embedded in each page's Nuxt payload.
"""

import asyncio
import re
from datetime import date, timedelta
from urllib.parse import quote_plus

from scraper.nuxt import read_payload

STORE = {"id": "aldi", "name": "ALDI SUISSE", "url": "https://www.aldi-suisse.ch/de/aktionen-und-angebote"}
BASE = "https://www.aldi-suisse.ch"
IMG_WIDTH = 400
DELAY_S = 1.5  # be polite between page loads
# Promotions that started up to this many days ago are still "this week".
LOOKBACK_DAYS = 7
LOOKAHEAD_DAYS = 7
# Staples tracked every week even when not on promotion (Magerquark-Radar).
STAPLES = [
    ("https://www.aldi-suisse.ch/de/produkte/milchprodukte-eier/joghurts-quark-desserts/k/158816141843305903",
     re.compile(r"magerquark", re.I)),
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
        for url, wanted in STAPLES:
            for p in await _products(page, url):
                if p["sku"] not in offers and wanted.search(p.get("name") or ""):
                    result.append(_offer(p, regular, set(), regular=True))
        return result
    finally:
        await page.close()
