"""Persistent processing scheduler - queue-based, tier-aware, crash-safe."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from radar.scale.config import get_interval_hours, get_tier_for_stars, load_scale_config
from radar.storage.database import Database

logger = logging.getLogger(__name__)


class ProcessingScheduler:

    def __init__(self, db=None, config=None):
        self.db = db or Database()
        self.config = config or load_scale_config()
        self._ensure_cursor_table()

    def _ensure_cursor_table(self):
        with self.db._conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS processing_cursor (
                repo_full_name TEXT PRIMARY KEY,
                tier INTEGER NOT NULL DEFAULT 4,
                last_processed_at TEXT,
                next_scheduled_at TEXT,
                processing_status TEXT DEFAULT 'pending',
                processing_attempts INTEGER DEFAULT 0,
                last_processing_error TEXT,
                created_at TEXT,
                updated_at TEXT
            )""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_cursor_schedule
                ON processing_cursor(next_scheduled_at, tier, processing_status)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_cursor_tier
                ON processing_cursor(tier, last_processed_at)""")
            conn.commit()

    def sync_repos_to_cursor(self):
        with self.db._conn() as conn:
            repos = conn.execute('SELECT full_name, stars FROM repositories').fetchall()
            new_count = 0
            for full_name, stars in repos:
                tier = get_tier_for_stars(stars or 0, self.config)
                now = datetime.now(tz=UTC).isoformat()
                result = conn.execute("""INSERT OR IGNORE INTO processing_cursor
                    (repo_full_name, tier, processing_status, created_at, updated_at)
                    VALUES (?, ?, 'pending', ?, ?)""", (full_name, tier, now, now))
                if result.rowcount > 0:
                    new_count += 1
                else:
                    conn.execute("""UPDATE processing_cursor SET tier=?, updated_at=?
                        WHERE repo_full_name=? AND tier!=?""", (tier, now, full_name, tier))
            conn.commit()
        return new_count

    def get_next_batch(self, batch_size=None):
        size = batch_size or self.config.get('batch', {}).get('size', 700)
        now = datetime.now(tz=UTC).isoformat()
        with self.db._conn() as conn:
            rows = conn.execute("""SELECT c.repo_full_name, c.tier, c.processing_attempts,
                c.last_processing_error, r.stars FROM processing_cursor c
                JOIN repositories r ON c.repo_full_name = r.full_name
                WHERE c.processing_status != 'processing'
                AND (c.next_scheduled_at IS NULL OR c.next_scheduled_at <= ?
                OR c.processing_status = 'failed')
                ORDER BY c.tier ASC, r.stars DESC LIMIT ?""", (now, size)).fetchall()
        return [{'full_name': r[0], 'tier': r[1], 'attempts': r[2],
                 'last_error': r[3], 'stars': r[4] or 0} for r in rows]

    def mark_processing(self, repos):
        now = datetime.now(tz=UTC).isoformat()
        with self.db._conn() as conn:
            for repo in repos:
                conn.execute("""UPDATE processing_cursor SET processing_status='processing',
                    processing_attempts=processing_attempts+1, updated_at=?
                    WHERE repo_full_name=?""", (now, repo['full_name']))
            conn.commit()

    def mark_completed(self, full_name):
        now = datetime.now(tz=UTC)
        interval_hours = get_interval_hours(self._get_tier(full_name), self.config)
        next_run = now + timedelta(hours=interval_hours)
        with self.db._conn() as conn:
            conn.execute("""UPDATE processing_cursor SET processing_status='completed',
                last_processed_at=?, next_scheduled_at=?, last_processing_error=NULL,
                updated_at=? WHERE repo_full_name=?""",
                (now.isoformat(), next_run.isoformat(), now.isoformat(), full_name))
            conn.commit()

    def mark_failed(self, full_name, error):
        now = datetime.now(tz=UTC).isoformat()
        max_attempts = self.config.get('retries', {}).get('max_attempts', 3)
        with self.db._conn() as conn:
            row = conn.execute(
                'SELECT processing_attempts FROM processing_cursor WHERE repo_full_name=?',
                (full_name,)).fetchone()
            status = 'permanent_failure' if (row and row[0] >= max_attempts) else 'failed'
            conn.execute("""UPDATE processing_cursor SET processing_status=?,
                last_processing_error=?, updated_at=? WHERE repo_full_name=?""",
                (status, error, now, full_name))
            conn.commit()

    def mark_skipped(self, full_name):
        now = datetime.now(tz=UTC)
        interval_hours = get_interval_hours(self._get_tier(full_name), self.config)
        next_run = now + timedelta(hours=interval_hours)
        with self.db._conn() as conn:
            conn.execute("""UPDATE processing_cursor SET processing_status='skipped',
                last_processed_at=?, next_scheduled_at=?, updated_at=?
                WHERE repo_full_name=?""",
                (now.isoformat(), next_run.isoformat(), now.isoformat(), full_name))
            conn.commit()

    def get_stats(self):
        with self.db._conn() as conn:
            total = conn.execute('SELECT COUNT(*) FROM processing_cursor').fetchone()[0]
            by_status = {r[0]: r[1] for r in conn.execute(
                'SELECT processing_status, COUNT(*) FROM processing_cursor '
                'GROUP BY processing_status').fetchall()}
            by_tier = {r[0]: r[1] for r in conn.execute(
                'SELECT tier, COUNT(*) FROM processing_cursor '
                'GROUP BY tier ORDER BY tier').fetchall()}
            now = datetime.now(tz=UTC).isoformat()
            due = conn.execute(
                'SELECT COUNT(*) FROM processing_cursor '
                'WHERE next_scheduled_at IS NULL OR next_scheduled_at<=?',
                (now,)).fetchone()[0]
            last_run = conn.execute(
                'SELECT MAX(last_processed_at) FROM processing_cursor').fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM processing_cursor "
                "WHERE processing_status='failed'").fetchone()[0]
            perm = conn.execute(
                "SELECT COUNT(*) FROM processing_cursor "
                "WHERE processing_status='permanent_failure'").fetchone()[0]
        return {'total_repos': total, 'due_for_processing': due, 'by_status': by_status,
                'by_tier': by_tier, 'failed': failed, 'permanent_failures': perm,
                'last_successful_run': last_run}

    def _get_tier(self, full_name):
        with self.db._conn() as conn:
            row = conn.execute(
                'SELECT tier FROM processing_cursor WHERE repo_full_name=?',
                (full_name,)).fetchone()
        return row[0] if row else 4
