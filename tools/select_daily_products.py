"""
Daily Product Selector
Picks the best products from scraped data for today's pins.
Filters by rating, ensures category diversity, avoids duplicates.
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_posted_history():
    """Load history of already-posted ASINs."""
    history_file = ROOT / ".tmp" / "posted_history.json"
    if history_file.exists():
        with open(history_file, encoding="utf-8") as f:
            return json.load(f)
    return []


def get_recent_asins(history, days=30):
    """Get ASINs posted within the last N days."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    return {
        entry["asin"]
        for entry in history
        if entry.get("posted_at", "") > cutoff
    }


def select_products(products, config):
    """Select the best products for today's pins."""
    daily_count = config["amazon"]["daily_pin_count"]
    min_rating = config["amazon"]["min_rating"]
    dedup_days = config["amazon"]["dedup_days"]

    # Load history for deduplication
    history = load_posted_history()
    recent_asins = get_recent_asins(history, dedup_days)

    # Filter
    filtered = []
    for p in products:
        # Must have essential fields
        if not p.get("title") or not p.get("asin"):
            continue
        # Rating filter (allow None — some products don't show rating)
        if p.get("rating") and p["rating"] < min_rating:
            continue
        # Skip recently posted
        if p["asin"] in recent_asins:
            continue
        filtered.append(p)

    print(f"After filtering: {len(filtered)} products (from {len(products)} total)")

    # Score products: prioritize high rating * review count
    for p in filtered:
        rating = p.get("rating") or 4.0
        reviews = p.get("review_count") or 0
        # Popularity score
        p["_score"] = rating * (reviews ** 0.5) if reviews > 0 else rating

    # Sort by score descending
    filtered.sort(key=lambda x: x["_score"], reverse=True)

    # Diversify: max 2 per category
    selected = []
    category_count = defaultdict(int)
    max_per_category = max(2, daily_count // 3)

    for p in filtered:
        cat = p.get("category", "unknown")
        if category_count[cat] >= max_per_category:
            continue
        selected.append(p)
        category_count[cat] += 1
        if len(selected) >= daily_count:
            break

    # Clean up internal score field
    for p in selected:
        p.pop("_score", None)

    print(f"Selected {len(selected)} products across {len(category_count)} categories")
    return selected


def main():
    with open(ROOT / "config.yaml") as f:
        config = yaml.safe_load(f)

    # Load today's scraped products
    today = datetime.now().strftime("%Y-%m-%d")
    input_file = ROOT / ".tmp" / "scraped" / f"products_{today}.json"

    if not input_file.exists():
        print(f"[ERROR] No scraped data found for today: {input_file}")
        print("Run scrape_amazon_bestsellers.py first.")
        return []

    with open(input_file, encoding="utf-8") as f:
        products = json.load(f)

    print(f"Loaded {len(products)} scraped products")

    selected = select_products(products, config)

    # Save selection
    output_file = ROOT / ".tmp" / "scraped" / f"daily_selection_{today}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(selected, f, ensure_ascii=False, indent=2)

    print(f"Saved to {output_file}")

    # Print summary
    for i, p in enumerate(selected, 1):
        price_str = f"{p['currency']} {p['price']}" if p.get("price") else "N/A"
        rating_str = f"{p['rating']}/5" if p.get("rating") else "N/A"
        print(f"  {i}. [{p['domain']}] {p['title'][:60]}... | {price_str} | {rating_str}")

    return selected


if __name__ == "__main__":
    main()
