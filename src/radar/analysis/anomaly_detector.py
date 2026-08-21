"""Anomaly Detection Engine — identifies unusual activity patterns.

Detects:
- Star spikes: sudden burst of stars in short period
- Fork spikes: unusual fork activity
- Score jumps: dramatic radar score changes
- Velocity anomalies: acceleration beyond normal range
- Health anomalies: sudden drops in health metrics
- Category anomalies: entire category showing unusual activity

Anomalies are scored by deviation from normal behavior.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from radar.storage.database import Database

logger = logging.getLogger(__name__)

# Anomaly thresholds
STAR_SPIKE_THRESHOLD = 3.0  # 3x normal daily rate
FORK_SPIKE_THRESHOLD = 3.0
SCORE_JUMP_THRESHOLD = 10.0  # 10+ point jump
VELOCITY_ANOMALY_THRESHOLD = 2.5  # 2.5x median velocity
HEALTH_DROP_THRESHOLD = -20.0  # 20+ point drop


class AnomalyDetector:
    """Identifies unusual activity patterns across repositories."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def detect_all(self) -> dict[str, list[dict[str, Any]]]:
        """Run all anomaly detections. Returns categorized results."""
        results = {
            "star_spikes": self.detect_star_spikes(),
            "fork_spikes": self.detect_fork_spikes(),
            "score_jumps": self.detect_score_jumps(),
            "velocity_anomalies": self.detect_velocity_anomalies(),
            "health_drops": self.detect_health_drops(),
        }

        # Add anomaly type to each result
        for key, items in results.items():
            for item in items:
                item["anomaly_type"] = key

        # Count total
        total = sum(len(v) for v in results.values())
        logger.info(f"Detected {total} anomalies across {len(results)} types")

        return results

    def detect_star_spikes(self, threshold: float = STAR_SPIKE_THRESHOLD) -> list[dict[str, Any]]:
        """Detect repos with sudden star bursts.

        Compares 7d growth rate to 30d average to find spikes.
        """
        with self.db._conn() as conn:
            # Get repos with both 7d and 30d growth data
            rows = conn.execute(
                """SELECT g.*, r.full_name, r.stars, r.language, r.url,
                          s.radar_score, s.velocity, s.health
                FROM growth_metrics g
                JOIN repositories r ON g.repo_full_name = r.full_name
                LEFT JOIN scores s ON g.repo_full_name = s.repo_full_name
                    AND s.timestamp = (SELECT MAX(timestamp) FROM scores)
                WHERE g.timestamp = (SELECT MAX(timestamp) FROM growth_metrics)
                  AND g.stars_30d > 0
                  AND r.stars >= 100"""
            ).fetchall()

        anomalies = []
        for row in rows:
            d = dict(row)
            rate_7d = d.get("star_growth_rate_7d", 0)
            rate_30d = d.get("star_growth_rate_30d", 0)

            if rate_30d <= 0:
                continue

            # Calculate deviation
            deviation = rate_7d / rate_30d if rate_30d > 0 else 0

            if deviation >= threshold:
                anomalies.append({
                    "repo_full_name": d["full_name"],
                    "stars": d["stars"],
                    "language": d.get("language"),
                    "url": d.get("url"),
                    "radar_score": d.get("radar_score"),
                    "metric": "stars",
                    "current_rate": round(rate_7d, 1),
                    "normal_rate": round(rate_30d, 1),
                    "deviation": round(deviation, 1),
                    "stars_7d": d.get("stars_7d", 0),
                    "stars_30d": d.get("stars_30d", 0),
                })

        # Sort by deviation
        anomalies.sort(key=lambda a: a["deviation"], reverse=True)
        return anomalies[:20]

    def detect_fork_spikes(self, threshold: float = FORK_SPIKE_THRESHOLD) -> list[dict[str, Any]]:
        """Detect repos with unusual fork activity."""
        with self.db._conn() as conn:
            rows = conn.execute(
                """SELECT g.*, r.full_name, r.stars, r.forks, r.language, r.url,
                          s.radar_score
                FROM growth_metrics g
                JOIN repositories r ON g.repo_full_name = r.full_name
                LEFT JOIN scores s ON g.repo_full_name = s.repo_full_name
                    AND s.timestamp = (SELECT MAX(timestamp) FROM scores)
                WHERE g.timestamp = (SELECT MAX(timestamp) FROM growth_metrics)
                  AND g.forks_30d > 0
                  AND r.forks >= 10"""
            ).fetchall()

        anomalies = []
        for row in rows:
            d = dict(row)
            forks_7d = d.get("forks_7d", 0)
            forks_30d = d.get("forks_30d", 0)

            if forks_30d <= 0:
                continue

            # Normalize to daily rate
            rate_7d = forks_7d / 7
            rate_30d = forks_30d / 30

            deviation = rate_7d / rate_30d if rate_30d > 0 else 0

            if deviation >= threshold:
                anomalies.append({
                    "repo_full_name": d["full_name"],
                    "stars": d["stars"],
                    "forks": d["forks"],
                    "language": d.get("language"),
                    "url": d.get("url"),
                    "radar_score": d.get("radar_score"),
                    "metric": "forks",
                    "current_rate": round(rate_7d, 1),
                    "normal_rate": round(rate_30d, 1),
                    "deviation": round(deviation, 1),
                    "forks_7d": forks_7d,
                    "forks_30d": forks_30d,
                })

        anomalies.sort(key=lambda a: a["deviation"], reverse=True)
        return anomalies[:15]

    def detect_score_jumps(self, threshold: float = SCORE_JUMP_THRESHOLD) -> list[dict[str, Any]]:
        """Detect repos with dramatic score changes between scoring runs."""
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
                    latest.impact as latest_impact,
                    latest.velocity as latest_velocity,
                    latest.health as latest_health,
                    r.stars, r.language, r.url
                FROM scores latest
                JOIN scores prev ON latest.repo_full_name = prev.repo_full_name
                JOIN repositories r ON latest.repo_full_name = r.full_name
                WHERE latest.timestamp = ?
                  AND prev.timestamp = ?
                  AND ABS(latest.radar_score - prev.radar_score) > ?
                ORDER BY ABS(latest.radar_score - prev.radar_score) DESC
                LIMIT 20""",
                (latest_ts, prev_ts, threshold),
            ).fetchall()

        anomalies = []
        for row in rows:
            d = dict(row)
            change = d["score_change"]

            # Determine what caused the jump
            cause = self._infer_score_cause(d)

            anomalies.append({
                "repo_full_name": d["repo_full_name"],
                "stars": d["stars"],
                "language": d.get("language"),
                "url": d.get("url"),
                "metric": "radar_score",
                "previous_score": round(d["prev_score"], 1),
                "current_score": round(d["latest_score"], 1),
                "change": round(change, 1),
                "direction": "up" if change > 0 else "down",
                "cause": cause,
                "impact": round(d.get("latest_impact", 0), 1),
                "velocity": round(d.get("latest_velocity", 0), 1),
                "health": round(d.get("latest_health", 0), 1),
            })

        return anomalies

    def detect_velocity_anomalies(
        self, threshold: float = VELOCITY_ANOMALY_THRESHOLD
    ) -> list[dict[str, Any]]:
        """Detect repos with velocity far above median."""
        with self.db._conn() as conn:
            median_row = conn.execute(
                """SELECT velocity FROM scores
                WHERE timestamp = (
                    SELECT MAX(timestamp) FROM scores)
                ORDER BY velocity LIMIT 1 OFFSET (
                    SELECT COUNT(*) / 2 FROM scores
                    WHERE timestamp = (
                        SELECT MAX(timestamp)
                        FROM scores))"""
            ).fetchone()

            if not median_row:
                return []

            median_velocity = median_row["velocity"]
            if median_velocity <= 0:
                return []

            # Find repos with velocity far above median
            rows = conn.execute(
                """SELECT s.*, r.full_name, r.stars, r.language, r.url,
                          a.category
                FROM scores s
                JOIN repositories r ON s.repo_full_name = r.full_name
                LEFT JOIN ai_analysis a ON s.repo_full_name = a.repo_full_name
                WHERE s.timestamp = (SELECT MAX(timestamp) FROM scores)
                  AND s.velocity > ?
                  AND r.stars >= 500
                ORDER BY s.velocity DESC
                LIMIT 20""",
                (median_velocity * threshold,),
            ).fetchall()

        anomalies = []
        for row in rows:
            d = dict(row)
            deviation = d["velocity"] / median_velocity

            anomalies.append({
                "repo_full_name": d["full_name"],
                "stars": d["stars"],
                "language": d.get("language"),
                "url": d.get("url"),
                "category": d.get("category"),
                "metric": "velocity",
                "velocity": round(d["velocity"], 1),
                "median_velocity": round(median_velocity, 1),
                "deviation": round(deviation, 1),
                "radar_score": round(d["radar_score"], 1),
            })

        return anomalies

    def detect_health_drops(self, threshold: float = HEALTH_DROP_THRESHOLD) -> list[dict[str, Any]]:
        """Detect repos with sudden health metric drops."""
        with self.db._conn() as conn:
            timestamps = conn.execute(
                """SELECT DISTINCT timestamp FROM scores
                ORDER BY timestamp DESC LIMIT 2"""
            ).fetchall()

            if len(timestamps) < 2:
                return []

            latest_ts = timestamps[0]["timestamp"]
            prev_ts = timestamps[1]["timestamp"]

            rows = conn.execute(
                """SELECT
                    latest.repo_full_name,
                    latest.health as latest_health,
                    prev.health as prev_health,
                    latest.health - prev.health as health_change,
                    r.stars, r.language, r.url,
                    g.days_since_last_push
                FROM scores latest
                JOIN scores prev ON latest.repo_full_name = prev.repo_full_name
                JOIN repositories r ON latest.repo_full_name = r.full_name
                LEFT JOIN growth_metrics g ON latest.repo_full_name = g.repo_full_name
                    AND g.timestamp = latest.timestamp
                WHERE latest.timestamp = ?
                  AND prev.timestamp = ?
                  AND (latest.health - prev.health) < ?
                  AND r.stars >= 1000
                ORDER BY (latest.health - prev.health) ASC
                LIMIT 15""",
                (latest_ts, prev_ts, threshold),
            ).fetchall()

        anomalies = []
        for row in rows:
            d = dict(row)

            # Infer cause
            cause = "Unknown"
            days_push = d.get("days_since_last_push", 0)
            if days_push and days_push > 90:
                cause = "Inactive (no push in 90+ days)"
            elif days_push and days_push > 30:
                cause = "Reduced activity"
            else:
                cause = "Issue/PR backlog growth"

            anomalies.append({
                "repo_full_name": d["repo_full_name"],
                "stars": d["stars"],
                "language": d.get("language"),
                "url": d.get("url"),
                "metric": "health",
                "previous_health": round(d["prev_health"], 1),
                "current_health": round(d["latest_health"], 1),
                "change": round(d["health_change"], 1),
                "days_since_last_push": days_push,
                "cause": cause,
            })

        return anomalies

    def _infer_score_cause(self, data: dict[str, Any]) -> str:
        """Infer what caused a score jump."""
        impact_change = data.get("latest_impact", 0) - data.get("prev_impact", 0)
        velocity_change = data.get("latest_velocity", 0) - data.get("prev_velocity", 0)
        health_change = data.get("latest_health", 0) - data.get("prev_health", 0)

        causes = []
        if abs(impact_change) > 5:
            causes.append("Impact " + ("surge" if impact_change > 0 else "drop"))
        if abs(velocity_change) > 5:
            causes.append("Velocity " + ("acceleration" if velocity_change > 0 else "deceleration"))
        if abs(health_change) > 5:
            causes.append("Health " + ("improvement" if health_change > 0 else "decline"))

        return ", ".join(causes) if causes else "Combined signal change"

    def get_anomaly_summary(self) -> dict[str, Any]:
        """Get a summary of all detected anomalies."""
        all_anomalies = self.detect_all()

        return {
            "detected_at": datetime.now(tz=UTC).isoformat(),
            "total_anomalies": sum(len(v) for v in all_anomalies.values()),
            "by_type": {k: len(v) for k, v in all_anomalies.items()},
            "star_spikes": all_anomalies["star_spikes"][:5],
            "fork_spikes": all_anomalies["fork_spikes"][:5],
            "score_jumps": all_anomalies["score_jumps"][:5],
            "velocity_anomalies": all_anomalies["velocity_anomalies"][:5],
            "health_drops": all_anomalies["health_drops"][:5],
        }
