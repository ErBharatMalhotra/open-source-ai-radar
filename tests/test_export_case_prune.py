"""Tests for pruning case-variant export files.

GitHub repository names are case-insensitive, so `Owner/Repo` and `Owner/repo`
are one project. When a repository's spelling changes, exports written under
the previous casing linger in history/ and api/badges/ even though the project
page has moved on -- producing duplicate pages and, on case-insensitive
filesystems, files git reports as perpetually modified.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.export import prune_case_variants


def _seed(out: Path) -> None:
    (out / "projects").mkdir(parents=True)
    (out / "api" / "history").mkdir(parents=True)
    (out / "api" / "badges").mkdir(parents=True)

    # Canonical project pages.
    (out / "projects" / "Owner__Repo.json").write_text("{}", encoding="utf-8")
    (out / "projects" / "Other__Project.json").write_text("{}", encoding="utf-8")

    # Stale exports under the previous spelling, in sibling directories.
    (out / "api" / "history" / "Owner__repo.json").write_text("{}", encoding="utf-8")
    stale_badge = out / "api" / "badges" / "Owner__repo"
    stale_badge.mkdir()
    (stale_badge / "score.svg").write_text("<svg/>", encoding="utf-8")

    # Matching exports that should survive.
    (out / "api" / "history" / "Other__Project.json").write_text("{}", encoding="utf-8")
    keep_badge = out / "api" / "badges" / "Other__Project"
    keep_badge.mkdir()
    (keep_badge / "score.svg").write_text("<svg/>", encoding="utf-8")


def _names(directory: Path, suffix: str = "") -> list[str]:
    """Directory listing, not path lookups: Windows resolves names case-insensitively."""
    return sorted(p.name for p in directory.iterdir() if p.name.endswith(suffix))


def test_prune_removes_stale_history_and_badges(tmp_path: Path) -> None:
    out = tmp_path / "exports"
    _seed(out)

    prune_case_variants(str(out))

    assert _names(out / "api" / "history", ".json") == ["Other__Project.json"]
    assert _names(out / "api" / "badges") == ["Other__Project"]
    assert _names(out / "projects", ".json") == ["Other__Project.json", "Owner__Repo.json"]


def test_prune_keeps_names_without_a_project_page(tmp_path: Path) -> None:
    """No canonical page means no reference spelling to correct against."""
    out = tmp_path / "exports"
    _seed(out)
    (out / "api" / "history" / "Ghost__project.json").write_text("{}", encoding="utf-8")

    prune_case_variants(str(out))

    assert "Ghost__project.json" in _names(out / "api" / "history", ".json")


def test_prune_is_a_noop_without_projects_dir(tmp_path: Path) -> None:
    out = tmp_path / "exports"
    out.mkdir()

    prune_case_variants(str(out))

    assert list(out.iterdir()) == []
