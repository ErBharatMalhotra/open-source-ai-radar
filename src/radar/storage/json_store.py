"""JSON-based storage for repository data.

Phase 1 uses JSON files. Phase 2 moves to SQLite.
This module abstracts the storage layer.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class JSONStore:
    """Simple JSON file storage for repositories and snapshots."""

    def __init__(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.repos_dir = self.data_dir / "repositories"
        self.snapshots_dir = self.data_dir / "snapshots"
        self.exports_dir = self.data_dir / "exports"

        self.repos_dir.mkdir(exist_ok=True)
        self.snapshots_dir.mkdir(exist_ok=True)
        self.exports_dir.mkdir(exist_ok=True)

        self.repos_file = self.data_dir / "repositories.json"

    # --- Repository storage ---

    def load_repos(self) -> list[dict[str, Any]]:
        """Load all repositories from the main JSON file."""
        if not self.repos_file.exists():
            return []
        try:
            return json.loads(self.repos_file.read_text())
        except (json.JSONDecodeError, ValueError):
            logger.error(f"Failed to parse {self.repos_file}")
            return []

    def save_repos(self, repos: list[dict[str, Any]]) -> None:
        """Save repositories to the main JSON file."""
        # Sort by stars descending
        repos.sort(key=lambda r: r.get("stars", 0), reverse=True)
        self.repos_file.write_text(json.dumps(repos, indent=2, default=str))
        logger.info(f"Saved {len(repos)} repos to {self.repos_file}")

    def upsert_repo(self, repo: dict[str, Any]) -> bool:
        """Add or update a single repository. Returns True if new."""
        repos = self.load_repos()
        full_name = repo.get("full_name", "")

        for i, existing in enumerate(repos):
            if existing.get("full_name") == full_name:
                # Update existing
                repos[i] = {**existing, **repo}
                self.save_repos(repos)
                return False

        # Add new
        repos.append(repo)
        self.save_repos(repos)
        return True

    def get_repo(self, full_name: str) -> dict[str, Any] | None:
        """Get a single repo by full_name."""
        repos = self.load_repos()
        for repo in repos:
            if repo.get("full_name") == full_name:
                return repo
        return None

    # --- Snapshot storage ---

    def save_snapshot(self, date_str: str, snapshot: dict[str, Any]) -> None:
        """Save a daily snapshot of all repo metrics."""
        snapshot_file = self.snapshots_dir / f"{date_str}.json"

        existing: dict[str, Any] = {}
        if snapshot_file.exists():
            try:
                existing = json.loads(snapshot_file.read_text())
            except (json.JSONDecodeError, ValueError):
                existing = {}

        # Merge
        full_name = snapshot.get("full_name", "")
        if full_name:
            existing[full_name] = snapshot

        snapshot_file.write_text(json.dumps(existing, indent=2, default=str))

    def load_snapshot(self, date_str: str) -> dict[str, Any]:
        """Load a snapshot for a given date."""
        snapshot_file = self.snapshots_dir / f"{date_str}.json"
        if not snapshot_file.exists():
            return {}
        try:
            return json.loads(snapshot_file.read_text())
        except (json.JSONDecodeError, ValueError):
            return {}

    def list_snapshots(self) -> list[str]:
        """List all available snapshot dates, sorted."""
        files = list(self.snapshots_dir.glob("*.json"))
        dates = sorted(f.stem for f in files)
        return dates

    # --- Export ---

    def export_top(self, n: int = 50, output_file: str = "top_repos.json") -> None:
        """Export top N repos to an export file."""
        repos = self.load_repos()
        top = repos[:n]

        export_data = {
            "generated_at": datetime.now().isoformat(),
            "total_repos": len(repos),
            "exported_count": len(top),
            "repos": top,
        }

        output_path = self.exports_dir / output_file
        output_path.write_text(json.dumps(export_data, indent=2, default=str))
        logger.info(f"Exported top {len(top)} repos to {output_path}")

    # --- Stats ---

    def get_stats(self) -> dict[str, Any]:
        """Get basic database statistics."""
        repos = self.load_repos()
        snapshots = self.list_snapshots()

        total_stars = sum(r.get("stars", 0) for r in repos)
        languages = {}
        categories = {}

        for repo in repos:
            lang = repo.get("language")
            if lang:
                languages[lang] = languages.get(lang, 0) + 1
            for cat in repo.get("discovery_sources", []):
                cat_slug = cat.split(":")[0] if ":" in cat else cat
                categories[cat_slug] = categories.get(cat_slug, 0) + 1

        return {
            "total_repos": len(repos),
            "total_stars": total_stars,
            "snapshots_count": len(snapshots),
            "latest_snapshot": snapshots[-1] if snapshots else None,
            "top_languages": dict(sorted(languages.items(), key=lambda x: -x[1])[:10]),
            "categories": dict(sorted(categories.items(), key=lambda x: -x[1])),
        }
