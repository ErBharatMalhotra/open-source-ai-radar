"""Public API endpoints for Open Source AI Radar.

Generates static API files:
- /api/repos.json — All repositories
- /api/repos.csv — All repositories as CSV
- /api/top.json — Top repos by radar score
- /api/trending.json — Trending repos by velocity
- /api/gems.json — Hidden gems
- /api/breakouts.json — Breakout candidates
- /api/anomalies.json — Detected anomalies
- /api/categories.json — Category intelligence
- /api/stats.json — Summary statistics
- /api/feed.xml — RSS feed
- /api/history/{owner}__{repo}.json — Historical data per repo
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from radar.storage.database import Database

logger = logging.getLogger(__name__)


class PublicAPI:
    """Generates public API files for external consumption."""

    def __init__(self, db: Database, out_dir: str = "data/exports/api") -> None:
        self.db = db
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)

    def generate_all(self) -> dict[str, int]:
        """Generate all API endpoints. Returns count of items per endpoint."""
        counts = {}

        counts["repos"] = self.generate_repos()
        counts["repos_csv"] = self.generate_repos_csv()
        counts["top"] = self.generate_top()
        counts["trending"] = self.generate_trending()
        counts["gems"] = self.generate_gems()
        counts["breakouts"] = self.generate_breakouts()
        counts["anomalies"] = self.generate_anomalies()
        counts["categories"] = self.generate_categories()
        counts["stats"] = self.generate_stats()
        counts["feed"] = self.generate_feed()

        logger.info(f"Generated API endpoints: {counts}")
        return counts

    def generate_repos(self) -> int:
        """Generate /api/repos.json — all repositories."""
        repos = self.db.get_all_repos()

        data = {
            "api_version": "1.0",
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "total": len(repos),
            "repos": [self._clean_repo(r) for r in repos],
        }

        (self.out / "repos.json").write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
        return len(repos)

    def generate_repos_csv(self) -> int:
        """Generate /api/repos.csv — all repositories as CSV."""
        repos = self.db.get_all_repos()

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "full_name", "url", "description", "language", "license",
            "stars", "forks", "open_issues", "created_at", "pushed_at",
        ])

        for r in repos:
            writer.writerow([
                r.get("full_name", ""),
                r.get("url", ""),
                r.get("description", "")[:200],
                r.get("language", ""),
                r.get("license", ""),
                r.get("stars", 0),
                r.get("forks", 0),
                r.get("open_issues", 0),
                r.get("created_at", ""),
                r.get("pushed_at", ""),
            ])

        (self.out / "repos.csv").write_text(
            output.getvalue(), encoding="utf-8"
        )
        return len(repos)

    def generate_top(self, limit: int = 100) -> int:
        """Generate /api/top.json — top repos by radar score."""
        repos = self.db.get_top_repos(limit)

        data = {
            "api_version": "1.0",
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "total": len(repos),
            "repos": [self._clean_scored(r) for r in repos],
        }

        (self.out / "top.json").write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
        return len(repos)

    def generate_trending(self, limit: int = 50) -> int:
        """Generate /api/trending.json — trending repos by velocity."""
        repos = self.db.get_top_repos(limit, "velocity")

        data = {
            "api_version": "1.0",
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "repos": [self._clean_scored(r) for r in repos],
        }

        (self.out / "trending.json").write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
        return len(repos)

    def generate_gems(self, limit: int = 50) -> int:
        """Generate /api/gems.json — hidden gems."""
        with self.db._conn() as conn:
            rows = conn.execute(
                """SELECT s.*, r.full_name, r.stars, r.forks, r.language,
                          r.url, r.description, a.category
                FROM scores s
                JOIN repositories r ON s.repo_full_name = r.full_name
                LEFT JOIN ai_analysis a ON s.repo_full_name = a.repo_full_name
                WHERE s.timestamp = (SELECT MAX(timestamp) FROM scores)
                  AND r.stars BETWEEN 10 AND 5000
                  AND s.velocity >= 60
                  AND s.health >= 60
                ORDER BY s.velocity * s.health DESC
                LIMIT ?""",
                (limit,),
            ).fetchall()

        gems = [self._clean_scored(dict(r)) for r in rows]

        data = {
            "api_version": "1.0",
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "total": len(gems),
            "repos": gems,
        }

        (self.out / "gems.json").write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
        return len(gems)

    def generate_breakouts(self, limit: int = 50) -> int:
        """Generate /api/breakouts.json — breakout candidates."""
        try:
            from radar.analysis.breakout_detector import BreakoutDetector
            detector = BreakoutDetector(self.db)
            breakouts = detector.detect_breakouts(limit)

            data = {
                "api_version": "1.0",
                "generated_at": datetime.now(tz=UTC).isoformat(),
                "total": len(breakouts),
                "candidates": breakouts,
            }

            (self.out / "breakouts.json").write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
            return len(breakouts)
        except Exception as e:
            logger.error(f"Failed to generate breakouts: {e}")
            return 0

    def generate_anomalies(self) -> int:
        """Generate /api/anomalies.json — detected anomalies."""
        try:
            from radar.analysis.anomaly_detector import AnomalyDetector
            detector = AnomalyDetector(self.db)
            summary = detector.get_anomaly_summary()

            (self.out / "anomalies.json").write_text(
                json.dumps(summary, indent=2, default=str),
                encoding="utf-8",
            )
            return summary.get("total_anomalies", 0)
        except Exception as e:
            logger.error(f"Failed to generate anomalies: {e}")
            return 0

    def generate_categories(self) -> int:
        """Generate /api/categories.json — category intelligence."""
        try:
            from radar.analysis.category_tracker import CategoryTracker
            tracker = CategoryTracker(self.db)
            momentums = tracker.get_category_comparison()
            # Exclude Uncategorized from display
            momentums = [m for m in momentums if m.get("category") != "Uncategorized"]

            data = {
                "api_version": "1.0",
                "generated_at": datetime.now(tz=UTC).isoformat(),
                "total": len(momentums),
                "categories": momentums,
            }

            (self.out / "categories.json").write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
            return len(momentums)
        except Exception as e:
            logger.error(f"Failed to generate categories: {e}")
            return 0

    def generate_stats(self) -> int:
        """Generate /api/stats.json — summary statistics."""
        stats = self.db.get_stats()

        # Add processing stats
        try:
            from radar.processing.change_detector import ChangeDetector
            detector = ChangeDetector(self.db)
            proc_stats = detector.get_stats()
            stats.update(proc_stats)
        except Exception:
            pass

        stats["api_version"] = "1.0"
        stats["generated_at"] = datetime.now(tz=UTC).isoformat()

        (self.out / "stats.json").write_text(
            json.dumps(stats, indent=2, default=str),
            encoding="utf-8",
        )
        return stats.get("repos", 0)

    def generate_feed(self) -> int:
        """Generate /api/feed.xml — RSS feed of trending repos."""
        repos = self.db.get_top_repos(20, "velocity")

        items = []
        for r in repos:
            items.append(f"""    <item>
      <title>{self._escape_xml(r.get('full_name', ''))}</title>
      <link>{r.get('url', '')}</link>
      <description>{self._escape_xml(r.get('description', '')[:200])}</description>
      <category>{r.get('category', '')}</category>
      <pubDate>{r.get('pushed_at', '')}</pubDate>
      <guid>{r.get('url', '')}</guid>
    </item>""")

        feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Open Source AI Radar — Trending</title>
    <link>https://erbharatmalhotra.github.io/open-source-ai-radar/</link>
    <description>Trending open-source AI projects ranked by velocity</description>
    <language>en-us</language>
    <lastBuildDate>{datetime.now(tz=UTC).strftime('%a, %d %b %Y %H:%M:%S +0000')}</lastBuildDate>
    <atom:link href="https://erbharatmalhotra.github.io/open-source-ai-radar/api/feed.xml"
               rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""

        (self.out / "feed.xml").write_text(
            feed, encoding="utf-8"
        )
        return len(repos)

    def _clean_repo(self, r: dict) -> dict:
        """Clean repo for API response."""
        return {
            "full_name": r.get("full_name", ""),
            "url": r.get("url", ""),
            "description": r.get("description", ""),
            "language": r.get("language"),
            "license": r.get("license"),
            "stars": r.get("stars", 0),
            "forks": r.get("forks", 0),
            "open_issues": r.get("open_issues", 0),
            "created_at": r.get("created_at"),
            "pushed_at": r.get("pushed_at"),
        }

    def _clean_scored(self, r: dict) -> dict:
        """Clean scored repo for API response."""
        base = self._clean_repo(r)
        base.update({
            "radar_score": r.get("radar_score", 0),
            "impact": r.get("impact", 0),
            "velocity": r.get("velocity", 0),
            "health": r.get("health", 0),
            "global_percentile": r.get("global_percentile", 0),
            "category": r.get("category", ""),
        })
        return base

    def _escape_xml(self, text: str) -> str:
        """Escape special XML characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )
