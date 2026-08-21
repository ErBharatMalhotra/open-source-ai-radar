"""Breakout Detection Engine — identifies repos likely to become breakout projects.

A "breakout" is a repo that's about to jump from obscurity to widespread adoption.
This is NOT prediction — it's candidate ranking based on leading indicators.

Signals used:
- Velocity (growth speed)
- Acceleration (growth is speeding up, not slowing)
- Health (sustainable growth)
- Relative popularity (compared to category peers)
- Category momentum (is the category itself growing?)
- Star velocity vs category median
- Fork velocity vs category median
- Freshness (recent activity)
- Newness (younger repos break out more)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from radar.storage.database import Database

logger = logging.getLogger(__name__)


class BreakoutDetector:
    """Identifies repositories likely to become breakout projects."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def detect_breakouts(self, limit: int = 50) -> list[dict[str, Any]]:
        """Detect breakout candidates across all repos.

        Returns repos ranked by breakout score.
        """
        with self.db._conn() as conn:
            # Get repos with scores and growth data
            rows = conn.execute(
                """SELECT
                    r.full_name, r.stars, r.forks, r.language, r.url,
                    r.created_at, r.pushed_at,
                    s.radar_score, s.impact, s.velocity, s.health,
                    g.stars_7d, g.stars_30d, g.stars_90d,
                    g.star_growth_rate_7d, g.star_growth_rate_30d,
                    g.star_growth_acceleration,
                    g.forks_7d, g.forks_30d,
                    g.freshness_score,
                    a.category
                FROM repositories r
                JOIN scores s ON r.full_name = s.repo_full_name
                LEFT JOIN growth_metrics g ON r.full_name = g.repo_full_name
                    AND g.timestamp = (SELECT MAX(timestamp) FROM growth_metrics)
                LEFT JOIN ai_analysis a ON r.full_name = a.repo_full_name
                WHERE s.timestamp = (SELECT MAX(timestamp) FROM scores)
                  AND r.stars >= 50
                  AND r.stars <= 50000
                  AND g.star_growth_rate_7d IS NOT NULL"""
            ).fetchall()

        if not rows:
            return []

        # Compute category medians for normalization
        category_medians = self._compute_category_medians(rows)

        # Score each repo
        candidates = []
        for row in rows:
            d = dict(row)
            breakout_score = self._compute_breakout_score(d, category_medians)

            if breakout_score >= 40:  # Minimum threshold
                candidates.append({
                    "repo_full_name": d["full_name"],
                    "stars": d["stars"],
                    "forks": d["forks"],
                    "language": d.get("language"),
                    "url": d.get("url"),
                    "category": d.get("category"),
                    "radar_score": round(d.get("radar_score", 0), 1),
                    "velocity": round(d.get("velocity", 0), 1),
                    "health": round(d.get("health", 0), 1),
                    "stars_7d": d.get("stars_7d", 0),
                    "stars_30d": d.get("stars_30d", 0),
                    "star_growth_rate_7d": round(d.get("star_growth_rate_7d", 0), 1),
                    "star_growth_acceleration": round(d.get("star_growth_acceleration", 1), 2),
                    "forks_7d": d.get("forks_7d", 0),
                    "freshness": round(d.get("freshness_score", 0) * 100, 0),
                    "breakout_score": round(breakout_score, 1),
                })

        # Sort by breakout score
        candidates.sort(key=lambda c: c["breakout_score"], reverse=True)

        logger.info(f"Detected {len(candidates)} breakout candidates")
        return candidates[:limit]

    def _compute_category_medians(
        self, rows: list[dict]
    ) -> dict[str, dict[str, float]]:
        """Compute median values per category for normalization."""
        categories: dict[str, list[dict]] = {}

        for row in rows:
            cat = row.get("category", "Unknown")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(dict(row))

        medians = {}
        for cat, cat_rows in categories.items():
            velocities = sorted([r.get("velocity", 0) for r in cat_rows])
            stars_list = sorted([r.get("stars", 0) for r in cat_rows])
            growth_rates = sorted([
                r.get("star_growth_rate_7d", 0) for r in cat_rows
                if r.get("star_growth_rate_7d", 0) > 0
            ])

            n = len(velocities)
            medians[cat] = {
                "velocity": velocities[n // 2] if n > 0 else 50,
                "stars": stars_list[n // 2] if n > 0 else 1000,
                "growth_rate": growth_rates[len(growth_rates) // 2] if growth_rates else 1,
            }

        return medians

    def _compute_breakout_score(
        self,
        repo: dict[str, Any],
        category_medians: dict[str, dict[str, float]],
    ) -> float:
        """Compute breakout score (0-100).

        Factors:
        1. Velocity (25%) — how fast is it growing?
        2. Acceleration (20%) — is growth speeding up?
        3. Relative velocity (15%) — vs category peers
        4. Health (15%) — sustainable growth?
        5. Star velocity (15%) — raw star acquisition rate
        6. Fork velocity (10%) — developer adoption
        """
        velocity = repo.get("velocity", 0)
        acceleration = repo.get("star_growth_acceleration", 1.0)
        health = repo.get("health", 0)
        rate_7d = repo.get("star_growth_rate_7d", 0)
        forks_7d = repo.get("forks_7d", 0)
        category = repo.get("category", "Unknown")

        # 1. Velocity score (0-100)
        velocity_score = min(100, velocity)

        # 2. Acceleration score (0-100)
        # 1.0 = normal, 2.0 = 2x acceleration, 0.5 = decelerating
        accel_score = min(100, max(0, (acceleration - 0.5) * 66.7))

        # 3. Relative velocity (vs category median)
        cat_median = category_medians.get(category, {}).get("velocity", 50)
        relative_velocity = velocity / cat_median if cat_median > 0 else 1
        relative_score = min(100, relative_velocity * 50)

        # 4. Health score (0-100)
        health_score = health

        # 5. Star velocity score (0-100)
        # Normalize: 10+ stars/day = high, 1 star/day = moderate
        star_velocity_score = min(100, rate_7d * 15)

        # 6. Fork velocity score (0-100)
        fork_velocity_score = min(100, forks_7d * 10)

        # Weighted composite
        breakout = (
            velocity_score * 0.25
            + accel_score * 0.20
            + relative_score * 0.15
            + health_score * 0.15
            + star_velocity_score * 0.15
            + fork_velocity_score * 0.10
        )

        # Bonus for young repos (they break out more dramatically)
        created_at = repo.get("created_at")
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_days = (datetime.now(tz=UTC) - created_dt).days
                if age_days < 90:
                    breakout *= 1.15  # 15% bonus for new repos
                elif age_days < 180:
                    breakout *= 1.08  # 8% bonus
            except (ValueError, AttributeError):
                pass

        return min(100, breakout)

    def get_breakout_summary(self) -> dict[str, Any]:
        """Get a summary of breakout detection results."""
        breakouts = self.detect_breakouts(25)

        return {
            "detected_at": datetime.now(tz=UTC).isoformat(),
            "total_candidates": len(breakouts),
            "candidates": breakouts,
            "top_5": breakouts[:5],
        }

    def get_breakouts_by_category(self) -> dict[str, list[dict[str, Any]]]:
        """Group breakout candidates by category."""
        breakouts = self.detect_breakouts(100)

        by_category: dict[str, list[dict]] = {}
        for b in breakouts:
            cat = b.get("category", "Unknown")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(b)

        return by_category
