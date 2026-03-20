"""
Pin Content Generator
Uses Claude API to generate Pinterest-optimized titles, descriptions, and hashtags.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def load_prompt_template():
    """Load the prompt template for pin content generation."""
    template_path = ROOT / "tools" / "prompts" / "pin_content.txt"
    with open(template_path, encoding="utf-8") as f:
        return f.read()


def generate_content_for_product(client, product, template, config):
    """Generate pin content for a single product using Claude."""
    hashtag_count = config["content"]["hashtag_count"]
    model = config["content"]["model"]

    prompt = template.format(
        title=product["title"],
        category=product.get("category", "General"),
        price=product.get("price", "N/A"),
        currency=product.get("currency", ""),
        rating=product.get("rating", "N/A"),
        domain=product["domain"],
        hashtag_count=hashtag_count,
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text.strip()

        # Parse JSON response
        # Handle potential markdown wrapping
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        content = json.loads(response_text)

        # Validate required fields
        if "title" not in content or "description" not in content:
            print(f"  [WARN] Missing fields in response for {product['asin']}")
            return None

        # Ensure hashtags is a list
        if "hashtags" not in content:
            content["hashtags"] = []

        return content

    except json.JSONDecodeError as e:
        print(f"  [ERROR] Failed to parse JSON for {product['asin']}: {e}")
        print(f"  Response was: {response_text[:200]}")
        return None
    except anthropic.APIError as e:
        print(f"  [ERROR] API error for {product['asin']}: {e}")
        return None


def main():
    # Check API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ERROR] ANTHROPIC_API_KEY not set in .env")
        print("Get your key at: https://console.anthropic.com/")
        sys.exit(1)

    with open(ROOT / "config.yaml") as f:
        config = yaml.safe_load(f)

    # Load today's selection
    today = datetime.now().strftime("%Y-%m-%d")
    input_file = ROOT / ".tmp" / "scraped" / f"daily_selection_{today}.json"

    if not input_file.exists():
        print(f"[ERROR] No daily selection found: {input_file}")
        print("Run select_daily_products.py first.")
        return []

    with open(input_file, encoding="utf-8") as f:
        products = json.load(f)

    print(f"Generating content for {len(products)} products...")

    client = anthropic.Anthropic(api_key=api_key)
    template = load_prompt_template()

    enriched = []
    for i, product in enumerate(products, 1):
        print(f"\n[{i}/{len(products)}] {product['title'][:50]}...")

        content = generate_content_for_product(client, product, template, config)
        if content:
            product["pin_title"] = content["title"]
            product["pin_description"] = content["description"]
            product["pin_hashtags"] = content["hashtags"]
            print(f"  Title: {content['title']}")
        else:
            # Fallback: use product title directly
            product["pin_title"] = product["title"][:100]
            lang = "de" if product["domain"] == "amazon.de" else "en"
            if lang == "de":
                product["pin_description"] = f"{product['title']} — Jetzt entdecken!"
            else:
                product["pin_description"] = f"{product['title']} — Check it out!"
            product["pin_hashtags"] = []
            print("  [FALLBACK] Using product title as pin content")

        enriched.append(product)

    # Save enriched data
    output_file = ROOT / ".tmp" / "scraped" / f"daily_content_{today}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    print(f"\nSaved enriched content to {output_file}")
    return enriched


if __name__ == "__main__":
    main()
