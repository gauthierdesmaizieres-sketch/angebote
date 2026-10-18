"""Lidl Schweiz: weekly promotions (Aktionen) from lidl.ch.

The home page links to the promotion lists (/c/de-CH/<name>/a<id>, e.g. "Wochenaktion"). Each product
tile carries its data as JSON in a data-grid-data attribute. Food categories (/h/...) list the same
promotions, including the next ones, so we read both and merge by product id.

Lidl has one national price list. A few promotions are marked "nur im Tessin" / "nur in der Westschweiz"
and don't apply in Buchs SG, so we drop them. lidl.ch only lists promotions: there is no regular price
for Magerquark or the comparison products, so Lidl only shows up in those when they are on promotion.
"""

import asyncio
import html
import json
import re
from datetime import date, datetime, timedelta, timezone

STORE = {"id": "lidl", "name": "Lidl", "url": "https://www.lidl.ch/",
         "scope": "national (ohne Tessin-/Westschweiz-Aktionen)"}
BASE = "https://www.lidl.ch"
DELAY_S = 1.5  # be polite between page loads
LOOKBACK_DAYS = 7
LOOKAHEAD_DAYS = 7
# Food categories, besides the promotion lists linked from the home page.
CATEGORIES = [
    "/h/de-CH/fruechte-gemuese/h10071012",
    "/h/de-CH/fleisch-gefluegel/h10095752",
    "/h/de-CH/fisch-meeresfruechte/h10071050",
    "/h/de-CH/kaese-milchprodukte-eier/h10095761",
]
SKIP_LISTS = re.compile(r"lidl-plus|coupons|prepaid|gutschein|reisen", re.I)
NOT_HERE = re.compile(r"nur im tessin|nur in der westschweiz|nur in der romandie", re.I)

_TILE = re.compile(r'data-grid-data="([^"]*)"')
_LIST = re.compile(r'href="(?:https://www\.lidl\.ch)?(/c/de-CH/[^"/]+/a\d+)"')
_LI = re.compile(r"<li[^>]*>(.*?)</li>", re.S)
_PER = re.compile(r"^pro\s+(.+)$", re.I)
_UNIT = re.compile(r"^([\d.]*\s*(?:kg|g|l|ml|cl))\s*=\s*([\d.]+)$", re.I)


async def _html(page, path):
    await asyncio.sleep(DELAY_S)
    resp = await page.goto(BASE + path, wait_until="domcontentloaded")
    if not resp or resp.status != 200:
        raise RuntimeError(f"{path} -> HTTP {resp.status if resp else '??'}")
    return await page.content()


def _day(ts):
    # Lidl dates are midnight Swiss time; +3 h lands on the right calendar day in winter and summer.
    return (datetime.fromtimestamp(ts, timezone.utc) + timedelta(hours=3)).date() if ts else None


def _facts(tile):
    """Pack size and unit price from the key facts list ("Pro 500 g", "100 g = 0.56")."""
    size = unit = None
    for li in _LI.findall((tile.get("keyfacts") or {}).get("description") or ""):
        text = html.unescape(re.sub(r"<[^>]+>", "", li)).strip()
        if m := _PER.match(text):
            size = re.sub(r"^kg$", "1 kg", m[1].strip())
        elif m := _UNIT.match(text):
            unit = f"CHF {m[2]}/{m[1].replace(' ', '')}"
    return size, unit


def _category(tile):
    """The promotion list ("Wochenaktion"), or for category pages the category ("Früchte & Gemüse")."""
    name = html.unescape(tile.get("listName") or "")
    if re.fullmatch(r"[a-z-]+", name):  # category pages report their URL slug
        parts = ((tile.get("keyfacts") or {}).get("wonCategoryPrimary") or "").split("/")
        name = parts[2] if len(parts) > 2 else ""
    return name


def _offer(tile):
    price = tile.get("price") or {}
    plus = None
    if not price.get("price") and tile.get("lidlPlus"):  # price only with the Lidl Plus app
        plus = tile["lidlPlus"][0]
        price = plus.get("price") or {}
    if not price.get("price"):
        return None
    discount = price.get("discount") or {}
    size, unit = _facts(tile)
    start = _day(tile.get("storeStartDate"))
    badge = next((b["text"] for b in ((tile.get("stockAvailability") or {}).get("badgeInfo") or {}).get("badges", [])
                  if b.get("text")), None)
    savings = discount.get("discountText") if discount.get("showDiscount") else None
    if plus:
        savings = f"{plus.get('lidlPlusText') or 'Mit Lidl Plus'} {savings or ''}".strip()
    return {
        "regular": False,
        "id": f"lidl-{tile['productId']}-{tile.get('storeStartDate') or ''}",  # same product, other week
        "store": "lidl",
        "name": html.unescape(tile.get("fullTitle") or tile.get("title") or ""),
        "brand": None,
        "size": size,
        "price": price["price"],
        "priceDisplay": f"CHF {price['price']:.2f}",
        "wasPriceDisplay": f"CHF {price['oldPrice']:.2f}" if price.get("oldPrice") else None,
        "savingsDisplay": savings,
        "unitPriceDisplay": unit,
        "validFrom": start.isoformat() if start else date.today().isoformat(),
        "validFromDisplay": (badge or (f"ab {start:%d.%m.}" if start else "")).replace(" - ", " – "),
        "categories": [_category(tile)] if _category(tile) else [],
        "food": (tile.get("keyfacts") or {}).get("analyticsCategory") == "Food",
        "image": tile.get("image"),
        "url": BASE + tile["canonicalUrl"] if tile.get("canonicalUrl") else STORE["url"],
        "_end": _day(tile.get("storeEndDate")),
    }


async def fetch(browser, today=None):
    today = today or date.today()
    lo, hi = today - timedelta(days=LOOKBACK_DAYS), today + timedelta(days=LOOKAHEAD_DAYS)
    page = await browser.new_page(locale="de-CH")
    try:
        home = await _html(page, "/")
        lists = [p for p in dict.fromkeys(_LIST.findall(home)) if not SKIP_LISTS.search(p)]
        result = {}
        for path in lists + CATEGORIES:
            for raw in _TILE.findall(await _html(page, path)):
                try:
                    tile = json.loads(html.unescape(raw))
                except ValueError:
                    continue
                if isinstance(tile, list):
                    tile = tile[0] if tile else {}
                if not tile.get("productId") or NOT_HERE.search(json.dumps(tile, ensure_ascii=False)):
                    continue
                o = _offer(tile)
                if not o or not lo <= date.fromisoformat(o["validFrom"]) <= hi:
                    continue
                end = o.pop("_end")
                if end and end < today:
                    continue
                result.setdefault(o["id"], o)
        return list(result.values())
    finally:
        await page.close()
