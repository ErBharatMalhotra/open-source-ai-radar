"""Tests for breakout detection.

Regression guard: `detect_breakouts()` used to hand raw `sqlite3.Row` objects to
`_compute_category_medians()` / `_compute_breakout_score()`, which call `.get()`.
Rows have no `.get()`, so every scheduled run raised
    AttributeError: 'sqlite3.Row' object has no attribute 'get'
and `data/exports/breakouts.json` was always empty.
"""

from __future__ import annotations

import pytest

from radar.analysis.breakout_detector import BreakoutDetector

NOW = "2026-11-03T00:00:00+00:00"


@pytest.fixture
def db(tmp_path):
    from radar.storage.database import Database

    return Database(str(tmp_path / "breakout.db"))


def _seed(db, full_name="acme/rocket", *, with_growth=True, category="LLM Frameworks"):
    with db._conn() as conn:
        conn.execute(
            """INSERT INTO repositories
               (full_name, url, stars, forks, language, created_at, pushed_at)
               VALUES (?, 'https://github.com/x', 4200, 380, 'Python', ?, ?)""",
            (full_name, NOW, NOW),
        )
        conn.execute(
            """INSERT INTO scores
               (repo_full_name, timestamp, impact, velocity, health, radar_score)
               VALUES (?, ?, 70, 90, 90, 82)""",
            (full_name, NOW),
        )
        if with_growth:
            conn.execute(
                """INSERT INTO growth_metrics
                   (repo_full_name, timestamp, stars_7d, stars_30d, stars_90d,
                    star_growth_rate_7d, star_growth_rate_30d,
                    star_growth_acceleration, forks_7d, forks_30d, freshness_score)
                   VALUES (?, ?, 42, 180, 400, 6.0, 6.0, 2.0, 5, 20, 0.9)""",
                (full_name, NOW),
            )
        conn.execute(
            """INSERT INTO ai_analysis (repo_full_name, timestamp, category)
               VALUES (?, ?, ?)""",
            (full_name, NOW, category),
        )


class TestBreakoutDetector:
    def test_detects_candidate_from_sqlite_rows(self, db):
        """Rows with growth data must produce candidates, not an AttributeError."""
        _seed(db)
        candidates = BreakoutDetector(db).detect_breakouts(limit=10)

        assert len(candidates) == 1
        c = candidates[0]
        assert c["repo_full_name"] == "acme/rocket"
        assert c["category"] == "LLM Frameworks"
        assert c["breakout_score"] >= 40
        assert c["velocity"] == 90.0
        assert c["forks_7d"] == 5
        assert c["freshness"] == 90.0  # freshness_score * 100, rounded

    def test_ignores_repos_without_growth_metrics(self, db):
        _seed(db, with_growth=False)
        assert BreakoutDetector(db).detect_breakouts(limit=10) == []

    def test_returns_empty_list_on_empty_database(self, db):
        assert BreakoutDetector(db).detect_breakouts(limit=10) == []

    def test_respects_limit(self, db):
        for i in range(3):
            _seed(db, full_name=f"acme/repo{i}")
        candidates = BreakoutDetector(db).detect_breakouts(limit=2)
        assert len(candidates) == 2

    def test_summary_serialisable(self, db):
        _seed(db)
        summary = BreakoutDetector(db).get_breakout_summary()
        assert summary["total_candidates"] == 1
        assert summary["candidates"]
        assert summary["top_5"][0]["repo_full_name"] == "acme/rocket"
