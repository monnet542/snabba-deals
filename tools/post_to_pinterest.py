"""
Pinterest Pin Poster
Creates pins on Pinterest via API v5 with images, descriptions, and affiliate links.
"""

import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

API_BASE = "https://api.pinterest.com/v5"


def upload_image_to_pinterest(token, image_path):
    """
    Upload a local image to Pinterest's media endpoint.
    Returns the media_id for use in pin creation.

    Note: Pinterest v5 API prefers image URLs. For local files,
    we use the media upload flow.
    """
    # Pinterest v5 supports direct image upload via multipart form
    # Step 1: Register media upload
    resp = requests.post(
        f"{API_BASE}/media",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"media_type": "image"},
    )

    if resp.status_code not in (200, 201):
        print(f"  [ERROR] Media registration failed: {resp.status_code} {resp.text}")
        return None

    media_data = resp.json()
    upload_url = media_data.get("upload_url")
    media_id = media_data.get("media_id")

    if not upload_url:
        print("  [ERROR] No upload URL received")
        return None

    # Step 2: Upload the actual image
    with open(image_path, "rb") as img_file:
        upload_resp = requests.put(
            upload_url,
            data=img_file.read(),
            headers={"Content-Type": "image/png"},
        )

    if upload_resp.status_code not in (200, 201, 204):
        print(f"  [ERROR] Image upload failed: {upload_resp.status_code}")
        return None

    return media_id


def create_pin(token, board_id, title, description, link, image_path):
    """Create a pin on Pinterest."""
    # For simplicity, use image_url approach if we have a URL,
    # otherwise try the media upload approach

    pin_data = {
        "board_id": board_id,
        "title": title[:100],  # Pinterest title limit
        "description": description[:500],  # Pinterest description limit
        "link": link,
        "alt_text": title[:500],
    }

    # Try to read the image and upload as base64 or use media upload
    if image_path and os.path.exists(image_path):
        import base64
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        pin_data["media_source"] = {
            "source_type": "image_base64",
            "content_type": "image/png",
            "data": image_data,
        }
    else:
        print(f"  [WARN] No image found at {image_path}")
        return None

    resp = requests.post(
        f"{API_BASE}/pins",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=pin_data,
    )

    if resp.status_code in (200, 201):
        pin = resp.json()
        print(f"  Pin created! ID: {pin.get('id')}")
        return pin
    else:
        print(f"  [ERROR] Pin creation failed: {resp.status_code}")
        print(f"  {resp.text[:300]}")
        return None


def update_posted_history(products_posted):
    """Update the history file with newly posted products."""
    history_file = ROOT / ".tmp" / "posted_history.json"

    history = []
    if history_file.exists():
        with open(history_file, encoding="utf-8") as f:
            history = json.load(f)

    for product in products_posted:
        history.append({
            "asin": product["asin"],
            "domain": product["domain"],
            "pin_id": product.get("_pin_id"),
            "posted_at": datetime.now().isoformat(),
        })

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def main():
    from pinterest_auth import get_valid_token
    from pinterest_board_manager import ensure_boards_exist, get_board_id_for_category

    token = get_valid_token()
    if not token:
        print("[ERROR] Could not get Pinterest token")
        sys.exit(1)

    with open(ROOT / "config.yaml") as f:
        config = yaml.safe_load(f)

    # Ensure boards exist
    print("Checking boards...")
    board_id_map = ensure_boards_exist(token, config)

    # Load today's content
    today = datetime.now().strftime("%Y-%m-%d")
    input_file = ROOT / ".tmp" / "scraped" / f"daily_content_{today}.json"

    if not input_file.exists():
        print(f"[ERROR] No content data found: {input_file}")
        print("Run the content and image generation tools first.")
        return

    with open(input_file, encoding="utf-8") as f:
        products = json.load(f)

    print(f"\nPosting {len(products)} pins to Pinterest...")

    posted = []
    for i, product in enumerate(products, 1):
        print(f"\n[{i}/{len(products)}] {product.get('pin_title', product['title'])[:50]}...")

        # Get board
        category = product.get("category", "default")
        board_id = get_board_id_for_category(category, config, board_id_map)
        if not board_id:
            # Fallback to first available board
            board_id = next(iter(board_id_map.values()), None)
        if not board_id:
            print("  [ERROR] No board available — skipping")
            continue

        # Build description with hashtags
        description = product.get("pin_description", product["title"])
        hashtags = product.get("pin_hashtags", [])
        if hashtags:
            hashtag_str = " ".join(f"#{tag}" for tag in hashtags[:10])
            description = f"{description}\n\n{hashtag_str}"

        # Create pin
        pin = create_pin(
            token=token,
            board_id=board_id,
            title=product.get("pin_title", product["title"]),
            description=description,
            link=product["affiliate_url"],
            image_path=product.get("pin_image_path"),
        )

        if pin:
            product["_pin_id"] = pin.get("id")
            posted.append(product)

        # Rate limiting: wait between posts
        if i < len(products):
            wait = random.uniform(30, 60)
            print(f"  Waiting {wait:.0f}s before next pin...")
            time.sleep(wait)

    # Update history
    if posted:
        update_posted_history(posted)
        print(f"\nSuccessfully posted {len(posted)}/{len(products)} pins!")
    else:
        print("\nNo pins were posted.")


if __name__ == "__main__":
    main()
