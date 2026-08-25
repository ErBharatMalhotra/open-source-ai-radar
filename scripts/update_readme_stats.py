"""Refresh the live-stats line in README.md from current DB state.

Replaces the content between the LIVE-STATS markers with real numbers
(repo count, classification rate, tracked stars, last update time).
Called by CI workflows before committing so the README never shows a
stale headline. No-op locally if markers are missing.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

README = Path("README.md")
START = "<!-- LIVE-STATS:START -->"
END = "<!-- LIVE-STATS:END -->"


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
