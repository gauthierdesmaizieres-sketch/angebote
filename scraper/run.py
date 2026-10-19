"""Fetch every store's offers and write docs/data/offers.json for the web page.

Usage: python -m scraper.run
Each module in scraper/stores/ exposes STORE and fetch(browser). A module with HEADED = True gets a
visible browser window (Migros refuses headless Chromium); on a server without a display use xvfb-run.

Prices noted by hand in the shop (scraper/manual_prices.json) are added as regular prices: ALDI and
Lidl don't publish their whole permanent range online (e.g. ALDI's cheapest Magerquark).

Coop is missing on purpose: coop.ch answers HTTP 403 to Playwright, headless and headed, even for
robots.txt, so there is no honest way to read its promotions.
"""

import asyncio
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

from scraper.health import annotate
from scraper.stores import aldi, lidl, migros

STORES = [aldi, migros, lidl]
OUT = Path(__file__).resolve().parent.parent / "docs" / "data" / "offers.json"
MANUAL = Path(__file__).resolve().parent / "manual_prices.json"


def manual_offers():
    """Regular prices noted in the shop, in the same format as the stores' offers."""
    stores = {s.STORE["id"]: s.STORE for s in STORES}
    result = []
    for i, m in enumerate(json.loads(MANUAL.read_text(encoding="utf-8")).get("preise", [])):
        if m.get("store") not in stores or not m.get("price"):
            continue
        seen = date.fromisoformat(m["seen"]) if m.get("seen") else None
        result.append({
            "regular": True,
            "manual": True,
            "id": f"manual-{m['store']}-{i}",
            "store": m["store"],
            "name": m["name"],
            "brand": m.get("brand"),
            "size": m.get("size"),
            "price": m["price"],
            "priceDisplay": f"CHF {m['price']:.2f}",
            "wasPriceDisplay": None,
            "savingsDisplay": None,
            "unitPriceDisplay": None,
            "validFrom": date.today().isoformat(),
            "validFromDisplay": f"Dauerpreis, im Laden notiert{f' am {seen:%d.%m.%Y}' if seen else ''}",
            "categories": [],
            "image": None,
            "url": stores[m["store"]]["url"],
            "ean": m.get("ean"),
            "protein100g": m.get("protein"),  # from the label / Open Food Facts, replaces the estimate
        })
    return result


async def main():
    result = {"updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stores": [], "offers": []}
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"offers": []}
    failed = []
    async with async_playwright() as p:
        browsers = {}
        for store in STORES:
            try:
                headed = getattr(store, "HEADED", False)
                if headed not in browsers:
                    browsers[headed] = await p.chromium.launch(headless=not headed)
                offers = await store.fetch(browsers[headed])
                if not offers:
                    raise RuntimeError("no offers found")
                print(f"{store.STORE['name']}: {len(offers)} offers")
            except Exception as exc:  # keep last week's data for this store rather than an empty page
                print(f"{store.STORE['name']}: FAILED ({exc}), keeping previous data", file=sys.stderr)
                failed.append(store.STORE["id"])
                offers = [o for o in previous["offers"] if o["store"] == store.STORE["id"] and not o.get("manual")]
            result["stores"].append({**store.STORE, "count": len(offers), "stale": store.STORE["id"] in failed})
            result["offers"] += offers
        for browser in browsers.values():
            await browser.close()

    result["offers"] += manual_offers()
    annotate(result["offers"])
    result["offers"].sort(key=lambda o: (o["validFrom"], o["store"], o["name"] or ""))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({len(result['offers'])} offers)")
    return 1 if len(failed) == len(STORES) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
