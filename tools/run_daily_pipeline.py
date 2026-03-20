"""
Daily Pipeline Orchestrator
Runs the full affiliate pin pipeline: Scrape -> Select -> Content -> Images -> Post
"""

import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
load_dotenv(ROOT / ".env")


def log_step(step_name, status, details=""):
    """Print a formatted log entry."""
    icon = "OK" if status == "ok" else "FAIL" if status == "error" else ">>"
    print(f"  [{icon}] {step_name}: {details}")


def run_pipeline(dry_run=False):
    """Run the complete daily pipeline."""
    today = datetime.now().strftime("%Y-%m-%d")
    start_time = datetime.now()

    print(f"\n{'='*60}")
    print(f"  SNABBA CASH — Daily Pipeline")
    print(f"  Date: {today}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"{'='*60}\n")

    results = {
        "date": today,
        "started_at": start_time.isoformat(),
        "steps": {},
        "errors": [],
    }

    # Step 1: Scrape Amazon Bestsellers
    print("STEP 1: Scraping Amazon Bestsellers...")
    try:
        from scrape_amazon_bestsellers import main as scrape_main
        products = scrape_main()
        results["steps"]["scrape"] = {
            "status": "ok",
            "products_found": len(products),
        }
        log_step("Scrape", "ok", f"{len(products)} products found")
    except Exception as e:
        results["steps"]["scrape"] = {"status": "error", "error": str(e)}
        results["errors"].append(f"Scrape: {e}")
        log_step("Scrape", "error", str(e))
        traceback.print_exc()
        print("\n[ABORT] Cannot continue without scraped data.")
        save_log(results)
        return results

    # Step 2: Select Daily Products
    print("\nSTEP 2: Selecting daily products...")
    try:
        from select_daily_products import main as select_main
        selected = select_main()
        results["steps"]["select"] = {
            "status": "ok",
            "products_selected": len(selected),
        }
        log_step("Select", "ok", f"{len(selected)} products selected")
    except Exception as e:
        results["steps"]["select"] = {"status": "error", "error": str(e)}
        results["errors"].append(f"Select: {e}")
        log_step("Select", "error", str(e))
        traceback.print_exc()
        print("\n[ABORT] Cannot continue without product selection.")
        save_log(results)
        return results

    if not selected:
        print("\n[DONE] No products to process today.")
        save_log(results)
        return results

    # Step 3: Generate Pin Content (Text)
    print("\nSTEP 3: Generating pin content...")
    load_dotenv(ROOT / ".env", override=True)  # Reload to ensure keys are fresh
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [SKIP] No ANTHROPIC_API_KEY — using fallback content")
        results["steps"]["content"] = {"status": "skipped", "reason": "no API key"}
        # Create fallback content file
        content_file = ROOT / ".tmp" / "scraped" / f"daily_content_{today}.json"
        for p in selected:
            lang = "de" if p["domain"] == "amazon.de" else "en"
            p["pin_title"] = p["title"][:100]
            if lang == "de":
                price_str = f" für nur {p['currency']} {p['price']}" if p.get("price") else ""
                p["pin_description"] = f"{p['title']}{price_str} — Jetzt entdecken!"
            else:
                price_str = f" for just {p['currency']} {p['price']}" if p.get("price") else ""
                p["pin_description"] = f"{p['title']}{price_str} — Check it out!"
            p["pin_hashtags"] = []
        with open(content_file, "w", encoding="utf-8") as f:
            json.dump(selected, f, ensure_ascii=False, indent=2)
    else:
        try:
            from generate_pin_content import main as content_main
            enriched = content_main()
            results["steps"]["content"] = {
                "status": "ok",
                "products_enriched": len(enriched),
            }
            log_step("Content", "ok", f"{len(enriched)} products enriched")
        except Exception as e:
            results["steps"]["content"] = {"status": "error", "error": str(e)}
            results["errors"].append(f"Content: {e}")
            log_step("Content", "error", str(e))

    # Step 4: Images — skipped, build_site.py downloads Amazon product images directly
    print("\nSTEP 4: Images — using Amazon product photos (downloaded by build_site)")
    results["steps"]["images"] = {"status": "skipped", "reason": "using Amazon product images"}

    # Step 5: Build Website + RSS Feed
    print("\nSTEP 5: Building website + RSS feed...")
    try:
        from build_site import main as build_main
        pages = build_main()
        results["steps"]["build_site"] = {
            "status": "ok",
            "pages_built": len(pages) if pages else 0,
        }
        log_step("Build Site", "ok", f"{len(pages) if pages else 0} pages built")
    except Exception as e:
        results["steps"]["build_site"] = {"status": "error", "error": str(e)}
        results["errors"].append(f"Build Site: {e}")
        log_step("Build Site", "error", str(e))
        traceback.print_exc()

    # Step 5b: Build Pinterest catalog feed
    print("\nSTEP 5b: Building Pinterest catalog feed...")
    try:
        from build_catalog_feed import main as catalog_main
        catalog_main()
        results["steps"]["catalog_feed"] = {"status": "ok"}
        log_step("Catalog Feed", "ok", "Generated successfully")
    except Exception as e:
        results["steps"]["catalog_feed"] = {"status": "error", "error": str(e)}
        results["errors"].append(f"Catalog Feed: {e}")
        log_step("Catalog Feed", "error", str(e))

    # Step 6: Deploy to GitHub Pages (if git is configured)
    print("\nSTEP 6: Deploying site...")
    if dry_run:
        print("  [SKIP] Dry run -- not deploying")
        results["steps"]["deploy"] = {"status": "skipped", "reason": "dry run"}
    else:
        try:
            from deploy_site import main as deploy_main
            deploy_main()
            results["steps"]["deploy"] = {"status": "ok"}
            log_step("Deploy", "ok", "Site deployed")
        except ImportError:
            print("  [SKIP] deploy_site.py not found -- deploy manually")
            results["steps"]["deploy"] = {"status": "skipped", "reason": "no deploy script"}
        except Exception as e:
            results["steps"]["deploy"] = {"status": "error", "error": str(e)}
            results["errors"].append(f"Deploy: {e}")
            log_step("Deploy", "error", str(e))

    # Summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    results["finished_at"] = end_time.isoformat()
    results["duration_seconds"] = duration

    print(f"\n{'='*60}")
    print(f"  Pipeline complete in {duration:.1f}s")
    print(f"  Errors: {len(results['errors'])}")
    if results["errors"]:
        for err in results["errors"]:
            print(f"    - {err}")
    print(f"{'='*60}\n")

    save_log(results)
    return results


def save_log(results):
    """Save pipeline log to .tmp/"""
    log_dir = ROOT / ".tmp"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"pipeline_log_{results['date']}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Log saved: {log_file}")


def main():
    # Check for --dry-run flag
    dry_run = "--dry-run" in sys.argv

    run_pipeline(dry_run=dry_run)


if __name__ == "__main__":
    main()
