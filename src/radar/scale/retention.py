"""Retention — configurable cleanup of old snapshots, scores, and growth metrics."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from radar.scale.config import load_scale_config
from radar.storage.database import Database

logger = logging.getLogger(__name__)


class SnapshotRetention:

    def __init__(self, db=None, config=None):
        self.db = db or Database()
        self.config = config or load_scale_config()

    def get_cleanup_candidates(self, dry_run=True):
        ret = self.config.get('retention', {})
        tier_keep = ret.get('tier_keep_days', {1: 730, 2: 365, 3: 180, 4: 90})
        now = datetime.now(tz=UTC)
        candidates = []

        for tier, keep_days in tier_keep.items():
            cutoff = (now - timedelta(days=keep_days)).isoformat()
            with self.db._conn() as conn:
                rows = conn.execute("""SELECT s.repo_full_name, COUNT(*) as cnt
                    FROM snapshots s
                    JOIN repositories r ON s.repo_full_name = r.full_name
                    WHERE r.full_name IN (
                        SELECT full_name FROM repositories
                        WHERE full_name IN (
                            SELECT repo_full_name FROM processing_cursor WHERE tier=?)
                    ) AND s.timestamp < ?
                    GROUP BY s.repo_full_name""", (tier, cutoff)).fetchall()
            for row in rows:
                candidates.append({
                    'repo': row[0], 'count': row[1],
                    'tier': tier, 'keep_days': keep_days,
                })

        return candidates

    def cleanup(self, dry_run=True):
        ret = self.config.get('retention', {})
        candidates = self.get_cleanup_candidates(dry_run=dry_run)

        if not candidates:
            logger.info('No snapshots to clean up')
            return {'deleted': 0, 'repos_affected': 0}

        total_deleted = 0
        repos_affected = 0

        for candidate in candidates:
            tier_keep = ret.get('tier_keep_days', {}).get(candidate['tier'], 365)
            cutoff = (datetime.now(tz=UTC) - timedelta(days=tier_keep)).isoformat()

            with self.db._conn() as conn:
                if dry_run:
                    # Count what WOULD be deleted; standard SQLite builds do
                    # not support DELETE ... LIMIT, so execute-time cleanup
                    # removes everything past the cutoff in one statement.
                    deleted = conn.execute("""SELECT COUNT(*) FROM snapshots
                        WHERE repo_full_name = ? AND timestamp < ?""",
                        (candidate['repo'], cutoff)).fetchone()[0]
                else:
                    deleted = conn.execute("""DELETE FROM snapshots
                        WHERE repo_full_name = ? AND timestamp < ?""",
                        (candidate['repo'], cutoff)).rowcount
                if deleted > 0:
                    total_deleted += deleted
                    repos_affected += 1
                    if not dry_run:
                        logger.info(f'Cleaned {deleted} snapshots for {candidate["repo"]}')

        action = 'Would delete' if dry_run else 'Deleted'
        logger.info(f'{action} {total_deleted} snapshots across {repos_affected} repos')
        return {'deleted': total_deleted, 'repos_affected': repos_affected, 'dry_run': dry_run}

    def get_storage_stats(self):
        with self.db._conn() as conn:
            total_snapshots = conn.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0]
            unique_repos = conn.execute(
                'SELECT COUNT(DISTINCT repo_full_name) FROM snapshots').fetchone()[0]
            oldest = conn.execute('SELECT MIN(timestamp) FROM snapshots').fetchone()[0]
            newest = conn.execute('SELECT MAX(timestamp) FROM snapshots').fetchone()[0]
            total_scores = conn.execute('SELECT COUNT(*) FROM scores').fetchone()[0]
            total_growth = conn.execute('SELECT COUNT(*) FROM growth_metrics').fetchone()[0]
            db_size = conn.execute(
                'SELECT page_count * page_size '
                'FROM pragma_page_count(), pragma_page_size()').fetchone()[0]
        return {
            'total_snapshots': total_snapshots,
            'unique_repos': unique_repos,
            'oldest_snapshot': oldest,
            'newest_snapshot': newest,
            'total_scores': total_scores,
            'total_growth_metrics': total_growth,
            'db_size_bytes': db_size,
            'db_size_mb': round(db_size / 1024 / 1024, 1),
        }


class ScoreRetention:
    """Retention for the per-run append-only tables: scores + growth_metrics.

    Unlike ai_analysis (upserted per repo), these tables gain one row per
    repo per run and would grow without bound — millions of rows/day at
    500K repos. A single indexed cutoff DELETE keeps them bounded.
    """

    def __init__(self, db=None, config=None, keep_days=None):
        self.db = db or Database()
        self.config = config or load_scale_config()
        self.keep_days = keep_days or self.config.get('retention', {}).get(
            'score_keep_days', 120)

    def _cutoff(self) -> str:
        return (datetime.now(tz=UTC) - timedelta(days=self.keep_days)).isoformat()

    def cleanup(self, dry_run=True) -> dict[str, int]:
        cutoff = self._cutoff()
        result: dict[str, int] = {'scores': 0, 'growth_metrics': 0, 'dry_run': dry_run}
        with self.db._conn() as conn:
            for table in ('scores', 'growth_metrics'):
                if dry_run:
                    deleted = conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE timestamp < ?", (cutoff,)
                    ).fetchone()[0]
                else:
                    deleted = conn.execute(
                        f"DELETE FROM {table} WHERE timestamp < ?", (cutoff,)
                    ).rowcount
                    if deleted > 0:
                        logger.info(f'Cleaned {deleted} rows from {table} (older than {cutoff})')
                result[table] = max(deleted, 0)
        action = 'Would delete' if dry_run else 'Deleted'
        logger.info(
            f'{action} {result["scores"]} scores + '
            f'{result["growth_metrics"]} growth_metrics rows'
        )
        return result
