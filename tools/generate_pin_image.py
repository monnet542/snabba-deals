"""
Pin Image Generator
Creates Pinterest-optimized images using DALL-E 3 with text overlay.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def load_image_themes():
    """Load category-to-visual-theme mapping."""
    themes_path = ROOT / "tools" / "image_themes.json"
    with open(themes_path, encoding="utf-8") as f:
        return json.load(f)


def get_theme_for_category(themes, category):
    """Get the visual theme for a product category."""
    return themes.get(category, themes.get("default", "elegant product display with soft lighting"))


def generate_image(client, product, themes, config):
    """Generate a DALL-E image for a product."""
    category = product.get("category", "default")
    theme = get_theme_for_category(themes, category)

    prompt = (
        f"A beautiful Pinterest-style lifestyle photograph: {theme}. "
        f"Photorealistic, warm and inviting, styled for social media. "
        f"No text, no logos, no watermarks, no people's faces. "
        f"Professional product photography aesthetic, soft natural lighting, "
        f"high resolution, clean composition."
    )

    model = config["image_generation"]["model"]
    size = config["image_generation"]["size"]
    quality = config["image_generation"]["quality"]

    try:
        response = client.images.generate(
            model=model,
            prompt=prompt,
            n=1,
            size=size,
            quality=quality,
        )

        image_url = response.data[0].url
        return image_url

    except Exception as e:
        print(f"  [ERROR] DALL-E generation failed: {e}")
        return None


def download_image(url, save_path):
    """Download an image from URL."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to download image: {e}")
        return False


def add_text_overlay(image_path, output_path, title, price=None, currency=None):
    """Add a text banner at the bottom of the image with product info."""
    try:
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        width, height = img.size

        # Banner dimensions
        banner_height = int(height * 0.18)
        banner_y = height - banner_height

        # Semi-transparent dark banner
        overlay = Image.new("RGBA", (width, banner_height), (0, 0, 0, 180))
        img = img.convert("RGBA")
        img.paste(overlay, (0, banner_y), overlay)

        draw = ImageDraw.Draw(img)

        # Try to use a good font, fallback to default
        font_size_title = int(banner_height * 0.35)
        font_size_price = int(banner_height * 0.28)
        try:
            # Try common Windows fonts
            for font_name in ["arial.ttf", "segoeui.ttf", "calibri.ttf"]:
                try:
                    font_title = ImageFont.truetype(font_name, font_size_title)
                    font_price = ImageFont.truetype(font_name, font_size_price)
                    break
                except OSError:
                    continue
            else:
                font_title = ImageFont.load_default()
                font_price = ImageFont.load_default()
        except Exception:
            font_title = ImageFont.load_default()
            font_price = ImageFont.load_default()

        # Truncate title if too long
        max_chars = 40
        display_title = title[:max_chars] + "..." if len(title) > max_chars else title

        # Draw title
        title_y = banner_y + int(banner_height * 0.15)
        draw.text(
            (int(width * 0.05), title_y),
            display_title,
            fill="white",
            font=font_title,
        )

        # Draw price if available
        if price and currency:
            price_text = f"{currency} {price:.2f}" if isinstance(price, float) else f"{currency} {price}"
            price_y = banner_y + int(banner_height * 0.58)
            draw.text(
                (int(width * 0.05), price_y),
                price_text,
                fill=(255, 200, 50),  # Gold color for price
                font=font_price,
            )

        # Save as PNG
        img = img.convert("RGB")
        img.save(output_path, "PNG", quality=95)
        return True

    except Exception as e:
        print(f"  [ERROR] Text overlay failed: {e}")
        return False


def main():
    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[ERROR] OPENAI_API_KEY not set in .env")
        print("Get your key at: https://platform.openai.com/")
        sys.exit(1)

    with open(ROOT / "config.yaml") as f:
        config = yaml.safe_load(f)

    # Load today's content
    today = datetime.now().strftime("%Y-%m-%d")
    input_file = ROOT / ".tmp" / "scraped" / f"daily_content_{today}.json"

    if not input_file.exists():
        print(f"[ERROR] No content data found: {input_file}")
        print("Run generate_pin_content.py first.")
        return []

    with open(input_file, encoding="utf-8") as f:
        products = json.load(f)

    print(f"Generating images for {len(products)} products...")

    client = OpenAI(api_key=api_key)
    themes = load_image_themes()
    images_dir = ROOT / ".tmp" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    cost_total = 0.0
    cost_per_image = 0.04 if config["image_generation"]["quality"] == "standard" else 0.08

    for i, product in enumerate(products, 1):
        asin = product["asin"]
        print(f"\n[{i}/{len(products)}] {product['title'][:50]}...")

        base_path = images_dir / f"{asin}_base.png"
        final_path = images_dir / f"{asin}_final.png"

        # Generate image
        image_url = generate_image(client, product, themes, config)
        if not image_url:
            product["pin_image_path"] = None
            continue

        cost_total += cost_per_image

        # Download
        if not download_image(image_url, base_path):
            product["pin_image_path"] = None
            continue

        # Add text overlay
        title = product.get("pin_title", product["title"])
        success = add_text_overlay(
            base_path, final_path,
            title=title,
            price=product.get("price"),
            currency=product.get("currency"),
        )

        if success:
            product["pin_image_path"] = str(final_path)
            print(f"  Saved: {final_path.name}")
        else:
            # Use base image without overlay as fallback
            product["pin_image_path"] = str(base_path)
            print("  [FALLBACK] Using image without text overlay")

    # Update content file with image paths
    output_file = ROOT / ".tmp" / "scraped" / f"daily_content_{today}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print(f"\nDone! Total image cost: ${cost_total:.2f}")
    return products


if __name__ == "__main__":
    main()
