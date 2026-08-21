"""RSS feed generator for Open Source AI Radar.

Generates an RSS 2.0 feed of trending repos, new discoveries,
and weekly report summaries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from radar.storage.database import Database


def _esc(text: str) -> str:
    """Escape XML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class RSSGenerator:
    """Generates RSS 2.0 feeds."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def generate_trending_feed(self, output_path: str | Path = "data/exports/feed.xml") -> str:
        """Generate RSS feed of trending repositories."""
        from radar.scoring.trends import TrendEngine

        engine = TrendEngine(self.db)
        trends = engine.detect_all()
        now = datetime.now(tz=timezone.utc)

        items: list[str] = []

        # Rising stars
        for repo in trends.get("rising_stars", [])[:20]:
            items.append(self._repo_item(repo, "🔥 Rising Star", now))

        # Hidden gems
        for repo in trends.get("hidden_gems", [])[:15]:
            items.append(self._repo_item(repo, "💎 Hidden Gem", now))

        # New promising
        for repo in trends.get("new_promising", [])[:10]:
            items.append(self._repo_item(repo, "🆕 New & Promising", now))

        feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Open Source AI Radar — Trending</title>
    <link>https://opensourceradar.dev</link>
    <description>Discover what is becoming important before everyone else does.</description>
    <language>en</language>
    <lastBuildDate>{now.strftime('%a, %d %b %Y %H:%M:%S +0000')}</lastBuildDate>
    <atom:link href="https://opensourceradar.dev/feed.xml" rel="self" type="application/rss+xml"/>
    {"".join(items)}
  </channel>
</rss>"""

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(feed, encoding="utf-8")
        print(f"RSS feed saved: {out}")
        return str(out)

    def _repo_item(self, repo: dict, tag: str, now: datetime) -> str:
        fn = repo.get("repo_full_name", "")
        stars = repo.get("stars", 0)
        score = repo.get("radar_score", 0)
        desc = repo.get("category", "") or "Open source AI"

        title = f"{tag} {fn} ({stars:,} ⭐)"
        link = f"https://github.com/{fn}"
        description = f"Radar Score: {score:.0f} | Stars: {stars:,} | {desc}"

        return f"""    <item>
      <title>{_esc(title)}</title>
      <link>{_esc(link)}</link>
      <description>{_esc(description)}</description>
      <pubDate>{now.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
      <guid>{_esc(link)}</guid>
    </item>"""
