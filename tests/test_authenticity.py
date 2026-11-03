"""Tests for star authenticity & organic growth confidence scoring."""

from __future__ import annotations

import pytest

from radar.analysis.authenticity import AuthenticityScorer

NOW = "2026-11-03T00:00:00+00:00"


@pytest.fixture
def db(tmp_path):
    from radar.storage.database import Database

    return Database(str(tmp_path / "test_auth.db"))


def test_organic_confidence_healthy_repo(db):
    with db._conn() as conn:
        conn.execute(
            """INSERT INTO repositories
               (full_name, url, stars, forks, open_issues, watchers, created_at, pushed_at)
               VALUES ('vllm-project/vllm', 'https://github.com/vllm-project/vllm',
                       25000, 3200, 450, 200, ?, ?)""",
            (NOW, NOW),
        )
        conn.execute(
            """INSERT INTO growth_metrics
               (repo_full_name, timestamp, stars_7d, stars_30d, stars_90d,
                star_growth_rate_7d, star_growth_rate_30d,
                star_growth_acceleration, forks_7d, forks_30d, days_since_last_push)
               VALUES ('vllm-project/vllm', ?, 350, 1500, 4500, 50.0, 50.0, 1.0, 45, 180, 0)""",
            (NOW,),
        )

    scorer = AuthenticityScorer(db)
    results = scorer.compute(min_stars=100)

    assert len(results) == 1
    res = results[0]
    assert res["repo_full_name"] == "vllm-project/vllm"
    assert res["organic_confidence"] >= 80.0
    assert res["verdict"] == "organic"
    assert res["label"] == "High Confidence"


def test_organic_confidence_suspicious_bot_repo(db):
    with db._conn() as conn:
        conn.execute(
            """INSERT INTO repositories
               (full_name, url, stars, forks, open_issues, watchers, created_at, pushed_at)
               VALUES ('bot-farm/shady-ai', 'https://github.com/bot-farm/shady-ai',
                       8000, 5, 0, 1, ?, ?)""",
            (NOW, NOW),
        )
        conn.execute(
            """INSERT INTO growth_metrics
               (repo_full_name, timestamp, stars_7d, stars_30d, stars_90d,
                star_growth_rate_7d, star_growth_rate_30d,
                star_growth_acceleration, forks_7d, forks_30d, days_since_last_push)
               VALUES ('bot-farm/shady-ai', ?, 3000, 3100, 3100, 428.0, 10.0, 8.5, 0, 2, 45)""",
            (NOW,),
        )

    scorer = AuthenticityScorer(db)
    results = scorer.compute(min_stars=100)

    assert len(results) == 1
    res = results[0]
    assert res["repo_full_name"] == "bot-farm/shady-ai"
    assert res["organic_confidence"] < 40.0
    assert res["verdict"] in ("mixed", "suspicious")
    assert len(res["red_flags"]) > 0
