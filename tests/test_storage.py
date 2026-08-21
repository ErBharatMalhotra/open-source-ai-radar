"""Tests for JSON storage module."""

from tempfile import TemporaryDirectory

from radar.storage.json_store import JSONStore


def test_save_and_load_repos():
    """Test saving and loading repositories."""
    with TemporaryDirectory() as tmpdir:
        store = JSONStore(tmpdir)

        repos = [
            {"full_name": "test/repo1", "stars": 1000, "url": "https://github.com/test/repo1"},
            {"full_name": "test/repo2", "stars": 500, "url": "https://github.com/test/repo2"},
        ]

        store.save_repos(repos)
        loaded = store.load_repos()

        assert len(loaded) == 2
        # Should be sorted by stars descending
        assert loaded[0]["full_name"] == "test/repo1"
        assert loaded[0]["stars"] == 1000


def test_upsert_repo():
    """Test upserting a repository."""
    with TemporaryDirectory() as tmpdir:
        store = JSONStore(tmpdir)

        # Insert
        repo1 = {"full_name": "test/repo", "stars": 100}
        assert store.upsert_repo(repo1) is True

        # Update
        repo1_updated = {"full_name": "test/repo", "stars": 200, "description": "updated"}
        assert store.upsert_repo(repo1_updated) is False

        loaded = store.load_repos()
        assert len(loaded) == 1
        assert loaded[0]["stars"] == 200
        assert loaded[0]["description"] == "updated"


def test_get_repo():
    """Test getting a single repo."""
    with TemporaryDirectory() as tmpdir:
        store = JSONStore(tmpdir)

        repos = [
            {"full_name": "a/first", "stars": 100},
            {"full_name": "b/second", "stars": 200},
        ]
        store.save_repos(repos)

        found = store.get_repo("b/second")
        assert found is not None
        assert found["stars"] == 200

        not_found = store.get_repo("c/third")
        assert not_found is None


def test_snapshots():
    """Test snapshot storage."""
    with TemporaryDirectory() as tmpdir:
        store = JSONStore(tmpdir)

        # Save snapshot
        snapshot = {
            "full_name": "test/repo",
            "stars": 1000,
            "forks": 200,
        }
        store.save_snapshot("2026-08-21", snapshot)

        # Load snapshot
        loaded = store.load_snapshot("2026-08-21")
        assert "test/repo" in loaded
        assert loaded["test/repo"]["stars"] == 1000

        # List snapshots
        snapshots = store.list_snapshots()
        assert "2026-08-21" in snapshots


def test_stats():
    """Test stats generation."""
    with TemporaryDirectory() as tmpdir:
        store = JSONStore(tmpdir)

        repos = [
            {
                "full_name": "a/repo1",
                "stars": 1000,
                "language": "Python",
                "discovery_sources": ["mcp:topic"],
            },
            {
                "full_name": "b/repo2",
                "stars": 500,
                "language": "TypeScript",
                "discovery_sources": ["llm:keyword"],
            },
            {
                "full_name": "c/repo3",
                "stars": 200,
                "language": "Python",
                "discovery_sources": ["mcp:keyword"],
            },
        ]
        store.save_repos(repos)

        stats = store.get_stats()
        assert stats["total_repos"] == 3
        assert stats["total_stars"] == 1700
        assert stats["top_languages"]["Python"] == 2
