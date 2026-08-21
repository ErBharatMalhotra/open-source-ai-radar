"""Change detector — lightweight signature comparison for incremental processing.

Instead of processing all 5,000+ repos every run, we compute a compact
"processing signature" from key metrics. On the next run, only repos whose
signature has changed need re-processing.

Signature is built from:
  - pushed_at (last commit time)
  - stars
  - forks
  - open_issues
  - latest_release (tag name or date)
  - contributors (mentionable_users)

This is intentionally cheap — a single string comparison per repo.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from radar.storage.database import Database

logger = logging.getLogger(__name__)


def compute_signature(repo: dict[str, Any]) -> str:
    """Compute a lightweight processing signature for a repository.

    The signature captures whether any tracked metric has changed.
    Two repos with identical metrics produce identical signatures.

    Returns:
        A short hex string (first 16 chars of SHA-256).
    """
    sig_data = {
        "pushed_at": repo.get("pushed_at", ""),
        "stars": repo.get("stars", 0),
        "forks": repo.get("forks", 0),
        "open_issues": repo.get("open_issues", 0),
        "latest_release": repo.get("latest_release_tag", "")
                          or repo.get("latest_release_date", ""),
        "contributors": repo.get("mentionable_users", 0),
    }
    raw = json.dumps(sig_data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def compute_signatures_batch(repos: list[dict[str, Any]]) -> dict[str, str]:
    """Compute signatures for a batch of repos.

    Returns:
        dict of {full_name: signature}
    """
    return {repo["full_name"]: compute_signature(repo) for repo in repos}


class ChangeDetector:
    """Detects which repositories have changed since last processing.

    Usage:
        detector = ChangeDetector(db)
        changed = detector.find_changed(repos)
        # Only 'changed' repos need full processing (snapshot, score, etc.)
        detector.mark_processed(changed, signatures)
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def find_changed(self, repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter repos to only those that have changed.

        Args:
            repos: Full repo data dicts (must include full_name and tracked fields)

        Returns:
            List of repo dicts that need processing.
        """
        if not repos:
            return []

        # Compute new signatures
        new_sigs = compute_signatures_batch(repos)

        # Compare against stored signatures
        changed_names = self.db.get_repos_needing_processing(new_sigs)

        if not changed_names:
            logger.info("No repos changed — all signatures match")
            return []

        changed_set = set(changed_names)
        changed_repos = [r for r in repos if r["full_name"] in changed_set]

        total = len(repos)
        n_changed = len(changed_repos)
        pct = (n_changed / total * 100) if total > 0 else 0
        logger.info(
            f"Change detection: {n_changed}/{total} repos changed ({pct:.1f}%)"
        )

        return changed_repos

    def find_unprocessed(self) -> list[dict[str, Any]]:
        """Find repos that have never been processed."""
        return self.db.get_unprocessed_repos()

    def mark_processed(
        self,
        repos: list[dict[str, Any]],
        signatures: dict[str, str] | None = None,
    ) -> None:
        """Mark repos as processed by updating their signatures.

        Args:
            repos: Repo dicts that were processed
            signatures: Optional pre-computed signatures. If None, computed from repos.
        """
        if not repos:
            return

        if signatures is None:
            signatures = compute_signatures_batch(repos)

        updates = [
            (r["full_name"], signatures[r["full_name"]])
            for r in repos
            if r["full_name"] in signatures
        ]

        self.db.update_processing_signatures_batch(updates)
        logger.info(f"Marked {len(updates)} repos as processed")

    def get_stats(self) -> dict[str, Any]:
        """Get processing statistics."""
        with self.db._conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM repositories"
            ).fetchone()[0]

            processed = conn.execute(
                "SELECT COUNT(*) FROM repositories WHERE processing_signature != ''"
            ).fetchone()[0]

            unprocessed = total - processed

            last_run = conn.execute(
                """SELECT MAX(last_processed_at) as last_run
                FROM repositories WHERE last_processed_at IS NOT NULL"""
            ).fetchone()["last_run"]

            return {
                "total_repos": total,
                "processed": processed,
                "unprocessed": unprocessed,
                "last_run": last_run,
            }
