"""Tests for change detection and incremental processing."""

import tempfile
from pathlib import Path

import pytest

from radar.processing.change_detector import (
    ChangeDetector,
    compute_signature,
    compute_signatures_batch,
)
from radar.storage.database import Database


@pytest.fixture
def tmp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(str(db_path))
        yield db


@pytest.fixture
def sample_repos():
    """Sample repository data for testing."""
    return [
        {
            "full_name": "owner/repo1",
            "url": "https://github.com/owner/repo1",
            "description": "Test repo 1",
            "language": "Python",
            "stars": 1000,
            "forks": 100,
            "open_issues": 10,
            "pushed_at": "2026-08-20T12:00:00Z",
            "latest_release_tag": "v1.0.0",
            "latest_release_date": "2026-08-19T10:00:00Z",
            "mentionable_users": 50,
        },
        {
            "full_name": "owner/repo2",
            "url": "https://github.com/owner/repo2",
            "description": "Test repo 2",
            "language": "TypeScript",
            "stars": 5000,
            "forks": 500,
            "open_issues": 25,
            "pushed_at": "2026-08-21T08:00:00Z",
            "latest_release_tag": "v2.1.0",
            "latest_release_date": "2026-08-20T15:00:00Z",
            "mentionable_users": 200,
        },
    ]


class TestSignature:
    def test_compute_signature_deterministic(self):
        """Same input produces same signature."""
        repo = {"stars": 100, "forks": 10, "pushed_at": "2026-08-20T12:00:00Z"}
        sig1 = compute_signature(repo)
        sig2 = compute_signature(repo)
        assert sig1 == sig2

    def test_compute_signature_different_for_different_data(self):
        """Different data produces different signatures."""
        repo1 = {"stars": 100, "forks": 10, "pushed_at": "2026-08-20T12:00:00Z"}
        repo2 = {"stars": 200, "forks": 10, "pushed_at": "2026-08-20T12:00:00Z"}
        sig1 = compute_signature(repo1)
        sig2 = compute_signature(repo2)
        assert sig1 != sig2

    def test_compute_signature_star_change(self):
        """Star count change produces different signature."""
        repo = {
            "stars": 1000,
            "forks": 100,
            "open_issues": 10,
            "pushed_at": "2026-08-20T12:00:00Z",
            "latest_release_tag": "v1.0.0",
            "latest_release_date": "2026-08-19T10:00:00Z",
            "mentionable_users": 50,
        }
        sig_before = compute_signature(repo)

        repo["stars"] = 1100
        sig_after = compute_signature(repo)
        assert sig_before != sig_after

    def test_compute_signature_push_time_change(self):
        """Push time change produces different signature."""
        repo = {
            "stars": 1000,
            "forks": 100,
            "open_issues": 10,
            "pushed_at": "2026-08-20T12:00:00Z",
            "latest_release_tag": "v1.0.0",
            "latest_release_date": "2026-08-19T10:00:00Z",
            "mentionable_users": 50,
        }
        sig_before = compute_signature(repo)

        repo["pushed_at"] = "2026-08-21T14:30:00Z"
        sig_after = compute_signature(repo)
        assert sig_before != sig_after

    def test_compute_signatures_batch(self):
        """Batch signature computation works."""
        repos = [
            {"full_name": "a/b", "stars": 100},
            {"full_name": "c/d", "stars": 200},
        ]
        sigs = compute_signatures_batch(repos)
        assert "a/b" in sigs
        assert "c/d" in sigs
        assert sigs["a/b"] != sigs["c/d"]


class TestChangeDetector:
    def test_find_changed_none_when_same(self, tmp_db, sample_repos):
        """No repos flagged as changed when data matches."""
        detector = ChangeDetector(tmp_db)

        # First run: import repos and mark as processed
        tmp_db.upsert_repos(sample_repos)
        detector.mark_processed(sample_repos)

        # Second run: same data
        changed = detector.find_changed(sample_repos)
        assert len(changed) == 0

    def test_find_changed_detects_star_change(self, tmp_db, sample_repos):
        """Detects when star count changes."""
        detector = ChangeDetector(tmp_db)

        # Import and mark
        tmp_db.upsert_repos(sample_repos)
        detector.mark_processed(sample_repos)

        # Change one repo's stars
        modified = [
            {**sample_repos[0], "stars": 1500},  # changed
            sample_repos[1],  # unchanged
        ]

        changed = detector.find_changed(modified)
        assert len(changed) == 1
        assert changed[0]["full_name"] == "owner/repo1"

    def test_find_changed_detects_push_time(self, tmp_db, sample_repos):
        """Detects when pushed_at changes."""
        detector = ChangeDetector(tmp_db)

        tmp_db.upsert_repos(sample_repos)
        detector.mark_processed(sample_repos)

        modified = [
            {**sample_repos[0], "pushed_at": "2026-08-21T20:00:00Z"},  # changed
            sample_repos[1],
        ]

        changed = detector.find_changed(modified)
        assert len(changed) == 1
        assert changed[0]["full_name"] == "owner/repo1"

    def test_find_changed_all_unchanged(self, tmp_db, sample_repos):
        """All repos unchanged returns empty list."""
        detector = ChangeDetector(tmp_db)

        tmp_db.upsert_repos(sample_repos)
        detector.mark_processed(sample_repos)

        # Exact same data
        changed = detector.find_changed(sample_repos)
        assert len(changed) == 0

    def test_find_unprocessed(self, tmp_db, sample_repos):
        """Finds repos with no signature."""
        detector = ChangeDetector(tmp_db)
        tmp_db.upsert_repos(sample_repos)

        unprocessed = detector.find_unprocessed()
        assert len(unprocessed) == 2  # Neither has been processed yet

    def test_mark_processed_then_unprocessed(self, tmp_db, sample_repos):
        """After marking, repos are no longer unprocessed."""
        detector = ChangeDetector(tmp_db)
        tmp_db.upsert_repos(sample_repos)

        # Initially all unprocessed
        assert len(detector.find_unprocessed()) == 2

        # Mark as processed
        detector.mark_processed(sample_repos[:1])

        # Now only 1 unprocessed
        unprocessed = detector.find_unprocessed()
        assert len(unprocessed) == 1
        assert unprocessed[0]["full_name"] == "owner/repo2"

    def test_get_stats(self, tmp_db, sample_repos):
        """Stats reflect processing state."""
        detector = ChangeDetector(tmp_db)
        tmp_db.upsert_repos(sample_repos)

        stats = detector.get_stats()
        assert stats["total_repos"] == 2
        assert stats["processed"] == 0
        assert stats["unprocessed"] == 2

        detector.mark_processed(sample_repos)

        stats = detector.get_stats()
        assert stats["total_repos"] == 2
        assert stats["processed"] == 2
        assert stats["unprocessed"] == 0

    def test_empty_repos(self, tmp_db):
        """Empty repo list handled gracefully."""
        detector = ChangeDetector(tmp_db)
        changed = detector.find_changed([])
        assert changed == []

    def test_fork_count_change(self, tmp_db, sample_repos):
        """Detects fork count changes."""
        detector = ChangeDetector(tmp_db)
        tmp_db.upsert_repos(sample_repos)
        detector.mark_processed(sample_repos)

        modified = [
            sample_repos[0],
            {**sample_repos[1], "forks": 600},  # changed
        ]

        changed = detector.find_changed(modified)
        assert len(changed) == 1
        assert changed[0]["full_name"] == "owner/repo2"

    def test_release_change_detected(self, tmp_db, sample_repos):
        """New release changes the signature."""
        detector = ChangeDetector(tmp_db)
        tmp_db.upsert_repos(sample_repos)
        detector.mark_processed(sample_repos)

        modified = [
            sample_repos[0],
            {**sample_repos[1], "latest_release_tag": "v3.0.0"},  # new release
        ]

        changed = detector.find_changed(modified)
        assert len(changed) == 1
        assert changed[0]["full_name"] == "owner/repo2"
