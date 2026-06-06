"""
Product Monitor Scraper
Uses Shopify's public JSON API -- no HTML scraping needed.
Runs via GitHub Actions every 6 hours.
"""

import requests
import json
import os
from datetime import datetime, timezone

SITES = [
    {
        "name": "Hotspot Electronics",
        "base_url": "https://hotspotelectronics.co.nz",
        "api_url": "https://hotspotelectronics.co.nz/products.json",
    },
    {
        "name": "TechCrazy",
        "base_url": "https://www.techcrazy.co.nz",
        "api_url": "https://www.techcrazy.co.nz/products.json",
    },
]

DATA_DIR = "docs/data"
PRODUCTS_FILE = f"{DATA_DIR}/products.json"
NEW_PRODUCTS_FILE = f"{DATA_DIR}/new_products.json"
PRICE_DROPS_FILE = f"{DATA_DIR}/price_drops.json"
LAST_UPDATED_FILE = f"{DATA_DIR}/last_updated.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ProductMonitorBot/1.0; "
        "+https://github.com)"
    )
}


def fetch_all_products(api_url, base_url):
    products = []
    page = 1
    while True:
        url = f"{api_url}?limit=250&page={page}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  ERROR fetching page {page}: {e}")
            break

        batch = resp.json().get("products", [])
        if not batch:
            break

        for p in batch:
            variants = p.get("variants", [])
            if not variants:
                continue
            variant = variants[0]
            try:
                price = float(variant["price"])
            except (ValueError, TypeError):
                continue

            image_url = ""
            images = p.get("images", [])
            if images:
                image_url = images[0].get("src", "")

            products.append({
                "id": str(p["id"]),
                "name": p["title"],
                "url": f"{base_url}/products/{p['handle']}",
                "price": price,
                "image": image_url,
            })

        print(f"  Page {page}: {len(batch)} products")
        page += 1
        if len(batch) < 250:
            break

    return products


def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stored = load_json(PRODUCTS_FILE)
    new_products = []
    price_drops = []
    total_fetched = 0

    for site in SITES:
        print(f"\nFetching: {site['name']}")
        products = fetch_all_products(site["api_url"], site["base_url"])
        total_fetched += len(products)
        print(f"  Total: {len(products)} products")

        for p in products:
            url = p["url"]
            if url not in stored:
                entry = {
                    "name": p["name"],
                    "url": url,
                    "price": p["price"],
                    "image": p["image"],
                    "site": site["name"],
                    "date_first_seen": now,
                }
                stored[url] = entry
                new_products.append(entry)
            else:
                old_price = stored[url].get("price", 0)
                new_price = p["price"]
                if new_price < old_price:
                    price_drops.append({
                        "name": stored[url]["name"],
                        "url": url,
                        "image": stored[url].get("image", p["image"]),
                        "site": stored[url].get("site", site["name"]),
                        "old_price": old_price,
                        "new_price": new_price,
                        "saving": round(old_price - new_price, 2),
                        "saving_pct": round((old_price - new_price) / old_price * 100, 1),
                        "date_first_seen": stored[url].get("date_first_seen", now),
                        "detected_at": now,
                    })
                stored[url]["price"] = new_price
                stored[url]["name"] = p["name"]
                if p["image"]:
                    stored[url]["image"] = p["image"]

    save_json(stored, PRODUCTS_FILE)
    save_json(new_products, NEW_PRODUCTS_FILE)
    save_json(price_drops, PRICE_DROPS_FILE)
    save_json({
        "last_updated": now,
        "total_products": len(stored),
        "new_this_run": len(new_products),
        "price_drops_this_run": len(price_drops),
    }, LAST_UPDATED_FILE)

    print(f"\nDone! Tracked: {len(stored)} | New: {len(new_products)} | Drops: {len(price_drops)}")


if __name__ == "__main__":
    main()
