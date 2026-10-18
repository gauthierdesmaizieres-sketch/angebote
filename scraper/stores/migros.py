"""Migros: weekly in-store promotions (Aktionen) of the Migros Ostschweiz cooperative, which runs Buchs SG.

The offers page (migros.ch/de/offers/home) loads its products from Migros' public JSON API. We open that
page in a real browser and call the same endpoints from inside it, with the guest token the page gets.
region "gmos" = Genossenschaft Migros Ostschweiz: national promotions plus the regional ones of Buchs SG.
Migros answers 403 to headless Chromium, so this store runs in a visible (headed) browser.
robots.txt disallows /offers/instore/ and /promotion/ pages, so we never open those.
"""

import asyncio
import html
import json
import re
from datetime import date

from scraper.health import is_staple

STORE = {"id": "migros", "name": "Migros", "url": "https://www.migros.ch/de/offers/home",
         "scope": "Migros Ostschweiz (Buchs SG)"}
HEADED = True
REGION = "gmos"
DELAY_S = 1.5  # be polite between requests
BATCH = 50  # product-cards accepts up to 50 products per request
IMG_STACK = "mo-custom/v-w-400-h-342"
# Categories whose regular prices we track every week, even off promotion (see aldi.STAPLES):
# Quark, Eier, Hackfleisch, Poulet, Äpfel, Bananen, Tomaten, Broccoli, Kartoffeln, Karotten.
STAPLES = [7494881, 7494870, 7494842, 7494845, 7495373, 7494900, 7494901, 7494905, 7494908, 7494909]
# Only these top categories count as food for the health tags (not baby food, pet food, sweets, drinks,
# spreads and canned food).
FOOD = {"Früchte & Gemüse", "Fleisch & Fisch", "Milchprodukte, Eier & frische Fertiggerichte", "Tiefkühlprodukte",
        "Brot, Backwaren & Frühstück"}
# Promotions on a whole range ("Alle L'Oréal Produkte") become one card instead of one per product.
MAX_GROUP = 20

_FETCH_JS = """async ([headers, method, path, body]) => {
  const r = await fetch(path, {method, headers, body: body ? JSON.stringify(body) : undefined});
  return [r.status, await r.text()];
}"""


class _Api:
    def __init__(self, page, headers):
        self.page, self.headers = page, headers

    async def __call__(self, method, path, body=None):
        await asyncio.sleep(DELAY_S)
        status, text = await self.page.evaluate(_FETCH_JS, [self.headers, method, path, body])
        if status != 200:
            raise RuntimeError(f"{path} -> HTTP {status}")
        return json.loads(text)


async def _open(page):
    """Load the offers page and reuse the API headers (guest token) the page itself sends."""
    headers = {}

    def on_request(req):
        if "/product-display/" in req.url and req.headers.get("leshopch") and not headers:
            headers.update({k: v for k, v in req.headers.items()
                            if k in ("leshopch", "migros-language", "peer-id", "accept", "content-type")})

    page.on("request", on_request)
    resp = await page.goto(STORE["url"], wait_until="domcontentloaded")
    if not resp or resp.status != 200:
        raise RuntimeError(f"{STORE['url']} -> HTTP {resp.status if resp else '??'}")
    for _ in range(40):
        if headers:
            return _Api(page, {"content-type": "application/json", **headers})
        await asyncio.sleep(0.5)
    raise RuntimeError("no API token from the offers page")


def _chf(value):
    return f"CHF {value:.2f}"


def _unit(price):
    u = price.get("unitPrice") or {}
    return f"CHF {u['value']:.2f}/{u['unit']}" if u.get("value") and u.get("unit") else None


def _offer(card, regular=False):
    offer = card.get("offer") or {}
    price = offer.get("price") or {}
    promo = offer.get("promotionPrice") or {}
    dates = offer.get("promotionDateRange") or {}
    shown = price if regular else promo
    badges = [b.get("description") for b in offer.get("badges") or [] if b.get("description")]
    badges = [f"-{b}" if b.endswith("%") else b for b in badges]
    start, end = dates.get("startDate"), dates.get("endDate")
    images = card.get("images") or []
    title = card.get("title") or card.get("name") or ""
    category = card["breadcrumb"][0]["name"] if card.get("breadcrumb") else None
    return {
        "regular": regular,
        "id": f"migros-{card.get('migrosId') or card['uid']}",
        "store": "migros",
        "name": (title.split(" · ", 1)[-1] if card.get("brand") else title).replace(" · ", ", ").strip(),
        "brand": card.get("brand"),
        "size": offer.get("quantity"),
        "price": shown.get("effectiveValue") or 0,
        "priceDisplay": _chf(shown.get("effectiveValue") or 0),
        "wasPriceDisplay": None if regular or not price.get("effectiveValue") else _chf(price["effectiveValue"]),
        "savingsDisplay": " ".join(badges) or None,
        "unitPriceDisplay": _unit(shown),
        "validFrom": date.today().isoformat() if regular else start,
        "validFromDisplay": "Dauerpreis" if regular else
        f"{date.fromisoformat(start):%d.%m.} – {date.fromisoformat(end):%d.%m.}" if start and end else "",
        "categories": [category] if category else [],
        "food": category in FOOD,
        "image": images[0]["url"].replace("{stack}", IMG_STACK) if images else None,
        "url": card.get("productUrls") or STORE["url"],
    }


def _price(text):
    m = re.match(r"\s*(\d+)\.(\d\d|–|-)", text or "")
    return float(f"{m[1]}.{m[2] if m[2].isdigit() else '00'}") if m else None


def _group_offer(d):
    """One card for a promotion on a whole range, from its text ("z.B. ..., <strong>3.15</strong> statt 3.95")."""
    hint = html.unescape(d.get("discountHint") or "")
    now = re.search(r"<strong>\s*([^<]+)</strong>", hint)
    was = re.search(r"statt\s*([\d.–-]+)", hint)
    price = _price(now[1]) if now else None
    badges = [b.get("description") for b in d.get("badges") or [] if b.get("description")]
    start, end = d.get("startDate"), d.get("endDate")
    category = d["categories"][0]["name"] if d.get("categories") else None
    return {
        "regular": False,
        "id": f"migros-g{d['id']}",
        "store": "migros",
        "name": d.get("description") or "",
        "brand": None,
        "size": None,
        "price": price or 0,
        "priceDisplay": f"ab CHF {price:.2f}" if price else " ".join(f"-{b}" if b.endswith("%") else b for b in badges),
        "wasPriceDisplay": _chf(_price(was[1])) if was and _price(was[1]) else None,
        "savingsDisplay": " ".join(f"-{b}" if b.endswith("%") else b for b in badges) or None,
        "unitPriceDisplay": None,
        "validFrom": start,
        "validFromDisplay": f"{date.fromisoformat(start):%d.%m.} – {date.fromisoformat(end):%d.%m.}" if start and end else "",
        "categories": [category] if category else [],
        "food": False,  # a whole range: not one product we can tag or compare
        "image": d["image"]["url"].replace("{stack}", IMG_STACK) if d.get("image") else None,
        "url": STORE["url"],
    }


async def _cards(api, uids, today):
    cards = []
    for i in range(0, len(uids), BATCH):
        cards += await api("POST", "/product-display/public/v4/product-cards", {
            "offerFilter": {"storeType": "OFFLINE", "region": REGION, "ongoingOfferDate": f"{today}T00:00:00"},
            "productFilter": {"uids": uids[i:i + BATCH]},
        })
    return cards


async def fetch(browser, today=None):
    today = today or date.today()
    page = await browser.new_page(locale="de-CH")
    try:
        api = await _open(page)

        # 1. This week's promotions: single products and promotion groups ("Alle Weiss- und Rotkabis").
        items, start = [], 0
        while True:
            res = await api("POST", "/product-display/public/web/v3/products/promotion/search", {
                "storeType": "OFFLINE", "period": "CURRENT", "filters": {}, "sortFields": ["categoryLevel"],
                "sortOrder": "asc", "from": start, "until": start + 100, "region": REGION, "warehouse": "8",
                "enabledSponsoredProducts": False})
            items += res.get("items") or []
            start += 100
            if start >= (res.get("numberOfItems") or 0):
                break
        uids = [i["id"] for i in items if i["type"] == "PRODUCT"]
        groups = list(dict.fromkeys(i["id"] for i in items if i["type"] == "GROUP_PROMOTION"))
        result = {}
        for i in range(0, len(groups), BATCH):
            details = await api("GET", f"/product-display/public/v2/promotions-details/"
                                       f"{','.join(groups[i:i + BATCH])}?region={REGION}")
            for d in details:
                if len(d.get("productIds") or []) > MAX_GROUP:
                    result.setdefault(f"migros-g{d['id']}", _group_offer(d))
                else:
                    uids += d.get("productIds") or []
        uids = list(dict.fromkeys(uids))

        for card in await _cards(api, uids, today):
            if (card.get("offer") or {}).get("promotionPrice"):  # group members that aren't discounted are skipped
                o = _offer(card)
                result.setdefault(o["id"], o)

        # 2. Regular prices of the staples (Magerquark-Radar and the "Bester Preis" comparison).
        for category in STAPLES:
            staple_uids, start = [], 0
            while True:
                res = await api("POST", f"/product-display/public/web/v1/products/category/{category}/search", {
                    "regionId": REGION, "language": "de", "sortFields": [], "sortOrder": "asc", "from": start,
                    "limit": 100, "filters": {}, "searchAlgorithm": "DEFAULT", "enabledSponsoredProducts": False})
                staple_uids += res.get("productIds") or []
                start = res.get("offset") or start + 100
                if start >= (res.get("numberOfProducts") or 0) or not res.get("productIds"):
                    break
            for card in await _cards(api, staple_uids, today):
                offer = card.get("offer") or {}
                if not offer.get("price"):
                    continue
                # Staples on promotion inside a large range promotion still show their promotion price.
                o = _offer(card, regular=not offer.get("promotionPrice"))
                if o["id"] not in result and is_staple(o):
                    result[o["id"]] = o
        return list(result.values())
    finally:
        await page.close()
