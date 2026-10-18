"""Fetch every store's offers and write docs/data/offers.json for the web page.

Usage: python -m scraper.run
Each module in scraper/stores/ exposes STORE and fetch(browser). A module with HEADED = True gets a
visible browser window (Migros refuses headless Chromium); on a server without a display use xvfb-run.

Coop is missing on purpose: coop.ch answers HTTP 403 to Playwright, headless and headed, even for
robots.txt, so there is no honest way to read its promotions.
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

from scraper.health import annotate
from scraper.stores import aldi, lidl, migros

STORES = [aldi, migros, lidl]
OUT = Path(__file__).resolve().parent.parent / "docs" / "data" / "offers.json"


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
                offers = [o for o in previous["offers"] if o["store"] == store.STORE["id"]]
            result["stores"].append({**store.STORE, "count": len(offers), "stale": store.STORE["id"] in failed})
            result["offers"] += offers
        for browser in browsers.values():
            await browser.close()

    annotate(result["offers"])
    result["offers"].sort(key=lambda o: (o["validFrom"], o["store"], o["name"] or ""))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({len(result['offers'])} offers)")
    return 1 if len(failed) == len(STORES) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
