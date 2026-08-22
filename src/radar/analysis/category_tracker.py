"""Category Intelligence Tracker — ecosystem-level momentum analysis.

Tracks how AI categories are evolving over time:
- Which categories are growing fastest
- New projects per category
- Average velocity/health per category
- Category momentum scores
- Trend detection (rising, stable, declining)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from radar.storage.database import Database

logger = logging.getLogger(__name__)


class CategoryTracker:
    """Computes and tracks momentum for AI categories."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def compute_momentum(self, timestamp: str | None = None) -> list[dict[str, Any]]:
        """Compute momentum for all categories.

        Returns:
            List of category momentum dicts.
        """
        ts = timestamp or datetime.now(tz=UTC).isoformat()

        # Get all repos with their categories and scores
        with self.db._conn() as conn:
            # Get repos with categories
            repos = conn.execute(
                """SELECT r.full_name, r.stars, r.forks, r.created_at, r.pushed_at,
                          a.category, a.sub_category
                FROM repositories r
                JOIN ai_analysis a ON r.full_name = a.repo_full_name
                WHERE a.category != ''"""
            ).fetchall()

            if not repos:
                logger.warning("No categorized repos found")
                return []

            # Get latest scores — use the most recent timestamp with enough repos
            # (avoids using a tiny test batch as the "latest")
            score_rows = conn.execute(
                """SELECT repo_full_name, velocity, health, radar_score
                FROM scores WHERE timestamp = (
                    SELECT timestamp FROM scores
                    GROUP BY timestamp
                    HAVING COUNT(*) > 100
                    ORDER BY timestamp DESC LIMIT 1
                )"""
            ).fetchall()
            score_map = {r["repo_full_name"]: dict(r) for r in score_rows}

            # Get growth metrics — use latest timestamp with sufficient data
            growth_rows = conn.execute(
                """SELECT repo_full_name, stars_7d, stars_30d, star_growth_rate_7d
                FROM growth_metrics WHERE timestamp = (
                    SELECT timestamp FROM growth_metrics
                    GROUP BY timestamp
                    HAVING COUNT(*) > 100
                    ORDER BY timestamp DESC LIMIT 1
                )"""
            ).fetchall()
            growth_map = {r["repo_full_name"]: dict(r) for r in growth_rows}

        # Group repos by category
        categories: dict[str, list[dict]] = {}
        for repo in repos:
            cat = repo["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(dict(repo))

        # Compute momentum for each category
        momentums = []
        now = datetime.now(tz=UTC)

        for cat, cat_repos in categories.items():
            total_tracked = len(cat_repos)
            total_stars = sum(r.get("stars", 0) for r in cat_repos)

            # Count new repos (discovered in last 30 days)
            new_count = 0
            for r in cat_repos:
                if r.get("discovered_at"):
                    try:
                        disc_dt = datetime.fromisoformat(
                            r["discovered_at"].replace("Z", "+00:00")
                        )
                        if (now - disc_dt).days <= 30:
                            new_count += 1
                    except (ValueError, AttributeError):
                        pass

            # Compute averages
            velocities = []
            healths = []
            growth_rates = []
            stars_list = []

            for r in cat_repos:
                fn = r["full_name"]
                if fn in score_map:
                    velocities.append(score_map[fn].get("velocity", 0))
                    healths.append(score_map[fn].get("health", 0))
                if fn in growth_map:
                    gr = growth_map[fn].get("star_growth_rate_7d", 0)
                    if gr > 0:
                        growth_rates.append(gr)
                stars_list.append(r.get("stars", 0))

            avg_stars = sum(stars_list) / len(stars_list) if stars_list else 0
            avg_velocity = sum(velocities) / len(velocities) if velocities else 0
            avg_health = sum(healths) / len(healths) if healths else 0
            avg_growth = sum(growth_rates) / len(growth_rates) if growth_rates else 0

            # Find top project
            top_project = ""
            if cat_repos:
                top_repo = max(cat_repos, key=lambda r: r.get("stars", 0))
                top_project = top_repo["full_name"]

            # Compute momentum score (composite)
            momentum_score = self._compute_momentum_score(
                total_tracked=total_tracked,
                new_count=new_count,
                avg_velocity=avg_velocity,
                avg_health=avg_health,
                avg_growth=avg_growth,
            )

            # Determine trend
            trend = self._determine_trend(cat, momentum_score)

            momentum = {
                "category": cat,
                "timestamp": ts,
                "total_tracked": total_tracked,
                "new_this_period": new_count,
                "avg_stars": round(avg_stars, 0),
                "avg_growth_rate": round(avg_growth, 2),
                "avg_velocity": round(avg_velocity, 1),
                "avg_health": round(avg_health, 1),
                "total_stars": total_stars,
                "top_project": top_project,
                "momentum_score": round(momentum_score, 1),
                "trend": trend,
            }
            momentums.append(momentum)

        # Sort by momentum score
        momentums.sort(key=lambda m: m["momentum_score"], reverse=True)

        # Save to database
        self.db.save_category_momentum_batch(momentums)

        logger.info(f"Computed momentum for {len(momentums)} categories")
        return momentums

    def _compute_momentum_score(
        self,
        total_tracked: int,
        new_count: int,
        avg_velocity: float,
        avg_health: float,
        avg_growth: float,
    ) -> float:
        """Compute a composite momentum score for a category.

        Factors:
        - Velocity (how fast repos in this category are growing)
        - New projects (discovery rate)
        - Growth rate (star acquisition)
        - Health (sustainability)
        - Scale (total tracked — bigger categories get slight boost)
        """
        # Normalize components
        velocity_score = min(100, avg_velocity)
        growth_score = min(100, avg_growth * 20)  # Scale up
        health_score = avg_health

        # New projects ratio (normalized)
        new_ratio = min(1.0, new_count / max(total_tracked * 0.1, 1))
        discovery_score = new_ratio * 100

        # Scale factor (log scale to prevent mega-categories from dominating)
        import math
        scale_factor = min(1.0, math.log(total_tracked + 1) / math.log(100))

        # Weighted composite
        momentum = (
            velocity_score * 0.35
            + growth_score * 0.25
            + health_score * 0.15
            + discovery_score * 0.15
            + scale_factor * 100 * 0.10
        )

        return momentum

    def _determine_trend(self, category: str, current_score: float) -> str:
        """Determine trend by comparing current momentum_score to previous."""
        history = self.db.get_category_momentum_history(category, limit=2)

        if len(history) < 2:
            return "new"

        # Compare momentum_score to previous momentum_score (not avg_velocity)
        prev_score = history[1].get("momentum_score", 0)
        if prev_score == 0:
            # First real comparison — use avg_velocity as fallback
            prev_score = history[1].get("avg_velocity", 0)

        diff = current_score - prev_score

        if diff > 10:
            return "rising"
        elif diff < -10:
            return "declining"
        else:
            return "stable"

    def get_category_rankings(self) -> list[dict[str, Any]]:
        """Get latest category rankings by momentum score."""
        with self.db._conn() as conn:
            rows = conn.execute(
                """SELECT cm.* FROM category_momentum cm
                INNER JOIN (
                    SELECT category, MAX(timestamp) as max_ts
                    FROM category_momentum
                    GROUP BY category
                ) latest ON cm.category = latest.category
                    AND cm.timestamp = latest.max_ts
                ORDER BY cm.avg_velocity DESC"""
            ).fetchall()
            return [dict(r) for r in rows]

    def get_category_comparison(self) -> list[dict[str, Any]]:
        """Compare categories across key metrics."""
        rankings = self.get_category_rankings()

        return [
            {
                "category": r["category"],
                "tracked": r["total_tracked"],
                "new": r["new_this_period"],
                "avg_stars": r["avg_stars"],
                "velocity": r["avg_velocity"],
                "health": r["avg_health"],
                "momentum": r.get("momentum_score", 0),
                "trend": r["trend"],
                "top_project": r["top_project"],
            }
            for r in rankings
        ]

    def get_trending_categories(self, n: int = 5) -> list[dict[str, Any]]:
        """Get the fastest-rising categories."""
        rankings = self.get_category_rankings()
        return [
            r for r in rankings
            if r["trend"] in ("rising", "new")
        ][:n]

    def get_declining_categories(self, n: int = 5) -> list[dict[str, Any]]:
        """Get categories that are losing momentum."""
        rankings = self.get_category_rankings()
        return [
            r for r in rankings
            if r["trend"] == "declining"
        ][:n]
