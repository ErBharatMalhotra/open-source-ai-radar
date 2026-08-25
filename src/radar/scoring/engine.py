"""Three-axis scoring engine for Open Source AI Radar.

Scoring Model:
  Impact (40%)  — How important is this project RIGHT NOW?
  Velocity (35%) — Is this project ACCELERATING?
  Health (25%)  — Is this project SUSTAINABLE?

Each axis is 0-100, computed from raw signals.
Radar Score = impact * 0.40 + velocity * 0.35 + health * 0.25

Without snapshot history, we use proxy signals from repo metadata
to estimate velocity and health. As snapshots accumulate, the engine
switches to real growth data automatically.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import Any, ClassVar

from radar.storage.database import Database

logger = logging.getLogger(__name__)

WEIGHTS = {
    "impact": 0.40,
    "velocity": 0.35,
    "health": 0.25,
}

FRESHNESS_LAMBDA = 0.015


def _percentile_rank(value: float, sorted_values: list[float]) -> float:
    """Percentile rank. sorted_values MUST be pre-sorted ascending."""
    n = len(sorted_values)
    if n == 0:
        return 0.0
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_values[mid] < value:
            lo = mid + 1
        else:
            hi = mid
    return (lo / n) * 100


def _log_scale(value: float) -> float:
    if value <= 0:
        return 0.0
    return math.log(value + 1)


def _days_since(iso_str: str | None) -> int:
    if not iso_str:
        return 9999
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(tz=UTC) - dt).days
    except (ValueError, AttributeError):
        return 9999


class ScoringEngine:
    def __init__(self, db: Database, weights: dict[str, float] | None = None) -> None:
        self.db = db
        self.weights = weights or WEIGHTS

    def compute_all_scores(self, timestamp: str | None = None) -> int:
        repos = self.db.get_all_repos()
        if not repos:
            logger.warning("No repos to score")
            return 0

        ts = timestamp or datetime.now(tz=UTC).isoformat()

        # ═══ Pre-compute ALL percentile arrays ONCE ═══
        all_stars_log = sorted(_log_scale(float(r.get("stars", 0))) for r in repos)
        all_forks_log = sorted(_log_scale(float(r.get("forks", 0))) for r in repos)
        all_watchers = sorted(float(r.get("watchers", 0)) for r in repos)
        all_issues = sorted(float(r.get("open_issues", 0)) for r in repos)

        # Pre-compute freshness per repo
        freshness_map: dict[str, float] = {}
        for r in repos:
            days = _days_since(r.get("pushed_at"))
            freshness_map[r["full_name"]] = math.exp(-FRESHNESS_LAMBDA * days)

        # Bus factor: latest known contributor counts (empty until
        # snapshots accumulate — scored conservatively as 0)
        try:
            contributors_map = self.db.get_latest_contributors()
        except Exception:
            logger.warning("Could not load contributor counts for bus factor")
            contributors_map = {}

        # ═══ Score each repo (batch insert) ═══
        score_batch: list[dict[str, Any]] = []
        for repo in repos:
            fn = repo["full_name"]
            stars = float(repo.get("stars", 0))
            forks = float(repo.get("forks", 0))
            watchers = float(repo.get("watchers", 0))

            impact = self._impact(
                stars, forks, watchers,
                all_stars_log, all_forks_log, all_watchers
            )
            velocity = self._velocity(repo, all_issues)
            health = self._health(
                repo, freshness_map[fn], contributors_map.get(fn, 0)
            )

            radar = (
                impact * self.weights["impact"]
                + velocity * self.weights["velocity"]
                + health * self.weights["health"]
            )

            score_batch.append({
                "repo_full_name": fn,
                "timestamp": ts,
                "impact": round(impact, 2),
                "velocity": round(velocity, 2),
                "health": round(health, 2),
                "radar_score": round(radar, 2),
                "global_percentile": 0.0,
                "category_percentile": 0.0,
            })

        # Batch insert all scores in one transaction
        self.db.save_scores_batch(score_batch)
        scored = len(score_batch)

        # ═══ Percentile pass ═══
        self._compute_percentiles(ts)

        logger.info(f"Scored {scored} repositories in {ts}")
        return scored

    # ── Impact ──────────────────────────────────────────────────────

    def _impact(
        self,
        stars: float,
        forks: float,
        watchers: float,
        sorted_stars_log: list[float],
        sorted_forks_log: list[float],
        sorted_watchers: list[float],
    ) -> float:
        stars_pct = _percentile_rank(_log_scale(stars), sorted_stars_log)
        forks_pct = _percentile_rank(_log_scale(forks), sorted_forks_log)
        watchers_pct = _percentile_rank(watchers, sorted_watchers)
        return stars_pct * 0.55 + forks_pct * 0.25 + watchers_pct * 0.20

    # ── Velocity ────────────────────────────────────────────────────

    def _velocity(self, repo: dict[str, Any], sorted_issues: list[float]) -> float:
        created_days = max(_days_since(repo.get("created_at")), 1)
        stars = repo.get("stars", 0)
        forks = repo.get("forks", 0)
        open_issues = repo.get("open_issues", 0)

        stars_per_day = stars / created_days
        fork_ratio = forks / max(stars, 1)

        # Recency: young + popular = explosive
        if created_days < 30:
            recency = 3.0
        elif created_days < 90:
            recency = 2.0
        elif created_days < 365:
            recency = 1.2
        else:
            recency = 0.7

        spd_score = min(100.0, _log_scale(stars_per_day + 1) * 30)
        fork_score = min(100.0, fork_ratio * 150)
        recency_score = min(100.0, recency * 35)
        commit_score = self._commit_recency(repo)
        issue_pct = _percentile_rank(float(open_issues), sorted_issues) if sorted_issues else 50.0

        return (
            spd_score * 0.30
            + fork_score * 0.20
            + recency_score * 0.20
            + commit_score * 0.15
            + issue_pct * 0.15
        )

    def _commit_recency(self, repo: dict[str, Any]) -> float:
        days = _days_since(repo.get("pushed_at"))
        if days <= 1:
            return 95.0
        elif days <= 3:
            return 85.0
        elif days <= 7:
            return 70.0
        elif days <= 14:
            return 55.0
        elif days <= 30:
            return 40.0
        elif days <= 90:
            return 20.0
        elif days <= 180:
            return 8.0
        return 2.0

    # ── Health ──────────────────────────────────────────────────────

    #: SPDX license identifiers considered safe for adopters (OSI-approved
    #: or widely-accepted). Anything unrecognized scores mid; missing
    #: licenses score low.
    SAFE_LICENSES: ClassVar[set[str]] = {
        "MIT", "Apache-2.0", "Apache-2.0 WITH LLVM-exception", "BSD-2-Clause",
        "BSD-3-Clause", "BSD-3-Clause-Clear", "ISC", "MPL-2.0", "Unlicense",
        "CC0-1.0", "CC-BY-4.0", "Zlib", "0BSD", "BSL-1.0",
        "GPL-2.0", "GPL-2.0-only", "GPL-2.0-or-later",
        "GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later",
        "LGPL-2.1", "LGPL-2.1-only", "LGPL-2.1-or-later",
        "LGPL-3.0", "LGPL-3.0-only", "LGPL-3.0-or-later",
        "AGPL-3.0", "AGPL-3.0-only", "AGPL-3.0-or-later",
        "EPL-1.0", "EPL-2.0", "CDDL-1.0", "CECILL-2.1", "EUPL-1.2",
    }

    def _bus_factor_score(self, contributors: int) -> float:
        """Score maintainer risk: how many people could keep this alive?"""
        if contributors >= 25:
            return 95.0
        if contributors >= 10:
            return 85.0
        if contributors >= 5:
            return 70.0
        if contributors >= 2:
            return 50.0
        return 20.0

    def _license_score(self, repo: dict[str, Any]) -> float:
        """Score legal safety: can adopters actually use this project?"""
        license_id = (repo.get("license") or "").strip()
        if not license_id:
            return 30.0
        return 90.0 if license_id in self.SAFE_LICENSES else 60.0

    def _health(
        self,
        repo: dict[str, Any],
        freshness: float,
        bus_factor: int = 0,
    ) -> float:
        freshness_score = freshness * 100

        has_release = bool(repo.get("latest_release_tag"))
        release_score = 85.0 if has_release else 20.0

        release_days = _days_since(repo.get("latest_release_date"))
        if release_days <= 30:
            release_recency = 90.0
        elif release_days <= 90:
            release_recency = 60.0
        elif release_days <= 180:
            release_recency = 30.0
        else:
            release_recency = 10.0

        open_issues = repo.get("open_issues", 0)
        stars = max(repo.get("stars", 1), 1)
        issue_ratio = open_issues / stars
        if issue_ratio < 0.001:
            issue_health = 40.0
        elif issue_ratio < 0.05:
            issue_health = 85.0
        elif issue_ratio < 0.15:
            issue_health = 55.0
        else:
            issue_health = 25.0

        forks = repo.get("forks", 0)
        fork_ratio = forks / stars
        if 0.05 <= fork_ratio <= 0.25:
            community_health = 85.0
        elif fork_ratio < 0.05:
            community_health = 50.0
        else:
            community_health = 65.0

        bus_factor_component = self._bus_factor_score(bus_factor)
        license_component = self._license_score(repo)

        return (
            freshness_score * 0.25
            + release_score * 0.10
            + release_recency * 0.10
            + issue_health * 0.12
            + community_health * 0.13
            + (100.0 if has_release else 50.0) * 0.05
            + bus_factor_component * 0.15
            + license_component * 0.10
        )

    # ── Percentiles ─────────────────────────────────────────────────

    def _compute_percentiles(self, ts: str) -> None:
        with self.db._conn() as conn:
            rows = conn.execute(
                "SELECT repo_full_name, radar_score FROM scores WHERE timestamp = ?",
                (ts,),
            ).fetchall()
            if not rows:
                return

            scores = [(r["repo_full_name"], r["radar_score"]) for r in rows]
            all_radars = sorted(s for _, s in scores)

            for full_name, radar in scores:
                pct = _percentile_rank(radar, all_radars)
                conn.execute(
                    "UPDATE scores SET global_percentile = ? "
                    "WHERE repo_full_name = ? AND timestamp = ?",
                    (round(pct, 2), full_name, ts),
                )

            logger.info(f"Computed percentiles for {len(scores)} repos")

    def compute_incremental_scores(
        self,
        repo_names: list[str],
        timestamp: str | None = None,
    ) -> int:
        """Score only specific repos (incremental mode).

        Still needs the full dataset for percentile computation,
        but only recalculates scores for the given repos.

        Args:
            repo_names: List of full_names to rescore
            timestamp: Optional timestamp

        Returns:
            Number of repos scored
        """
        if not repo_names:
            return 0

        ts = timestamp or datetime.now(tz=UTC).isoformat()

        # Get ALL repos for percentile computation
        all_repos = self.db.get_all_repos()
        if not all_repos:
            logger.warning("No repos to score")
            return 0

        # Pre-compute percentile arrays (same as full score)
        all_stars_log = sorted(_log_scale(float(r.get("stars", 0))) for r in all_repos)
        all_forks_log = sorted(_log_scale(float(r.get("forks", 0))) for r in all_repos)
        all_watchers = sorted(float(r.get("watchers", 0)) for r in all_repos)
        all_issues = sorted(float(r.get("open_issues", 0)) for r in all_repos)

        freshness_map: dict[str, float] = {}
        for r in all_repos:
            days = _days_since(r.get("pushed_at"))
            freshness_map[r["full_name"]] = math.exp(-FRESHNESS_LAMBDA * days)

        # Build lookup for repos to score
        repo_lookup = {r["full_name"]: r for r in all_repos}

        score_batch: list[dict[str, Any]] = []
        for fn in repo_names:
            repo = repo_lookup.get(fn)
            if not repo:
                continue

            stars = float(repo.get("stars", 0))
            forks = float(repo.get("forks", 0))
            watchers = float(repo.get("watchers", 0))

            impact = self._impact(
                stars, forks, watchers,
                all_stars_log, all_forks_log, all_watchers
            )
            velocity = self._velocity(repo, all_issues)
            health = self._health(repo, freshness_map.get(fn, 0.5))

            radar = (
                impact * self.weights["impact"]
                + velocity * self.weights["velocity"]
                + health * self.weights["health"]
            )

            score_batch.append({
                "repo_full_name": fn,
                "timestamp": ts,
                "impact": round(impact, 2),
                "velocity": round(velocity, 2),
                "health": round(health, 2),
                "radar_score": round(radar, 2),
                "global_percentile": 0.0,
                "category_percentile": 0.0,
            })

        self.db.save_scores_batch(score_batch)

        # Recompute percentiles for all repos (needed for accurate rankings)
        self._compute_percentiles(ts)

        logger.info(f"Incrementally scored {len(score_batch)} repos in {ts}")
        return len(score_batch)

    def get_rankings(self, n: int = 50, sort_by: str = "radar_score") -> list[dict[str, Any]]:
        return self.db.get_top_repos(n, sort_by)
