"""Refresh live counts in README.md and web meta descriptions from DB state.

Replaces content between the LIVE-STATS markers in README.md and patches
the rounded repo-count claims in web page descriptions so marketing copy
never goes stale. Called by CI workflows before committing.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

README = Path("README.md")
START = "<!-- LIVE-STATS:START -->"
END = "<!-- LIVE-STATS:END -->"

WEB_FILES = [
    Path("web/src/layouts/Layout.astro"),
    Path("web/src/pages/index.astro"),
]

# Rounded down to the nearest thousand so copy never overclaims
def _rounded_thousands(n: int) -> str:
    return f"{(n // 1000) * 1000:,}+"


def _patch_web_counts(total_repos: int) -> int:
    """Update 'X,000+' repo mentions in web meta descriptions."""
    rounded = _rounded_thousands(total_repos)
    patterns = [
        re.compile(r"(Track )[\d,]+\+( AI open-source projects)"),
        re.compile(r"(detection for )[\d,]+\+( projects)"),
        re.compile(r"(Track )[\d,]+\+( projects scored)"),
    ]
    changed = 0
    for path in WEB_FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        new_text = text
        for pat in patterns:
            new_text = pat.sub(lambda m: f"{m.group(1)}{rounded}{m.group(2)}", new_text)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            print(f"Web counts updated in {path}")
            changed += 1
    return changed


def main() -> int:
    from radar.storage.database import Database

    db = Database()
    total_repos = db.get_repo_count()

    with db._conn() as conn:
        classified = conn.execute(
            "SELECT COUNT(*) FROM ai_analysis "
            "WHERE category IS NOT NULL AND category != '' "
            "AND category != 'Uncategorized'"
        ).fetchone()[0]
        category_rows = conn.execute(
            "SELECT COUNT(DISTINCT category) FROM ai_analysis "
            "WHERE category IS NOT NULL AND category != '' "
            "AND category != 'Uncategorized'"
        ).fetchone()[0]
        total_stars = conn.execute(
            "SELECT COALESCE(SUM(stars), 0) FROM repositories"
        ).fetchone()[0]

    pct = (classified / total_repos * 100) if total_repos else 0.0
    stars_m = total_stars / 1_000_000
    updated = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")

    line = (
        f"**Tracking {total_repos:,} repos · "
        f"{pct:.0f}% auto-classified into {category_rows} AI categories · "
        f"{stars_m:.1f}M stars tracked · Updated {updated}**"
    )

    text = README.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(START) + r"\n.*?\n" + re.escape(END), re.DOTALL
    )
    if not pattern.search(text):
        print(f"Warning: {START} markers not found in README.md")
        return 1

    new_text = pattern.sub(f"{START}\n{line}\n{END}", text)
    if new_text != text:
        README.write_text(new_text, encoding="utf-8")
        print(f"README stats updated: {line}")
    else:
        print("README stats already up to date")

    _patch_web_counts(total_repos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
