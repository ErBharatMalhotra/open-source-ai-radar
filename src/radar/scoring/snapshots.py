"""Snapshot engine — captures current repo metrics and calculates growth.

The snapshot system is the foundation for historical intelligence.
Each snapshot captures a point-in-time view of a repository's metrics.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime
from typing import Any

from radar.github.client import GitHubClient
from radar.storage.database import Database

logger = logging.getLogger(__name__)


def calculate_freshness(
    days_since_push: int, lam: float = 0.01
) -> float:
    """Calculate freshness score using exponential decay.

    freshness = e^(-lambda * days)

    - 0 days old: 1.0 (fresh)
    - 30 days: 0.74
    - 90 days: 0.41
    - 180 days: 0.16
    """
    return math.exp(-lam * days_since_push)


def calculate_growth_metrics(
    current: dict[str, Any],
    previous_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate growth metrics by comparing current to historical snapshots.

    Args:
        current: Current repo data (stars, forks, etc.)
        previous_snapshots: List of past snapshots, newest first

    Returns:
        Dictionary with growth metrics
    """
    now = datetime.now(tz=UTC)
    result: dict[str, Any] = {}

    # Default values if no history
    result["stars_7d"] = 0
    result["stars_30d"] = 0
    result["stars_90d"] = 0
    result["star_growth_rate_7d"] = 0.0
    result["star_growth_rate_30d"] = 0.0
    result["star_growth_acceleration"] = 1.0  # Default: stable (no change)
    result["forks_7d"] = 0
    result["forks_30d"] = 0
    result["contributors_7d"] = 0

    # Days since last push
    pushed_at = current.get("pushed_at")
    if pushed_at:
        try:
            push_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            result["days_since_last_push"] = (now - push_dt).days
        except (ValueError, AttributeError):
            result["days_since_last_push"] = 999
    else:
        result["days_since_last_push"] = 999

    result["freshness_score"] = calculate_freshness(
        result["days_since_last_push"]
    )

    if not previous_snapshots:
        return result

    current_stars = current.get("stars", 0)
    current_forks = current.get("forks", 0)

    # Find snapshots by age
    for snap in previous_snapshots:
        try:
            snap_time = datetime.fromisoformat(snap["timestamp"].replace("Z", "+00:00"))
            days_ago = (now - snap_time).days

            star_diff = current_stars - snap.get("stars", 0)
            fork_diff = current_forks - snap.get("forks", 0)

            if days_ago <= 7:
                result["stars_7d"] = star_diff
                result["forks_7d"] = fork_diff
                if days_ago > 0:
                    result["star_growth_rate_7d"] = star_diff / days_ago

            if days_ago <= 30:
                result["stars_30d"] = star_diff
                result["forks_30d"] = fork_diff
                if days_ago > 0:
                    result["star_growth_rate_30d"] = star_diff / days_ago

            if days_ago <= 90:
                result["stars_90d"] = star_diff

        except (ValueError, KeyError, AttributeError):
            continue

    # Growth acceleration: rate_7d vs rate_30d
    if result["star_growth_rate_30d"] > 0:
        result["star_growth_acceleration"] = (
            result["star_growth_rate_7d"] / result["star_growth_rate_30d"]
        )
    else:
        result["star_growth_acceleration"] = 1.0

    return result


class SnapshotEngine:
    """Captures current repo metrics and stores them as snapshots.

    Supports:
    - Single repo snapshot
    - Batch snapshot of all tracked repos
    - Incremental snapshot (only changed repos)
    - Growth calculation from historical data
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    async def snapshot_repo(
        self,
        client: GitHubClient,
        full_name: str,
    ) -> dict[str, Any] | None:
        """Capture a snapshot for a single repository.

        Returns the snapshot data, or None if fetch failed.
        """
        parts = full_name.split("/")
        if len(parts) != 2:
            return None

        owner, name = parts
        repo_data = await client.get_repo(owner, name)
        if not repo_data:
            return None

        # Update repository record
        self.db.upsert_repo(repo_data)

        # Get previous snapshots for growth calculation
        prev_snapshots = self.db.get_snapshots(full_name, limit=90)

        # Calculate growth metrics
        growth = calculate_growth_metrics(repo_data, prev_snapshots)

        # Create snapshot
        now = datetime.now(tz=UTC).isoformat()
        snapshot = {
            "repo_full_name": full_name,
            "timestamp": now,
            "stars": repo_data.get("stars", 0),
            "forks": repo_data.get("forks", 0),
            "open_issues": repo_data.get("open_issues", 0),
            "contributors": repo_data.get("mentionable_users", 0),
            "releases": 1 if repo_data.get("latest_release_tag") else 0,
            "latest_release": repo_data.get("latest_release_tag"),
            "latest_release_date": repo_data.get("latest_release_date"),
        }

        self.db.save_snapshot(full_name, snapshot)

        # Save growth metrics
        growth["repo_full_name"] = full_name
        growth["timestamp"] = now
        self.db.save_growth(growth)

        return snapshot

    async def snapshot_all(
        self,
        client: GitHubClient,
        max_repos: int | None = None,
        delay_between: float = 0.5,
    ) -> int:
        """Snapshot all tracked repositories.

        Args:
            client: GitHub API client
            max_repos: Limit number of repos to snapshot
            delay_between: Seconds between API calls

        Returns:
            Number of repos successfully snapshotted
        """
        repos = self.db.get_all_repos()
        if max_repos:
            repos = repos[:max_repos]

        total = len(repos)
        success = 0
        failed = 0

        logger.info(f"Starting batch snapshot of {total} repositories...")

        for i, repo in enumerate(repos, 1):
            full_name = repo["full_name"]

            try:
                snapshot = await self.snapshot_repo(client, full_name)
                if snapshot:
                    success += 1
                    if success % 50 == 0:
                        logger.info(
                            f"Progress: {i}/{total} "
                            f"({success} success, {failed} failed)"
                        )
                else:
                    failed += 1

                # Rate limit: wait between requests
                if delay_between > 0:
                    await asyncio.sleep(delay_between)

            except Exception as e:
                logger.error(f"Failed to snapshot {full_name}: {e}")
                failed += 1

        logger.info(
            f"Batch snapshot complete: {success}/{total} success, {failed} failed"
        )
        return success

    async def snapshot_incremental(
        self,
        client: GitHubClient,
        changed_repos: list[dict[str, Any]],
        delay_between: float = 0.5,
    ) -> tuple[int, int]:
        """Snapshot only repos that have changed.

        This is the core of incremental processing — instead of fetching
        all 5,000+ repos, we only fetch the ~800 that changed.

        Args:
            client: GitHub API client
            changed_repos: List of repo dicts that need updating
            delay_between: Seconds between API calls

        Returns:
            Tuple of (success_count, failed_count)
        """
        if not changed_repos:
            logger.info("No changed repos to snapshot")
            return 0, 0

        total = len(changed_repos)
        success = 0
        failed = 0

        logger.info(f"Starting incremental snapshot of {total} changed repos...")

        for i, repo in enumerate(changed_repos, 1):
            full_name = repo["full_name"]

            try:
                snapshot = await self.snapshot_repo(client, full_name)
                if snapshot:
                    success += 1
                    if success % 25 == 0:
                        logger.info(
                            f"Progress: {i}/{total} "
                            f"({success} success, {failed} failed)"
                        )
                else:
                    failed += 1

                if delay_between > 0:
                    await asyncio.sleep(delay_between)

            except Exception as e:
                logger.error(f"Failed to snapshot {full_name}: {e}")
                failed += 1

        logger.info(
            f"Incremental snapshot complete: {success}/{total} success, {failed} failed"
        )
        return success, failed

    def get_snapshot_summary(self, full_name: str) -> dict[str, Any]:
        """Get a summary of a repo's snapshot history."""
        snapshots = self.db.get_snapshots(full_name, limit=90)
        if not snapshots:
            return {"repo": full_name, "snapshots": 0}

        latest = snapshots[0]
        oldest = snapshots[-1] if len(snapshots) > 1 else latest

        return {
            "repo": full_name,
            "snapshots": len(snapshots),
            "latest_stars": latest.get("stars", 0),
            "oldest_stars": oldest.get("stars", 0),
            "star_change": latest.get("stars", 0) - oldest.get("stars", 0),
            "latest_timestamp": latest.get("timestamp"),
            "oldest_timestamp": oldest.get("timestamp"),
        }
