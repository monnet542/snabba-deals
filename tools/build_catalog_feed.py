"""
Pinterest Catalog Feed Generator
Creates a TSV file compatible with Pinterest's catalog data source format.
Pinterest fetches this file daily to create/update product Pins automatically.
"""

import csv
import json
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "docs"


def main():
    with open(ROOT / "config.yaml") as f:
        config = yaml.safe_load(f)

    site_base_url = config.get("site", {}).get("base_url", "")

    # Load today's content
    today = datetime.now().strftime("%Y-%m-%d")
    input_file = ROOT / ".tmp" / "scraped" / f"daily_content_{today}.json"

    if not input_file.exists():
        print(f"[ERROR] No content data found: {input_file}")
        return

    with open(input_file, encoding="utf-8") as f:
        products = json.load(f)

    print(f"Generating Pinterest catalog feed for {len(products)} products...")

    # Required Pinterest catalog fields:
    # id, title, description, link, image_link, price, availability
    fieldnames = [
        "id",
        "title",
        "description",
        "link",
        "image_link",
        "price",
        "availability",
        "brand",
        "condition",
        "product_type",
    ]

    output_path = SITE_DIR / "catalog.tsv"
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()

        for product in products:
            asin = product["asin"]
            domain = product["domain"]
            is_de = domain == "amazon.de"

            # Price formatting: Pinterest expects "9.99 EUR" or "9.99 USD"
            price = product.get("price")
            currency = "EUR" if is_de else "USD"
            if isinstance(price, (int, float)) and price:
                price_str = f"{price:.2f} {currency}"
            else:
                price_str = ""

            # Image URL — use locally hosted image if available
            img_path = SITE_DIR / "images" / f"{asin}.jpg"
            if img_path.exists():
                image_link = f"{site_base_url}/images/{asin}.jpg"
            else:
                image_link = product.get("image_url", "")

            # Description
            description = product.get("pin_description", product["title"])
            if not description:
                description = product["title"]

            # Product page link (landing page with affiliate link)
            link = f"{site_base_url}/products/{asin}.html"

            # Category
            category = product.get("category", "")

            row = {
                "id": asin,
                "title": product.get("pin_title", product["title"])[:150],
                "description": description[:10000],
                "link": link,
                "image_link": image_link,
                "price": price_str,
                "availability": "in stock",
                "brand": product.get("brand", ""),
                "condition": "new",
                "product_type": category,
            }
            writer.writerow(row)

    print(f"  Catalog feed: {output_path}")
    print(f"  URL: {site_base_url}/catalog.tsv")
    return str(output_path)


if __name__ == "__main__":
    main()
