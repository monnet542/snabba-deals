"""
Static Site Builder
Generates HTML product pages and index page for Pinterest RSS auto-publishing.
Each product gets its own page with Open Graph meta tags for Pinterest Rich Pins.
"""

import html
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from string import Template

import yaml

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "docs"
TEMPLATES_DIR = ROOT / "tools" / "templates"


def load_template(name):
    """Load an HTML template."""
    with open(TEMPLATES_DIR / name, encoding="utf-8") as f:
        return f.read()


def escape(text):
    """HTML-escape text safely."""
    if not text:
        return ""
    return html.escape(str(text))


def rating_to_stars(rating):
    """Convert numeric rating to star display."""
    if not rating:
        return ""
    full = int(rating)
    half = 1 if (rating - full) >= 0.3 else 0
    empty = 5 - full - half
    # Use simple text since Unicode stars can cause issues
    return ("*" * full) + ("+" * half) + ("-" * empty)


def build_product_page(product, config, site_base_url):
    """Build a single product HTML page."""
    template = load_template("product_page.html")

    asin = product["asin"]
    domain = product["domain"]
    is_de = domain == "amazon.de"

    # Determine language and localized strings
    lang = "de" if is_de else "en"
    cta_text = "Jetzt auf Amazon ansehen" if is_de else "View on Amazon"
    currency_symbol = "" if is_de else "$"
    affiliate_disclosure = (
        "Als Amazon-Partner verdiene ich an qualifizierten Verkaeufen."
        if is_de
        else "As an Amazon Associate I earn from qualifying purchases."
    )

    # Build page URL
    page_filename = f"{asin}.html"
    page_url = f"{site_base_url}/products/{page_filename}"

    # Image: use pin_image if available, otherwise Amazon product image
    image_url = product.get("image_url", "")

    # If we have a locally generated image, copy it to site/images/
    pin_image_path = product.get("pin_image_path")
    if pin_image_path and os.path.exists(pin_image_path):
        img_dest = SITE_DIR / "images" / f"{asin}.png"
        shutil.copy2(pin_image_path, img_dest)
        image_url = f"{site_base_url}/images/{asin}.png"

    # Price formatting
    price = product.get("price")
    price_str = f"{price:.2f}" if isinstance(price, (int, float)) and price else ""

    # Hashtags
    hashtags = product.get("pin_hashtags", [])
    hashtags_html = " ".join(f'<span>#{escape(tag)}</span>' for tag in hashtags)

    # Short description (for meta tags, no hashtags)
    pin_description = product.get("pin_description", product["title"])
    pin_description_short = pin_description[:200]

    # Rating
    rating = product.get("rating")
    rating_stars = rating_to_stars(rating)
    rating_str = str(rating) if rating else "N/A"

    page_html = Template(template).safe_substitute(
        lang=lang,
        pin_title=escape(product.get("pin_title", product["title"])),
        pin_description_short=escape(pin_description_short),
        pin_description=escape(pin_description),
        image_url=escape(image_url),
        page_url=escape(page_url),
        price=escape(price_str),
        currency=escape(product.get("currency", "")),
        currency_symbol=currency_symbol,
        affiliate_url=escape(product["affiliate_url"]),
        rating=escape(rating_str),
        rating_stars=rating_stars,
        cta_text=cta_text,
        affiliate_disclosure=affiliate_disclosure,
        hashtags_html=hashtags_html,
    )

    # Write page
    products_dir = SITE_DIR / "products"
    products_dir.mkdir(parents=True, exist_ok=True)
    output_path = products_dir / page_filename

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page_html)

    return {
        "asin": asin,
        "page_url": page_url,
        "page_path": str(output_path),
        "image_url": image_url,
        "title": product.get("pin_title", product["title"]),
        "description": pin_description_short,
        "price": price_str,
        "currency": product.get("currency", ""),
    }


def build_index_page(all_pages, site_base_url):
    """Build the main index page with product grid."""
    template = load_template("index_page.html")

    # Group pages by date
    today = datetime.now().strftime("%Y-%m-%d")

    cards_html = ""
    for page in all_pages:
        cards_html += f"""
        <a class="card" href="products/{page['asin']}.html">
            <img src="{escape(page['image_url'])}" alt="{escape(page['title'])}">
            <div class="card-body">
                <div class="card-title">{escape(page['title'])}</div>
                <div class="card-price">{escape(page['currency'])} {escape(page['price'])}</div>
            </div>
        </a>
        """

    product_sections = f"""
        <div class="date-section">Deals vom {today}</div>
        <div class="product-grid">
            {cards_html}
        </div>
    """

    index_html = Template(template).safe_substitute(product_sections=product_sections)

    output_path = SITE_DIR / "index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"  Index page: {output_path}")


def build_rss_feed(all_pages, site_base_url):
    """Build an RSS 2.0 feed that Pinterest can consume."""
    now = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")

    items = ""
    for page in all_pages:
        items += f"""
    <item>
      <title>{escape(page['title'])}</title>
      <link>{escape(page['page_url'])}</link>
      <description>{escape(page['description'])}</description>
      <enclosure url="{escape(page['image_url'])}" type="image/jpeg" />
      <guid isPermaLink="true">{escape(page['page_url'])}</guid>
      <pubDate>{now}</pubDate>
    </item>"""

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Snabba Deals - Top Trending Produkte</title>
    <link>{escape(site_base_url)}</link>
    <description>Taeglich kuratierte Top-Deals und Trending-Produkte von Amazon</description>
    <language>de</language>
    <lastBuildDate>{now}</lastBuildDate>
    <atom:link href="{escape(site_base_url)}/feed.xml" rel="self" type="application/rss+xml" />
    {items}
  </channel>
</rss>"""

    output_path = SITE_DIR / "feed.xml"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rss)

    print(f"  RSS feed: {output_path}")


def main():
    with open(ROOT / "config.yaml") as f:
        config = yaml.safe_load(f)

    # Site base URL — needs to be configured after deployment
    site_base_url = config.get("site", {}).get("base_url", "https://yourusername.github.io/snabba-deals")

    # Load today's content
    today = datetime.now().strftime("%Y-%m-%d")
    input_file = ROOT / ".tmp" / "scraped" / f"daily_content_{today}.json"

    if not input_file.exists():
        print(f"[ERROR] No content data found: {input_file}")
        print("Run the content generation tools first.")
        return []

    with open(input_file, encoding="utf-8") as f:
        products = json.load(f)

    print(f"Building site for {len(products)} products...")

    # Ensure site directories exist
    (SITE_DIR / "products").mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "images").mkdir(parents=True, exist_ok=True)

    # Build individual product pages
    all_pages = []
    for i, product in enumerate(products, 1):
        print(f"  [{i}/{len(products)}] {product.get('pin_title', product['title'])[:50]}...")
        page_info = build_product_page(product, config, site_base_url)
        all_pages.append(page_info)

    # Build index page
    print("\nBuilding index page...")
    build_index_page(all_pages, site_base_url)

    # Build RSS feed
    print("Building RSS feed...")
    build_rss_feed(all_pages, site_base_url)

    print(f"\nDone! Site built with {len(all_pages)} product pages.")
    print(f"  Site directory: {SITE_DIR}")
    print(f"  Open: {SITE_DIR / 'index.html'}")

    return all_pages


if __name__ == "__main__":
    main()
