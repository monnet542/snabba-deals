"""
Site Deployer
Commits docs/ changes and pushes to GitHub.
GitHub Pages is configured to serve from /docs on the main branch.
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "docs"


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
        print("[ERROR] docs/ directory does not exist. Run build_site.py first.")
        return False

    today = datetime.now().strftime("%Y-%m-%d")

    # Check if there are changes to commit
    run_cmd("git add docs/")
    status = run_cmd("git status --porcelain docs/")

    if not status.stdout.strip():
        print("  No changes to deploy.")
        return True

    # Commit changes
    commit_msg = f"Update deals {today}"
    result = run_cmd(f'git commit -m "{commit_msg}"')
    if result.returncode != 0:
        print(f"  [ERROR] Commit failed: {result.stderr.strip()}")
        return False
    print(f"  Committed: {commit_msg}")

    # Push to origin
    result = run_cmd("git push origin main")
    if result.returncode != 0:
        print(f"  [ERROR] Push failed: {result.stderr.strip()}")
        print("  You may need to push manually: git push origin main")
        return False

    print("  Pushed to GitHub. Site will update in ~1 minute.")
    return True


if __name__ == "__main__":
    main()
