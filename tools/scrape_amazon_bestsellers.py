"""
Amazon Bestseller Scraper
Scrapes trending/bestseller products from amazon.de and amazon.com.
Outputs JSON with product data + affiliate links.
"""

import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Setup paths
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]


def get_session():
    """Create a requests session with random user agent."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return session


def polite_sleep():
    """Random delay between requests to avoid detection."""
    time.sleep(random.uniform(3, 6))


def fetch_page(session, url):
    """Fetch a page with error handling."""
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 503:
            print(f"  [BLOCKED] Got 503 for {url} — possible CAPTCHA")
            return None
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"  [ERROR] Failed to fetch {url}: {e}")
        return None


def extract_categories(html, base_url):
    """Extract top-level category links from the bestsellers main page."""
    soup = BeautifulSoup(html, "lxml")
    categories = []

    # Look for category navigation links
    # Amazon uses different structures, try multiple selectors
    selectors = [
        "div._p13n-zg-nav-tree-all_style_zg-browse-group__88fbz a",
        "div#zg_browseRoot a",
        "ul li a[href*='/bestsellers/']",
        "div[role='treeitem'] a",
    ]

    for selector in selectors:
        links = soup.select(selector)
        if links:
            for link in links:
                href = link.get("href", "")
                name = link.get_text(strip=True)
                if not name or not href:
                    continue
                if href.startswith("/"):
                    href = f"https://www.{base_url}{href}"
                if "/bestsellers/" in href and name:
                    categories.append({"name": name, "url": href})
            break

    # Fallback: if no categories found, try broad link search
    if not categories:
        for link in soup.find_all("a", href=True):
            href = link["href"]
            name = link.get_text(strip=True)
            if "/gp/bestsellers/" in href and len(name) > 2 and len(name) < 50:
                if href.startswith("/"):
                    href = f"https://www.{base_url}{href}"
                categories.append({"name": name, "url": href})

    # Deduplicate by URL
    seen = set()
    unique = []
    for cat in categories:
        if cat["url"] not in seen:
            seen.add(cat["url"])
            unique.append(cat)

    return unique


def extract_products(html, domain, affiliate_tag, category_name):
    """Extract product data from a bestseller category page."""
    soup = BeautifulSoup(html, "lxml")
    products = []

    # Try multiple selectors for product cards
    product_cards = (
        soup.select("div.zg-grid-general-faceout")
        or soup.select("div#gridItemRoot")
        or soup.select("li.zg-item-immersion")
        or soup.select("div.a-section.a-spacing-none.aok-relative")
    )

    for card in product_cards:
        try:
            product = extract_single_product(card, domain, affiliate_tag, category_name)
            if product:
                products.append(product)
        except Exception as e:
            print(f"  [WARN] Failed to parse a product card: {e}")
            continue

    return products


def extract_single_product(card, domain, affiliate_tag, category_name):
    """Extract data from a single product card element."""
    # Title
    title_el = (
        card.select_one("a.a-link-normal span div")
        or card.select_one("a.a-link-normal span")
        or card.select_one("div._cDEzb_p13n-sc-css-line-clamp-1_1Fn1y")
        or card.select_one("div.p13n-sc-truncate-desktop-type2")
        or card.select_one("div.p13n-sc-truncated")
        or card.select_one("span.zg-text-center-align")
    )
    title = title_el.get_text(strip=True) if title_el else None
    if not title or len(title) < 3:
        return None

    # ASIN from link
    asin = None
    for link in card.select("a[href]"):
        href = link.get("href", "")
        asin_match = re.search(r"/dp/([A-Z0-9]{10})", href)
        if asin_match:
            asin = asin_match.group(1)
            break
    if not asin:
        return None

    # Price
    price = None
    currency = "EUR" if domain == "amazon.de" else "USD"
    price_el = (
        card.select_one("span.p13n-sc-price")
        or card.select_one("span.a-price span.a-offscreen")
        or card.select_one("span._cDEzb_p13n-sc-price_3mJ9Z")
    )
    if price_el:
        price_text = price_el.get_text(strip=True)
        # Extract numeric price
        price_match = re.search(r"[\d.,]+", price_text.replace("\xa0", ""))
        if price_match:
            price_str = price_match.group()
            # Handle locale: DE uses comma as decimal, US uses period
            if domain == "amazon.de":
                price_str = price_str.replace(".", "").replace(",", ".")
            else:
                price_str = price_str.replace(",", "")
            try:
                price = float(price_str)
            except ValueError:
                pass

    # Image URL
    image_url = None
    img_el = card.select_one("img")
    if img_el:
        image_url = img_el.get("src") or img_el.get("data-src")

    # Rating
    rating = None
    rating_el = card.select_one("span.a-icon-alt") or card.select_one("i.a-icon-star-small")
    if rating_el:
        rating_text = rating_el.get_text(strip=True)
        rating_match = re.search(r"([\d.,]+)", rating_text)
        if rating_match:
            try:
                rating = float(rating_match.group(1).replace(",", "."))
            except ValueError:
                pass

    # Review count
    review_count = 0
    review_el = card.select_one("span.a-size-small") or card.select_one("a.a-size-small")
    if review_el:
        review_text = review_el.get_text(strip=True)
        review_match = re.search(r"([\d.,]+)", review_text.replace(".", "").replace(",", ""))
        if review_match:
            try:
                review_count = int(review_match.group(1))
            except ValueError:
                pass

    # Build affiliate URL
    affiliate_url = f"https://www.{domain}/dp/{asin}"
    if affiliate_tag:
        affiliate_url += f"?tag={affiliate_tag}"

    return {
        "asin": asin,
        "title": title,
        "price": price,
        "currency": currency,
        "image_url": image_url,
        "affiliate_url": affiliate_url,
        "category": category_name,
        "rating": rating,
        "review_count": review_count,
        "domain": domain,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def scrape_marketplace(config, marketplace):
    """Scrape bestsellers for a single marketplace (de or us)."""
    mkt_config = config["amazon"][marketplace]
    domain = mkt_config["domain"]
    base_url = mkt_config["bestsellers_url"]
    affiliate_tag = mkt_config["affiliate_tag"]
    categories_limit = config["amazon"]["categories_limit"]
    products_per_category = config["amazon"]["products_per_category"]

    if not affiliate_tag and marketplace != "us":
        print(f"[SKIP] No affiliate tag for {marketplace}")
        return []

    print(f"\n{'='*60}")
    print(f"Scraping {domain} bestsellers...")
    print(f"{'='*60}")

    session = get_session()
    all_products = []

    # Step 1: Get categories
    print(f"Fetching main bestsellers page: {base_url}")
    html = fetch_page(session, base_url)
    if not html:
        print("[ERROR] Could not fetch main bestsellers page")
        return []

    categories = extract_categories(html, domain)
    print(f"Found {len(categories)} categories")

    if not categories:
        print("[WARN] No categories found — trying direct category URLs")
        # Fallback: use known category paths
        if marketplace == "de":
            categories = [
                {"name": "Elektronik & Foto", "url": f"https://www.{domain}/gp/bestsellers/ce-de"},
                {"name": "Küche, Haushalt & Wohnen", "url": f"https://www.{domain}/gp/bestsellers/kitchen"},
                {"name": "Bücher", "url": f"https://www.{domain}/gp/bestsellers/books"},
                {"name": "Sport & Freizeit", "url": f"https://www.{domain}/gp/bestsellers/sports"},
                {"name": "Garten", "url": f"https://www.{domain}/gp/bestsellers/garden"},
            ]
        else:
            categories = [
                {"name": "Electronics", "url": f"https://www.{domain}/gp/bestsellers/electronics"},
                {"name": "Kitchen & Dining", "url": f"https://www.{domain}/gp/bestsellers/kitchen"},
                {"name": "Books", "url": f"https://www.{domain}/gp/bestsellers/books"},
                {"name": "Sports & Outdoors", "url": f"https://www.{domain}/gp/bestsellers/sporting-goods"},
                {"name": "Home & Kitchen", "url": f"https://www.{domain}/gp/bestsellers/home-garden"},
            ]

    # Step 2: Scrape each category
    for i, cat in enumerate(categories[:categories_limit]):
        print(f"\n[{i+1}/{min(len(categories), categories_limit)}] {cat['name']}")
        polite_sleep()

        session = get_session()  # Fresh session per category
        html = fetch_page(session, cat["url"])
        if not html:
            continue

        products = extract_products(html, domain, affiliate_tag, cat["name"])
        products = products[:products_per_category]
        print(f"  Found {len(products)} products")

        all_products.extend(products)

    # Deduplicate by ASIN
    seen_asins = set()
    unique_products = []
    for p in all_products:
        if p["asin"] not in seen_asins:
            seen_asins.add(p["asin"])
            unique_products.append(p)

    print(f"\nTotal unique products for {domain}: {len(unique_products)}")
    return unique_products


def main():
    # Load config
    with open(ROOT / "config.yaml") as f:
        config = yaml.safe_load(f)

    all_products = []

    # Scrape DE
    de_products = scrape_marketplace(config, "de")
    all_products.extend(de_products)

    # Scrape US (only if tag is configured)
    us_tag = config["amazon"]["us"]["affiliate_tag"]
    if us_tag:
        us_products = scrape_marketplace(config, "us")
        all_products.extend(us_products)
    else:
        print("\n[INFO] US marketplace skipped — no affiliate tag configured")

    # Save results
    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = ROOT / ".tmp" / "scraped"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"products_{today}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"DONE — Saved {len(all_products)} products to {output_file}")
    print(f"{'='*60}")

    return all_products


if __name__ == "__main__":
    main()
