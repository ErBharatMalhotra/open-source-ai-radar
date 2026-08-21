"""Trend detection engine — identifies anomalies, rising stars, hidden gems.

Detects:
  - 🔥 Rising Stars: High velocity + growing fast
  - 💎 Hidden Gems: Low stars + high velocity + high health
  - ⚠️ Losing Momentum: Previously strong repos with declining signals
  - 🆕 New & Promising: Recently created with strong signals
  - 👑 Established Leaders: High impact + high health
  - ☠️ Abandoned: Historically popular but inactive
  - ⚡ Anomalies: Sudden score/growth jumps between scoring runs
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from radar.storage.database import Database

logger = logging.getLogger(__name__)


class TrendEngine:
    """Identifies trends and anomalies across the repository dataset."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def detect_all(self) -> dict[str, list[dict]]:
        """Run all trend detections. Returns categorized results."""
        results = {
            "rising_stars": self.get_rising_stars(25),
            "hidden_gems": self.get_hidden_gems(25),
            "losing_momentum": self.get_losing_momentum(15),
            "new_promising": self.get_new_promising(15),
            "established": self.get_established(15),
            "anomalies": self.get_anomalies(10),
        }

        # Add category counts
        for key, repos in results.items():
            for r in repos:
                r["trend_type"] = key

        return results

    def get_rising_stars(self, n: int = 25) -> list[dict]:
        """Projects with high velocity — growing fast right now."""
        with self.db._conn() as conn:
            rows = conn.execute(
                """SELECT s.*, r.stars, r.forks, r.language, r.url,
                          a.category, a.sub_category
                FROM scores s
                JOIN repositories r ON s.repo_full_name = r.full_name
                LEFT JOIN ai_analysis a ON s.repo_full_name = a.repo_full_name
                WHERE s.timestamp = (SELECT MAX(timestamp) FROM scores)
                  AND r.stars >= 100
                ORDER BY s.velocity DESC
                LIMIT ?""",
                (n,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_hidden_gems(self, n: int = 25) -> list[dict]:
        """Low stars but high velocity + high health — about to blow up."""
        with self.db._conn() as conn:
            rows = conn.execute(
                """SELECT s.*, r.stars, r.forks, r.language, r.url,
                          a.category, a.sub_category
                FROM scores s
                JOIN repositories r ON s.repo_full_name = r.full_name
                LEFT JOIN ai_analysis a ON s.repo_full_name = a.repo_full_name
                WHERE s.timestamp = (SELECT MAX(timestamp) FROM scores)
                  AND r.stars BETWEEN 10 AND 5000
                  AND s.velocity >= 60
                  AND s.health >= 60
                ORDER BY s.velocity * s.health DESC
                LIMIT ?""",
                (n,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_losing_momentum(self, n: int = 15) -> list[dict]:
        """Previously strong repos with declining health/velocity."""
        with self.db._conn() as conn:
            rows = conn.execute(
                """SELECT s.*, r.stars, r.forks, r.language, r.url,
                          a.category, a.sub_category
                FROM scores s
                JOIN repositories r ON s.repo_full_name = r.full_name
                LEFT JOIN ai_analysis a ON s.repo_full_name = a.repo_full_name
                WHERE s.timestamp = (SELECT MAX(timestamp) FROM scores)
                  AND r.stars >= 1000
                  AND s.velocity <= 30
                  AND s.health <= 40
                ORDER BY s.health ASC
                LIMIT ?""",
                (n,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_new_promising(self, n: int = 15) -> list[dict]:
        """Recently created (< 90 days) with strong signals."""
        with self.db._conn() as conn:
            rows = conn.execute(
                """SELECT s.*, r.stars, r.forks, r.language, r.url,
                          r.created_at, a.category, a.sub_category
                FROM scores s
                JOIN repositories r ON s.repo_full_name = r.full_name
                LEFT JOIN ai_analysis a ON s.repo_full_name = a.repo_full_name
                WHERE s.timestamp = (SELECT MAX(timestamp) FROM scores)
                  AND r.created_at > datetime('now', '-90 days')
                  AND r.stars >= 10
                ORDER BY s.velocity DESC
                LIMIT ?""",
                (n,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_established(self, n: int = 15) -> list[dict]:
        """High impact + high health — mature, reliable projects."""
        with self.db._conn() as conn:
            rows = conn.execute(
                """SELECT s.*, r.stars, r.forks, r.language, r.url,
                          a.category, a.sub_category
                FROM scores s
                JOIN repositories r ON s.repo_full_name = r.full_name
                LEFT JOIN ai_analysis a ON s.repo_full_name = a.repo_full_name
                WHERE s.timestamp = (SELECT MAX(timestamp) FROM scores)
                  AND r.stars >= 5000
                  AND s.health >= 70
                ORDER BY s.impact DESC
                LIMIT ?""",
                (n,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_anomalies(self, n: int = 10) -> list[dict]:
        """Repos with sudden score jumps between scoring runs.

        Compares the two most recent scoring timestamps.
        """
        with self.db._conn() as conn:
            # Get the two most recent timestamps
            timestamps = conn.execute(
                """SELECT DISTINCT timestamp FROM scores
                ORDER BY timestamp DESC LIMIT 2"""
            ).fetchall()

            if len(timestamps) < 2:
                return []

            latest_ts = timestamps[0]["timestamp"]
            prev_ts = timestamps[1]["timestamp"]

            # Find repos with biggest score changes
            rows = conn.execute(
                """SELECT
                    latest.repo_full_name,
                    latest.radar_score as latest_score,
                    prev.radar_score as prev_score,
                    latest.radar_score - prev.radar_score as score_change,
                    r.stars, r.language, r.url,
                    a.category
                FROM scores latest
                JOIN scores prev ON latest.repo_full_name = prev.repo_full_name
                JOIN repositories r ON latest.repo_full_name = r.full_name
                LEFT JOIN ai_analysis a ON latest.repo_full_name = a.repo_full_name
                WHERE latest.timestamp = ?
                  AND prev.timestamp = ?
                  AND ABS(latest.radar_score - prev.radar_score) > 5
                ORDER BY ABS(latest.radar_score - prev.radar_score) DESC
                LIMIT ?""",
                (latest_ts, prev_ts, n),
            ).fetchall()

            results = []
            for r in rows:
                d = dict(r)
                d["trend_direction"] = "up" if d["score_change"] > 0 else "down"
                results.append(d)
            return results

    def get_category_momentum(self) -> list[dict]:
        """Compare category distributions across scoring runs."""
        with self.db._conn() as conn:
            # Current distribution
            current = conn.execute(
                """SELECT category, COUNT(*) as count
                FROM ai_analysis WHERE category != ''
                GROUP BY category ORDER BY count DESC"""
            ).fetchall()

            return [
                {
                    "category": r["category"],
                    "count": r["count"],
                }
                for r in current
            ]

    def get_trending_summary(self) -> dict[str, Any]:
        """Generate a summary of current trends."""
        all_trends = self.detect_all()

        return {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "rising_stars_count": len(all_trends["rising_stars"]),
            "hidden_gems_count": len(all_trends["hidden_gems"]),
            "losing_momentum_count": len(all_trends["losing_momentum"]),
            "new_promising_count": len(all_trends["new_promising"]),
            "anomalies_count": len(all_trends["anomalies"]),
            "top_rising": all_trends["rising_stars"][:5],
            "top_gems": all_trends["hidden_gems"][:5],
            "categories": self.get_category_momentum(),
        }
