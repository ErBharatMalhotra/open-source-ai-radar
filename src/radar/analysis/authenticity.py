"""Organic Growth Confidence — star authenticity heuristics.

Star counts are the most gameable signal on GitHub: bot farms, paid "star
packages" and coordinated Telegram/Discord pushes can inflate a repo into
trending within hours. Because the Radar already stores repeated snapshots plus
7d/30d growth metrics, it can look for the fingerprints that organic growth
leaves and fake growth does not:

- Developers actually build on real projects -> forks scale with stars
  (healthy AI repos sit around 8-20%; botted repos often sit under 1%).
- Star bursts come with *proportional* fork and issue activity.
- Growth compounds over weeks instead of appearing as a 6-hour cliff.
- People open issues when they use something.

Each signal is scored 0-100 and combined into an "Organic Growth Confidence"
score. Missing signals are dropped and the remaining weights are re-normalised,
so repos with thin history are not punished for missing data.

This is a heuristic, not proof. It flags patterns worth a human look; it never
claims a repository has bought stars.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from radar.storage.database import Database

logger = logging.getLogger(__name__)

MIN_STARS = 100
BURST_WINDOW = timedelta(days=1)
SNAPSHOT_LOOKBACK = timedelta(days=30)

# Verdict bands (organic_confidence, label, verdict, blurb)
VERDICTS: list[tuple[float, str, str, str]] = [
    (80.0, "High Confidence", "organic", "Growth pattern looks organic."),
    (65.0, "Moderate Confidence", "likely_organic", "Mostly organic, minor oddities."),
    (45.0, "Mixed Signals", "mixed", "Some growth signals do not line up."),
    (0.0, "Low Confidence", "suspicious", "Pattern matches known star inflation."),
]

SIGNAL_LABELS = {
    "fork_ratio": "Fork-to-star ratio",
    "burst": "Burst pattern",
    "alignment": "Star/fork velocity alignment",
    "acceleration": "Growth acceleration",
    "engagement": "Issue engagement",
    "maintenance": "Maintenance cadence",
}

SIGNAL_WEIGHTS = {
    "fork_ratio": 0.22,
    "burst": 0.24,
    "alignment": 0.18,
    "acceleration": 0.14,
    "engagement": 0.12,
    "maintenance": 0.10,
}


def _interp(value: float, points: list[tuple[float, float]]) -> float:
    """Map `value` onto 0-100 using ascending (x, score) points, clamped."""
    if value <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if value <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
    return points[-1][1]


def _parse_ts(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _num(value: float) -> str:
    return f"{value:,.0f}"


@dataclass
class Signal:
    """One scored authenticity signal."""

    key: str
    score: float | None
    weight: float
    detail: str
    available: bool = field(default=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": SIGNAL_LABELS.get(self.key, self.key),
            "score": None if self.score is None else round(self.score, 1),
            "weight": self.weight,
            "detail": self.detail,
        }


class AuthenticityScorer:
    """Computes an Organic Growth Confidence score for tracked repositories."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ── public API ──────────────────────────────────────────────────────────

    def compute(self, min_stars: int = MIN_STARS) -> list[dict[str, Any]]:
        """Score every repo with at least `min_stars` stars."""
        rows = self._fetch_repos(min_stars)
        if not rows:
            return []

        snapshots = self._fetch_snapshots({r["full_name"] for r in rows})
        results: list[dict[str, Any]] = []

        for row in rows:
            repo = dict(row)
            history = snapshots.get(repo["full_name"], [])
            signals = self._compute_signals(repo, history)
            confidence, reasons, red_flags = self._combine(signals)
            label, verdict, blurb = self._verdict(confidence)

            results.append(
                {
                    "repo_full_name": repo["full_name"],
                    "stars": repo.get("stars") or 0,
                    "forks": repo.get("forks") or 0,
                    "stars_7d": repo.get("stars_7d") or 0,
                    "fork_ratio": round(
                        (repo.get("forks") or 0) / max(repo.get("stars") or 1, 1), 4
                    ),
                    "organic_confidence": round(confidence, 1),
                    "label": label,
                    "verdict": verdict,
                    "summary": blurb,
                    "signals": [s.to_dict() for s in signals],
                    "reasons": reasons,
                    "red_flags": red_flags,
                    "computed_at": datetime.now(tz=UTC).isoformat(),
                }
            )

        results.sort(key=lambda r: r["organic_confidence"])
        logger.info("Scored organic growth confidence for %d repos", len(results))
        return results

    def save(self, results: list[dict[str, Any]]) -> int:
        """Persist scores so exports and project pages can read them."""
        if not results:
            return 0
        with self.db._conn() as conn:
            conn.execute("DELETE FROM star_authenticity")
            conn.executemany(
                """INSERT OR REPLACE INTO star_authenticity
                   (repo_full_name, timestamp, organic_confidence, verdict, label,
                    signals, reasons, red_flags)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        r["repo_full_name"],
                        r["computed_at"],
                        r["organic_confidence"],
                        r["verdict"],
                        r["label"],
                        json.dumps(r["signals"]),
                        json.dumps(r["reasons"]),
                        json.dumps(r["red_flags"]),
                    )
                    for r in results
                ],
            )
        return len(results)

    def summary(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate counts used by CLI output and the export payload."""
        buckets = {"organic": 0, "likely_organic": 0, "mixed": 0, "suspicious": 0}
        for r in results:
            buckets[r["verdict"]] = buckets.get(r["verdict"], 0) + 1

        flagged = [r for r in results if r["verdict"] in ("mixed", "suspicious")]
        flagged.sort(key=lambda r: r["organic_confidence"])

        return {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "total_scored": len(results),
            "buckets": buckets,
            "most_suspicious": flagged[:20],
            "most_organic": sorted(
                results, key=lambda r: r["organic_confidence"], reverse=True
            )[:20],
        }

    # ── data access ─────────────────────────────────────────────────────────

    def _fetch_repos(self, min_stars: int) -> list[Any]:
        with self.db._conn() as conn:
            return conn.execute(
                """SELECT r.full_name, r.stars, r.forks, r.open_issues, r.watchers,
                          r.created_at, r.pushed_at,
                          g.stars_7d, g.stars_30d, g.stars_90d,
                          g.star_growth_rate_7d, g.star_growth_rate_30d,
                          g.star_growth_acceleration,
                          g.forks_7d, g.forks_30d, g.days_since_last_push
                   FROM repositories r
                   LEFT JOIN growth_metrics g ON g.repo_full_name = r.full_name
                     AND g.timestamp = (SELECT MAX(timestamp) FROM growth_metrics)
                   WHERE r.stars >= ?
                   ORDER BY r.stars DESC""",
                (min_stars,),
            ).fetchall()

    def _fetch_snapshots(
        self, repos: set[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Recent snapshots grouped by repo, oldest first."""
        since = (datetime.now(tz=UTC) - SNAPSHOT_LOOKBACK).isoformat()
        with self.db._conn() as conn:
            rows = conn.execute(
                """SELECT repo_full_name, timestamp, stars, forks
                   FROM snapshots
                   WHERE timestamp >= ?
                   ORDER BY repo_full_name, timestamp""",
                (since,),
            ).fetchall()

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if row["repo_full_name"] not in repos:
                continue
            grouped.setdefault(row["repo_full_name"], []).append(dict(row))
        return grouped

    # ── signal computation ──────────────────────────────────────────────────

    def _compute_signals(
        self, repo: dict[str, Any], history: list[dict[str, Any]]
    ) -> list[Signal]:
        stars = repo.get("stars") or 0
        forks = repo.get("forks") or 0
        stars_7d = repo.get("stars_7d") or 0
        forks_7d = repo.get("forks_7d") or 0

        signals = [
            self._fork_ratio_signal(stars, forks),
            self._burst_signal(history, stars_7d, forks_7d),
            self._alignment_signal(stars, forks, stars_7d, forks_7d),
            self._acceleration_signal(repo.get("star_growth_acceleration")),
            self._engagement_signal(stars, repo.get("open_issues") or 0),
            self._maintenance_signal(repo.get("days_since_last_push"), repo.get("pushed_at")),
        ]
        return [s for s in signals if s is not None]

    def _fork_ratio_signal(self, stars: int, forks: int) -> Signal:
        weight = SIGNAL_WEIGHTS["fork_ratio"]
        if stars < MIN_STARS:
            return Signal("fork_ratio", None, weight, "Not enough stars to judge.", False)

        ratio = forks / stars
        score = _interp(
            ratio,
            [
                (0.0, 5),
                (0.002, 20),
                (0.005, 40),
                (0.02, 62),
                (0.05, 82),
                (0.10, 100),
                (0.35, 95),
            ],
        )
        return Signal(
            "fork_ratio",
            score,
            weight,
            f"{_num(forks)} forks for {_num(stars)} stars ({_pct(ratio)}).",
        )

    def _burst_signal(
        self, history: list[dict[str, Any]], stars_7d: int, forks_7d: int
    ) -> Signal:
        weight = SIGNAL_WEIGHTS["burst"]
        if len(history) < 2:
            return Signal("burst", None, weight, "Not enough snapshots yet.", False)

        parsed = [
            (ts, row.get("stars") or 0, row.get("forks") or 0)
            for row in history
            if (ts := _parse_ts(str(row.get("timestamp", "")))) is not None
        ]
        if len(parsed) < 2:
            return Signal("burst", None, weight, "Not enough valid snapshots.", False)

        span = parsed[-1][0] - parsed[0][0]
        if span < timedelta(hours=12):
            return Signal("burst", None, weight, "History window too short.", False)

        # Best 24h window vs the average daily rate over the whole window.
        best_stars = 0
        best_forks = 0
        for start_ts, start_stars, start_forks in parsed:
            end_ts = start_ts + BURST_WINDOW
            window = [p for p in parsed if start_ts <= p[0] <= end_ts]
            if len(window) < 2:
                continue
            delta_stars = window[-1][1] - start_stars
            delta_forks = window[-1][2] - start_forks
            if delta_stars > best_stars:
                best_stars = delta_stars
                best_forks = delta_forks

        if best_stars <= 0:
            return Signal(
                "burst",
                90.0,
                weight,
                "No single-day star surge in the last 30 days.",
            )

        days = max(span.total_seconds() / 86400, 0.5)
        baseline = max((parsed[-1][1] - parsed[0][1]) / days, 1.0)
        ratio = best_stars / baseline

        score = _interp(
            ratio,
            [(1.0, 100), (2.0, 90), (3.0, 75), (5.0, 52), (8.0, 32), (15.0, 12)],
        )

        detail = (
            f"Largest 24h jump was {_num(best_stars)} stars "
            f"({_num(best_forks)} forks, {ratio:.1f}x the daily average)."
        )

        # A big star burst with almost no forks is the classic bot signature.
        if best_stars >= 300:
            burst_ratio = best_forks / best_stars
            if best_forks <= 2:
                score -= 25
                detail += " Forks did not move at all."
            elif burst_ratio < 0.005:
                score -= 15
                detail += f" Only {_pct(burst_ratio)} of burst stars came with a fork."

        return Signal("burst", max(0.0, min(100.0, score)), weight, detail)

    def _alignment_signal(
        self, stars: int, forks: int, stars_7d: int, forks_7d: int
    ) -> Signal:
        weight = SIGNAL_WEIGHTS["alignment"]
        if stars_7d < 20:
            return Signal(
                "alignment", None, weight, "Weekly star growth too small to compare.", False
            )

        lifetime_ratio = forks / stars if stars else 0.0
        expected_forks = max(stars_7d * max(lifetime_ratio, 0.005), 1.0)
        ratio = forks_7d / expected_forks

        score = _interp(
            ratio,
            [(0.0, 5), (0.1, 20), (0.25, 40), (0.5, 65), (0.8, 88), (1.0, 100), (2.0, 95)],
        )
        return Signal(
            "alignment",
            score,
            weight,
            f"+{_num(stars_7d)} stars vs +{_num(forks_7d)} forks this week "
            f"(expected ~{_num(expected_forks)} forks).",
        )

    def _acceleration_signal(self, acceleration: float | None) -> Signal:
        weight = SIGNAL_WEIGHTS["acceleration"]
        if acceleration is None or acceleration <= 0:
            return Signal("acceleration", None, weight, "No acceleration data.", False)

        score = _interp(
            acceleration,
            [(0.0, 100), (1.0, 95), (1.5, 85), (2.0, 70), (3.0, 50), (5.0, 30), (10.0, 10)],
        )
        return Signal(
            "acceleration",
            score,
            weight,
            f"Weekly growth is {acceleration:.2f}x the monthly baseline.",
        )

    def _engagement_signal(self, stars: int, open_issues: int) -> Signal:
        weight = SIGNAL_WEIGHTS["engagement"]
        if stars < MIN_STARS:
            return Signal("engagement", None, weight, "Not enough stars to judge.", False)

        ratio = open_issues / stars
        score = _interp(
            ratio,
            [(0.0, 25), (0.002, 45), (0.005, 60), (0.01, 75), (0.02, 90), (0.05, 100)],
        )
        return Signal(
            "engagement",
            score,
            weight,
            f"{_num(open_issues)} open issues for {_num(stars)} stars ({_pct(ratio)}).",
        )

    def _maintenance_signal(
        self, days_since_push: Any, pushed_at: str | None
    ) -> Signal:
        weight = SIGNAL_WEIGHTS["maintenance"]
        days = days_since_push
        if days is None and pushed_at:
            pushed = _parse_ts(str(pushed_at))
            if pushed:
                days = (datetime.now(tz=UTC) - pushed).days
        if days is None:
            return Signal("maintenance", None, weight, "No push data.", False)

        days = float(days)
        score = _interp(
            days, [(0.0, 100), (7.0, 95), (30.0, 85), (90.0, 70), (180.0, 45), (365.0, 25)]
        )
        return Signal(
            "maintenance",
            score,
            weight,
            f"Last push {days:.0f} days ago.",
        )

    # ── combination ─────────────────────────────────────────────────────────

    def _combine(self, signals: list[Signal]) -> tuple[float, list[str], list[str]]:
        available = [s for s in signals if s.score is not None]
        if not available:
            return 50.0, ["Not enough data to judge growth quality."], []

        total_weight = sum(s.weight for s in available)
        confidence = sum(s.score * s.weight for s in available if s.score is not None)
        confidence = confidence / total_weight if total_weight else 50.0

        reasons: list[str] = []
        red_flags: list[str] = []
        for signal in sorted(available, key=lambda s: s.score or 0):
            score = signal.score or 0
            if score < 40:
                red_flags.append(f"{SIGNAL_LABELS[signal.key]}: {signal.detail}")
            elif score >= 75 and len(reasons) < 3:
                reasons.append(f"{SIGNAL_LABELS[signal.key]}: {signal.detail}")

        return max(0.0, min(100.0, confidence)), reasons, red_flags

    def _verdict(self, confidence: float) -> tuple[str, str, str]:
        for threshold, label, verdict, blurb in VERDICTS:
            if confidence >= threshold:
                return label, verdict, blurb
        return VERDICTS[-1][1], VERDICTS[-1][2], VERDICTS[-1][3]
