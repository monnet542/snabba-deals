"""
Site Deployer
Pushes the site/ directory to GitHub Pages.
Uses a separate gh-pages branch for deployment.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "site"


def run_cmd(cmd, cwd=None):
    """Run a shell command and return output."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=cwd or str(ROOT), encoding="utf-8", errors="replace"
    )
    if result.returncode != 0 and result.stderr:
        print(f"  [WARN] {result.stderr.strip()}")
    return result


def main():
    if not SITE_DIR.exists():
        print("[ERROR] site/ directory does not exist. Run build_site.py first.")
        return False

    # Check if gh-pages branch exists, create if not
    result = run_cmd("git branch --list gh-pages")
    if "gh-pages" not in result.stdout:
        print("  Creating gh-pages branch...")
        # Create an orphan gh-pages branch
        run_cmd("git checkout --orphan gh-pages", cwd=str(SITE_DIR))
        run_cmd("git rm -rf .", cwd=str(SITE_DIR))

    # Use git worktree or subtree push approach
    # Simplest: use ghp-import if available, otherwise manual approach
    print("  Deploying site/ to gh-pages branch...")

    # Copy site contents to a temp deploy process using subtree
    result = run_cmd('git add site/ && git subtree push --prefix site origin gh-pages')

    if result.returncode == 0:
        print("  Site deployed to GitHub Pages!")
        return True
    else:
        # Fallback: manual approach
        print("  Subtree push failed. Trying manual deploy...")
        print("  You can deploy manually:")
        print("    1. Push this repo to GitHub")
        print("    2. Go to Settings > Pages")
        print("    3. Set source to 'Deploy from branch' > 'main' > '/site'")
        print("  Or install ghp-import: pip install ghp-import")
        print("    Then run: ghp-import -p site/")
        return False


if __name__ == "__main__":
    main()
