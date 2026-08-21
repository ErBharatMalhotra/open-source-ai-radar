"""Why Trending Analyzer — explains why repositories are gaining attention.

Combines multiple signals to generate human-readable explanations:
- Star growth rate and acceleration
- Fork activity
- Release cadence
- Contributor growth
- Anomaly detection results
- Category momentum
- External mentions (future)

Output is stored in the database and displayed on project pages.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from radar.storage.database import Database

logger = logging.getLogger(__name__)


class WhyTrendingAnalyzer:
    """Generates 'why is this trending?' explanations for repositories."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def analyze_repo(self, full_name: str) -> dict[str, Any] | None:
        """Generate a 'why trending' explanation for a single repo.

        Returns:
            Dict with explanation, signals, and confidence.
        """
        # Gather all signals
        signals = self._gather_signals(full_name)
        if not signals:
            return None

        # Generate explanation
        explanation = self._generate_explanation(signals)

        # Calculate confidence
        confidence = self._calculate_confidence(signals)

        return {
            "repo_full_name": full_name,
            "explanation": explanation,
            "signals": signals,
            "confidence": confidence,
            "analyzed_at": datetime.now(tz=UTC).isoformat(),
        }

    def analyze_all_trending(self, limit: int = 50) -> list[dict[str, Any]]:
        """Analyze why top trending repos are trending.

        Args:
            limit: Max repos to analyze

        Returns:
            List of analysis results
        """
        # Get top repos by velocity (most likely to be trending)
        with self.db._conn() as conn:
            rows = conn.execute(
                """SELECT s.repo_full_name, s.velocity, s.radar_score
                FROM scores s
                WHERE s.timestamp = (SELECT MAX(timestamp) FROM scores)
                ORDER BY s.velocity DESC
                LIMIT ?""",
                (limit,),
            ).fetchall()

        results = []
        for row in rows:
            fn = row["repo_full_name"]
            analysis = self.analyze_repo(fn)
            if analysis:
                results.append(analysis)

        logger.info(f"Analyzed {len(results)} trending repos")
        return results

    def _gather_signals(self, full_name: str) -> dict[str, Any]:
        """Gather all relevant signals for explanation generation."""
        signals = {}

        # Get repo data
        repo = self.db.get_repo(full_name)
        if not repo:
            return {}

        signals["stars"] = repo.get("stars", 0)
        signals["forks"] = repo.get("forks", 0)
        signals["language"] = repo.get("language")
        signals["description"] = repo.get("description", "")[:200]

        # Get latest score
        with self.db._conn() as conn:
            score_row = conn.execute(
                """SELECT * FROM scores WHERE repo_full_name = ?
                ORDER BY timestamp DESC LIMIT 1""",
                (full_name,),
            ).fetchone()

        if score_row:
            signals["radar_score"] = score_row["radar_score"]
            signals["impact"] = score_row["impact"]
            signals["velocity"] = score_row["velocity"]
            signals["health"] = score_row["health"]

        # Get growth metrics
        with self.db._conn() as conn:
            growth_row = conn.execute(
                """SELECT * FROM growth_metrics WHERE repo_full_name = ?
                ORDER BY timestamp DESC LIMIT 1""",
                (full_name,),
            ).fetchone()

        if growth_row:
            signals["stars_7d"] = growth_row["stars_7d"]
            signals["stars_30d"] = growth_row["stars_30d"]
            signals["stars_90d"] = growth_row["stars_90d"]
            signals["star_growth_rate_7d"] = growth_row["star_growth_rate_7d"]
            signals["star_growth_rate_30d"] = growth_row["star_growth_rate_30d"]
            signals["star_growth_acceleration"] = growth_row["star_growth_acceleration"]
            signals["forks_7d"] = growth_row["forks_7d"]
            signals["forks_30d"] = growth_row["forks_30d"]
            signals["freshness_score"] = growth_row["freshness_score"]

        # Get analysis
        with self.db._conn() as conn:
            analysis_row = conn.execute(
                """SELECT * FROM ai_analysis WHERE repo_full_name = ?
                ORDER BY timestamp DESC LIMIT 1""",
                (full_name,),
            ).fetchone()

        if analysis_row:
            signals["category"] = analysis_row["category"]
            signals["maturity"] = analysis_row["maturity"]

        # Check for recent anomalies
        signals["has_star_spike"] = self._check_star_spike(full_name)
        signals["has_fork_spike"] = self._check_fork_spike(full_name)

        return signals

    def _check_star_spike(self, full_name: str) -> bool:
        """Check if repo has a recent star spike."""
        with self.db._conn() as conn:
            row = conn.execute(
                """SELECT star_growth_rate_7d, star_growth_rate_30d
                FROM growth_metrics WHERE repo_full_name = ?
                ORDER BY timestamp DESC LIMIT 1""",
                (full_name,),
            ).fetchone()

        if not row:
            return False

        rate_7d = row["star_growth_rate_7d"] or 0
        rate_30d = row["star_growth_rate_30d"] or 0

        return rate_30d > 0 and rate_7d / rate_30d >= 3.0

    def _check_fork_spike(self, full_name: str) -> bool:
        """Check if repo has a recent fork spike."""
        with self.db._conn() as conn:
            row = conn.execute(
                """SELECT forks_7d, forks_30d
                FROM growth_metrics WHERE repo_full_name = ?
                ORDER BY timestamp DESC LIMIT 1""",
                (full_name,),
            ).fetchone()

        if not row:
            return False

        forks_7d = row["forks_7d"] or 0
        forks_30d = row["forks_30d"] or 0

        if forks_30d <= 0:
            return False

        return (forks_7d / 7) / (forks_30d / 30) >= 3.0

    def _generate_explanation(self, signals: dict[str, Any]) -> str:
        """Generate a human-readable explanation from signals."""
        parts = []

        velocity = signals.get("velocity", 0)
        stars_7d = signals.get("stars_7d", 0)
        acceleration = signals.get("star_growth_acceleration", 1.0)
        health = signals.get("health", 0)
        category = signals.get("category", "")

        # Star growth explanation
        if stars_7d > 0:
            if acceleration and acceleration > 1.5:
                parts.append(
                    f"Rapidly gaining stars — {stars_7d} new stars in the last 7 days "
                    f"({acceleration:.1f}x the usual pace)"
                )
            elif stars_7d >= 100:
                parts.append(f"Strong momentum with {stars_7d} new stars this week")
            elif stars_7d >= 20:
                parts.append(f"Steady growth with {stars_7d} new stars this week")

        # Velocity explanation
        if velocity >= 80:
            parts.append("Among the fastest-growing projects in its category")
        elif velocity >= 60:
            parts.append("Above-average growth velocity")

        # Fork activity
        forks_7d = signals.get("forks_7d", 0)
        if forks_7d > 10:
            parts.append(f"High developer adoption with {forks_7d} new forks this week")

        # Health
        if health >= 70:
            parts.append("Well-maintained with active development")
        elif health < 30:
            parts.append("⚠️ Declining health metrics — may need attention")

        # Star spike
        if signals.get("has_star_spike"):
            parts.append("🚨 Unusual star activity detected — possible viral moment")

        # Category context
        if category:
            parts.append(f"Active in the {category} category")

        # Maturity
        maturity = signals.get("maturity", "")
        if maturity == "Emerging":
            parts.append("New and emerging project")
        elif maturity == "Mature":
            parts.append("Established project with proven track record")

        # Fallback if no signals generated
        if not parts:
            stars = signals.get("stars", 0)
            if stars > 10000:
                parts.append("Popular project with significant community interest")
            elif stars > 1000:
                parts.append("Growing project gaining traction")
            else:
                parts.append("Project showing positive momentum")

        return ". ".join(parts) + "."

    def _calculate_confidence(self, signals: dict[str, Any]) -> float:
        """Calculate confidence in the explanation (0-1)."""
        confidence = 0.5  # Base

        # More data = higher confidence
        if signals.get("stars_7d") is not None:
            confidence += 0.1
        if signals.get("star_growth_rate_7d") is not None:
            confidence += 0.1
        if signals.get("category"):
            confidence += 0.1
        if signals.get("radar_score"):
            confidence += 0.1
        if signals.get("has_star_spike") or signals.get("has_fork_spike"):
            confidence += 0.1

        return min(1.0, confidence)

    def save_why_trending(self, full_name: str, analysis: dict[str, Any]) -> None:
        """Save why_trending analysis to the database."""
        with self.db._conn() as conn:
            # Update ai_analysis with why_trending
            conn.execute(
                """UPDATE ai_analysis SET
                    summary = CASE WHEN summary = '' THEN ? ELSE summary END
                WHERE repo_full_name = ?""",
                (analysis["explanation"], full_name),
            )

    def get_why_trending_batch(
        self, repo_names: list[str]
    ) -> dict[str, str]:
        """Get why_trending explanations for multiple repos.

        Returns:
            Dict of {full_name: explanation}
        """
        results = {}
        for fn in repo_names:
            analysis = self.analyze_repo(fn)
            if analysis:
                results[fn] = analysis["explanation"]
        return results
