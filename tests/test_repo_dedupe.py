"""Tests for case-insensitive repository identity.

GitHub repo names are case-insensitive, but `repositories.full_name` is not. An
upstream rename that only changed casing (e.g. `jub0t/Concat` -> `jub0t/concat`)
used to create a second row for the same project, which leaked out as duplicate
project pages and case-colliding export filenames.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

EXPORT_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export.py"


@pytest.fixture
def db(tmp_path):
    from radar.storage.database import Database

    return Database(str(tmp_path / "dedupe.db"))


@pytest.fixture
def export_mod():
    spec = importlib.util.spec_from_file_location("radar_export", EXPORT_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestUpsertCaseInsensitive:
    def test_case_variant_updates_existing_row(self, db):
        new, updated = db.upsert_repos([{"full_name": "Acme/Widget", "stars": 100}])
        assert (new, updated) == (1, 0)

        new, updated = db.upsert_repos([{"full_name": "acme/widget", "stars": 250}])
        assert (new, updated) == (0, 1)

        with db._conn() as conn:
            rows = conn.execute("SELECT full_name, stars FROM repositories").fetchall()
        assert len(rows) == 1
        # Original casing is preserved; the new stars are applied.
        assert rows[0]["full_name"] == "Acme/Widget"
        assert rows[0]["stars"] == 250

    def test_case_variants_within_one_batch_insert_once(self, db):
        new, _ = db.upsert_repos(
            [
                {"full_name": "Acme/Widget", "stars": 100},
                {"full_name": "acme/widget", "stars": 400},
            ]
        )
        assert new == 1
        with db._conn() as conn:
            assert conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0] == 1


class TestExportDedupe:
    def test_keeps_freshest_row_per_repo(self, export_mod):
        repos = [
            {"full_name": "jub0t/concat", "stars": 6987, "pushed_at": "2026-10-16T00:00:00Z"},
            {"full_name": "jub0t/Concat", "stars": 13662, "pushed_at": "2026-11-01T00:00:00Z"},
            {"full_name": "other/repo", "stars": 10, "pushed_at": "2026-01-01T00:00:00Z"},
        ]
        deduped = export_mod._dedupe_repos(repos)

        assert len(deduped) == 2
        winner = next(r for r in deduped if r["full_name"].lower() == "jub0t/concat")
        assert winner["full_name"] == "jub0t/Concat"
        assert winner["stars"] == 13662

    def test_drops_entries_without_a_name(self, export_mod):
        assert export_mod._dedupe_repos([{"full_name": ""}, {"stars": 5}]) == []
