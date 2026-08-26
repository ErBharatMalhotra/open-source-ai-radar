"""Tests for retention — snapshot + score/growth cleanup."""

import pytest

from radar.scale.retention import ScoreRetention, SnapshotRetention


@pytest.fixture
def db(tmp_path):
    from radar.storage.database import Database

    db_path = tmp_path / "test.db"
    database = Database(str(db_path))
    with database._conn() as conn:
        # processing_cursor is created by the scheduler, not the base schema
        conn.execute("""CREATE TABLE IF NOT EXISTS processing_cursor (
            repo_full_name TEXT PRIMARY KEY,
            tier INTEGER NOT NULL DEFAULT 4
        )""")
        conn.execute("INSERT INTO repositories (full_name, url) VALUES ('a/b', 'u')")
        conn.execute("INSERT INTO processing_cursor (repo_full_name, tier) VALUES ('a/b', 4)")
        # Old rows (200 days) and fresh rows (1 day)
        for ts in ("2026-01-01T00:00:00+00:00", "2026-08-25T00:00:00+00:00"):
            conn.execute(
                "INSERT INTO snapshots (repo_full_name, timestamp) VALUES ('a/b', ?)", (ts,)
            )
            conn.execute(
                "INSERT INTO scores (repo_full_name, timestamp) VALUES ('a/b', ?)", (ts,)
            )
            conn.execute(
                "INSERT INTO growth_metrics (repo_full_name, timestamp) VALUES ('a/b', ?)", (ts,)
            )
    return database


def _config():
    return {"retention": {"tier_keep_days": {4: 90}}}


class TestSnapshotRetention:
    def test_cleanup_deletes_only_old_rows(self, db):
        r = SnapshotRetention(db=db, config=_config())
        result = r.cleanup(dry_run=False)
        assert result["deleted"] == 1  # only the 200-day-old row
        with db._conn() as conn:
            remaining = conn.execute(
                "SELECT COUNT(*) FROM snapshots"
            ).fetchone()[0]
        assert remaining == 1

    def test_dry_run_deletes_nothing(self, db):
        r = SnapshotRetention(db=db, config=_config())
        result = r.cleanup(dry_run=True)
        assert result["deleted"] == 1
        with db._conn() as conn:
            remaining = conn.execute(
                "SELECT COUNT(*) FROM snapshots"
            ).fetchone()[0]
        assert remaining == 2

    def test_stats_include_scores_and_growth(self, db):
        stats = SnapshotRetention(db=db, config=_config()).get_storage_stats()
        assert stats["total_scores"] == 2
        assert stats["total_growth_metrics"] == 2
        assert stats["db_size_mb"] > 0


class TestScoreRetention:
    def test_cleanup_bounds_scores_and_growth(self, db):
        r = ScoreRetention(db=db, config=_config(), keep_days=120)
        result = r.cleanup(dry_run=False)
        assert result["scores"] == 1
        assert result["growth_metrics"] == 1
        with db._conn() as conn:
            scores_left = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
            growth_left = conn.execute(
                "SELECT COUNT(*) FROM growth_metrics"
            ).fetchone()[0]
        assert scores_left == 1
        assert growth_left == 1

    def test_dry_run_keeps_everything(self, db):
        r = ScoreRetention(db=db, config=_config(), keep_days=120)
        result = r.cleanup(dry_run=True)
        assert result["scores"] == 1
        with db._conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        assert count == 2

    def test_default_keep_days_from_config(self, db):
        cfg = {"retention": {"score_keep_days": 30}}
        r = ScoreRetention(db=db, config=cfg)
        assert r.keep_days == 30
