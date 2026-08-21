"""SQLite database for Open Source AI Radar.

Phase 1 replaces JSON with SQLite for better querying and historical data.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS repositories (
    full_name TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    description TEXT DEFAULT '',
    homepage TEXT DEFAULT '',
    language TEXT,
    license TEXT,
    topics TEXT DEFAULT '[]',
    owner_login TEXT DEFAULT '',
    owner_avatar TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    created_at TEXT,
    pushed_at TEXT,
    discovered_at TEXT,
    last_analyzed_at TEXT,
    discovery_sources TEXT DEFAULT '[]',
    -- Denormalized latest values
    stars INTEGER DEFAULT 0,
    forks INTEGER DEFAULT 0,
    open_issues INTEGER DEFAULT 0,
    watchers INTEGER DEFAULT 0,
    default_branch TEXT DEFAULT 'main'
);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    stars INTEGER DEFAULT 0,
    forks INTEGER DEFAULT 0,
    open_issues INTEGER DEFAULT 0,
    closed_issues INTEGER DEFAULT 0,
    pull_requests INTEGER DEFAULT 0,
    contributors INTEGER DEFAULT 0,
    commits_7d INTEGER DEFAULT 0,
    commits_30d INTEGER DEFAULT 0,
    releases INTEGER DEFAULT 0,
    latest_release TEXT,
    latest_release_date TEXT,
    FOREIGN KEY (repo_full_name) REFERENCES repositories(full_name),
    UNIQUE(repo_full_name, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_repo ON snapshots(repo_full_name);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON snapshots(timestamp);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    impact REAL DEFAULT 0.0,
    velocity REAL DEFAULT 0.0,
    health REAL DEFAULT 0.0,
    radar_score REAL DEFAULT 0.0,
    global_percentile REAL DEFAULT 0.0,
    category_percentile REAL DEFAULT 0.0,
    FOREIGN KEY (repo_full_name) REFERENCES repositories(full_name),
    UNIQUE(repo_full_name, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_scores_repo ON scores(repo_full_name);
CREATE INDEX IF NOT EXISTS idx_scores_radar ON scores(radar_score DESC);
CREATE INDEX IF NOT EXISTS idx_scores_time ON scores(timestamp);

CREATE TABLE IF NOT EXISTS growth_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    stars_7d INTEGER DEFAULT 0,
    stars_30d INTEGER DEFAULT 0,
    stars_90d INTEGER DEFAULT 0,
    star_growth_rate_7d REAL DEFAULT 0.0,
    star_growth_rate_30d REAL DEFAULT 0.0,
    star_growth_acceleration REAL DEFAULT 0.0,
    forks_7d INTEGER DEFAULT 0,
    forks_30d INTEGER DEFAULT 0,
    contributors_7d INTEGER DEFAULT 0,
    days_since_last_push INTEGER DEFAULT 0,
    freshness_score REAL DEFAULT 0.0,
    FOREIGN KEY (repo_full_name) REFERENCES repositories(full_name),
    UNIQUE(repo_full_name, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_growth_repo ON growth_metrics(repo_full_name);

CREATE TABLE IF NOT EXISTS ai_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    category TEXT DEFAULT '',
    sub_category TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    tech_stack TEXT DEFAULT '[]',
    use_cases TEXT DEFAULT '[]',
    maturity TEXT DEFAULT 'Unknown',
    quality REAL DEFAULT 0.0,
    potential REAL DEFAULT 0.0,
    confidence REAL DEFAULT 0.0,
    matched_by TEXT DEFAULT 'none',
    FOREIGN KEY (repo_full_name) REFERENCES repositories(full_name)
);

CREATE INDEX IF NOT EXISTS idx_analysis_repo ON ai_analysis(repo_full_name);
CREATE INDEX IF NOT EXISTS idx_analysis_category ON ai_analysis(category);
"""


class Database:
    """SQLite database for repository data, snapshots, and scores."""

    def __init__(self, db_path: str | Path = "data/radar.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            logger.info(f"Database initialized: {self.db_path}")

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection with WAL mode."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- Repository CRUD ---

    def upsert_repo(self, repo: dict[str, Any]) -> bool:
        """Insert or update a repository. Returns True if new."""
        now = datetime.now(tz=UTC).isoformat()
        full_name = repo["full_name"]

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT full_name FROM repositories WHERE full_name = ?",
                (full_name,),
            ).fetchone()

            if existing:
                # Update
                conn.execute(
                    """UPDATE repositories SET
                        url = ?,
                        description = ?,
                        homepage = ?,
                        language = ?,
                        license = ?,
                        topics = ?,
                        owner_login = ?,
                        owner_avatar = ?,
                        status = ?,
                        pushed_at = ?,
                        stars = ?,
                        forks = ?,
                        open_issues = ?,
                        watchers = ?,
                        default_branch = ?
                    WHERE full_name = ?""",
                    (
                        repo.get("url", ""),
                        repo.get("description", ""),
                        repo.get("homepage", ""),
                        repo.get("language"),
                        repo.get("license"),
                        json.dumps(repo.get("topics", [])),
                        repo.get("owner_login", ""),
                        repo.get("owner_avatar", ""),
                        "archived" if repo.get("is_archived") else "active",
                        repo.get("pushed_at"),
                        repo.get("stars", 0),
                        repo.get("forks", 0),
                        repo.get("open_issues", 0),
                        repo.get("watchers", 0),
                        repo.get("default_branch", "main"),
                        full_name,
                    ),
                )
                return False
            else:
                # Insert
                conn.execute(
                    """INSERT INTO repositories
                        (full_name, url, description, homepage, language, license,
                         topics, owner_login, owner_avatar, status, created_at,
                         pushed_at, discovered_at, discovery_sources,
                         stars, forks, open_issues, watchers, default_branch)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?)""",
                    (
                        full_name,
                        repo.get("url", ""),
                        repo.get("description", ""),
                        repo.get("homepage", ""),
                        repo.get("language"),
                        repo.get("license"),
                        json.dumps(repo.get("topics", [])),
                        repo.get("owner_login", ""),
                        repo.get("owner_avatar", ""),
                        "archived" if repo.get("is_archived") else "active",
                        repo.get("created_at"),
                        repo.get("pushed_at"),
                        now,
                        json.dumps(repo.get("discovery_sources", [])),
                        repo.get("stars", 0),
                        repo.get("forks", 0),
                        repo.get("open_issues", 0),
                        repo.get("watchers", 0),
                        repo.get("default_branch", "main"),
                    ),
                )
                return True

    def upsert_repos(self, repos: list[dict[str, Any]]) -> tuple[int, int]:
        """Batch upsert repositories. Returns (new_count, updated_count)."""
        new = 0
        updated = 0
        now = datetime.now(tz=UTC).isoformat()

        with self._conn() as conn:
            # Get existing names
            existing_rows = conn.execute(
                "SELECT full_name FROM repositories"
            ).fetchall()
            existing_names = {r["full_name"] for r in existing_rows}

            # Batch insert new repos
            new_repos = []
            for repo in repos:
                fn = repo.get("full_name", "")
                if fn in existing_names:
                    # Update
                    conn.execute(
                        """UPDATE repositories SET
                            url=?, description=?, homepage=?, language=?,
                            license=?, topics=?, owner_login=?, owner_avatar=?,
                            status=?, pushed_at=?, stars=?, forks=?,
                            open_issues=?, watchers=?, default_branch=?
                        WHERE full_name=?""",
                        (
                            repo.get("url", ""),
                            repo.get("description", ""),
                            repo.get("homepage", ""),
                            repo.get("language"),
                            repo.get("license"),
                            json.dumps(repo.get("topics", [])),
                            repo.get("owner_login", ""),
                            repo.get("owner_avatar", ""),
                            "archived" if repo.get("is_archived") else "active",
                            repo.get("pushed_at"),
                            repo.get("stars", 0),
                            repo.get("forks", 0),
                            repo.get("open_issues", 0),
                            repo.get("watchers", 0),
                            repo.get("default_branch", "main"),
                            fn,
                        ),
                    )
                    updated += 1
                else:
                    new_repos.append(repo)
                    new += 1

            # Batch insert new repos (filter out any that snuck into both lists)
            truly_new = [r for r in new_repos if r.get("full_name", "") not in existing_names]
            if truly_new:
                conn.executemany(
                    """INSERT OR REPLACE INTO repositories
                        (full_name, url, description, homepage, language, license,
                         topics, owner_login, owner_avatar, status, created_at,
                         pushed_at, discovered_at, discovery_sources,
                         stars, forks, open_issues, watchers, default_branch)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?)""",
                    [
                        (
                            r.get("full_name", ""),
                            r.get("url", ""),
                            r.get("description", ""),
                            r.get("homepage", ""),
                            r.get("language"),
                            r.get("license"),
                            json.dumps(r.get("topics", [])),
                            r.get("owner_login", ""),
                            r.get("owner_avatar", ""),
                            "archived" if r.get("is_archived") else "active",
                            r.get("created_at"),
                            r.get("pushed_at"),
                            now,
                            json.dumps(r.get("discovery_sources", [])),
                            r.get("stars", 0),
                            r.get("forks", 0),
                            r.get("open_issues", 0),
                            r.get("watchers", 0),
                            r.get("default_branch", "main"),
                        )
                        for r in truly_new
                    ],
                )

        return new, updated

    def get_repo(self, full_name: str) -> dict[str, Any] | None:
        """Get a single repository."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM repositories WHERE full_name = ?", (full_name,)
            ).fetchone()
            return dict(row) if row else None

    def get_all_repos(self) -> list[dict[str, Any]]:
        """Get all repositories sorted by stars."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM repositories ORDER BY stars DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_repo_count(self) -> int:
        """Get total repository count."""
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]

    # --- Snapshots ---

    def save_snapshot(
        self, repo_full_name: str, snapshot: dict[str, Any]
    ) -> bool:
        """Save a snapshot for a repository. Returns True if new."""
        timestamp = snapshot.get("timestamp", datetime.now(tz=UTC).isoformat())
        with self._conn() as conn:
            try:
                conn.execute(
                    """INSERT INTO snapshots
                        (repo_full_name, timestamp, stars, forks, open_issues,
                         closed_issues, pull_requests, contributors, commits_7d,
                         commits_30d, releases, latest_release, latest_release_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        repo_full_name,
                        timestamp,
                        snapshot.get("stars", 0),
                        snapshot.get("forks", 0),
                        snapshot.get("open_issues", 0),
                        snapshot.get("closed_issues", 0),
                        snapshot.get("pull_requests", 0),
                        snapshot.get("contributors", 0),
                        snapshot.get("commits_7d", 0),
                        snapshot.get("commits_30d", 0),
                        snapshot.get("releases", 0),
                        snapshot.get("latest_release"),
                        snapshot.get("latest_release_date"),
                    ),
                )
                return True
            except sqlite3.IntegrityError:
                # Duplicate — update existing
                conn.execute(
                    """UPDATE snapshots SET
                        stars = ?, forks = ?, open_issues = ?,
                        contributors = ?, releases = ?
                    WHERE repo_full_name = ? AND timestamp = ?""",
                    (
                        snapshot.get("stars", 0),
                        snapshot.get("forks", 0),
                        snapshot.get("open_issues", 0),
                        snapshot.get("contributors", 0),
                        snapshot.get("releases", 0),
                        repo_full_name,
                        timestamp,
                    ),
                )
                return False

    def get_snapshots(
        self, repo_full_name: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        """Get recent snapshots for a repository."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM snapshots
                WHERE repo_full_name = ?
                ORDER BY timestamp DESC
                LIMIT ?""",
                (repo_full_name, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_latest_snapshot(self, repo_full_name: str) -> dict[str, Any] | None:
        """Get the most recent snapshot for a repository."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM snapshots
                WHERE repo_full_name = ?
                ORDER BY timestamp DESC LIMIT 1""",
                (repo_full_name,),
            ).fetchone()
            return dict(row) if row else None

    def get_snapshot_dates(self) -> list[str]:
        """Get all unique snapshot dates, sorted."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT DISTINCT SUBSTR(timestamp, 1, 10) as date
                FROM snapshots ORDER BY date"""
            ).fetchall()
            return [r["date"] for r in rows]

    # --- Scores ---

    def save_score(self, score: dict[str, Any]) -> None:
        """Save a score for a repository."""
        self.save_scores_batch([score])

    def save_scores_batch(self, scores: list[dict[str, Any]]) -> None:
        """Batch insert scores in a single transaction."""
        if not scores:
            return
        with self._conn() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO scores
                    (repo_full_name, timestamp, impact, velocity, health,
                     radar_score, global_percentile, category_percentile)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        s["repo_full_name"],
                        s.get("timestamp", datetime.now(tz=UTC).isoformat()),
                        s.get("impact", 0.0),
                        s.get("velocity", 0.0),
                        s.get("health", 0.0),
                        s.get("radar_score", 0.0),
                        s.get("global_percentile", 0.0),
                        s.get("category_percentile", 0.0),
                    )
                    for s in scores
                ],
            )

    def get_top_repos(
        self, n: int = 50, order_by: str = "radar_score"
    ) -> list[dict[str, Any]]:
        """Get top N repos by score."""
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT s.*,
                       r.full_name, r.description, r.language, r.url, r.topics,
                       r.stars, r.forks, r.open_issues, r.owner_login, r.owner_avatar,
                       r.created_at, r.pushed_at,
                       a.category, a.sub_category, a.maturity, a.quality, a.potential
                FROM scores s
                JOIN repositories r ON s.repo_full_name = r.full_name
                LEFT JOIN ai_analysis a ON s.repo_full_name = a.repo_full_name
                WHERE s.timestamp = (SELECT MAX(timestamp) FROM scores)
                ORDER BY s.{order_by} DESC
                LIMIT ?""",
                (n,),
            ).fetchall()
            return [dict(r) for r in rows]

    # --- Growth Metrics ---

    def save_growth(self, growth: dict[str, Any]) -> None:
        """Save growth metrics for a repository."""
        timestamp = growth.get(
            "timestamp", datetime.now(tz=UTC).isoformat()
        )
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO growth_metrics
                    (repo_full_name, timestamp, stars_7d, stars_30d, stars_90d,
                     star_growth_rate_7d, star_growth_rate_30d,
                     star_growth_acceleration, forks_7d, forks_30d,
                     contributors_7d, days_since_last_push, freshness_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    growth["repo_full_name"],
                    timestamp,
                    growth.get("stars_7d", 0),
                    growth.get("stars_30d", 0),
                    growth.get("stars_90d", 0),
                    growth.get("star_growth_rate_7d", 0.0),
                    growth.get("star_growth_rate_30d", 0.0),
                    growth.get("star_growth_acceleration", 0.0),
                    growth.get("forks_7d", 0),
                    growth.get("forks_30d", 0),
                    growth.get("contributors_7d", 0),
                    growth.get("days_since_last_push", 0),
                    growth.get("freshness_score", 0.0),
                ),
            )

    # --- AI Analysis ---

    def save_analysis(self, analysis: dict[str, Any]) -> None:
        """Save AI analysis results for a repository."""
        timestamp = analysis.get("timestamp", datetime.now(tz=UTC).isoformat())
        fn = analysis["repo_full_name"]

        # Serialize lists to JSON
        tech_stack = analysis.get("tech_stack", [])
        use_cases = analysis.get("use_cases", [])
        if isinstance(tech_stack, list):
            tech_stack = json.dumps(tech_stack)
        if isinstance(use_cases, list):
            use_cases = json.dumps(use_cases)

        with self._conn() as conn:
            # Check if analysis exists for this repo
            existing = conn.execute(
                "SELECT id FROM ai_analysis WHERE repo_full_name = ?",
                (fn,),
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE ai_analysis SET
                        timestamp=?, category=?, sub_category=?, summary=?,
                        tech_stack=?, use_cases=?, maturity=?, quality=?,
                        potential=?, confidence=?, matched_by=?
                    WHERE repo_full_name=?""",
                    (
                        timestamp,
                        analysis.get("category", ""),
                        analysis.get("sub_category", ""),
                        analysis.get("summary", ""),
                        tech_stack,
                        use_cases,
                        analysis.get("maturity", "Unknown"),
                        analysis.get("quality", 0.0),
                        analysis.get("potential", 0.0),
                        analysis.get("confidence", 0.0),
                        analysis.get("matched_by", "none"),
                        fn,
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO ai_analysis
                        (repo_full_name, timestamp, category, sub_category,
                         summary, tech_stack, use_cases, maturity, quality,
                         potential, confidence, matched_by)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        fn,
                        timestamp,
                        analysis.get("category", ""),
                        analysis.get("sub_category", ""),
                        analysis.get("summary", ""),
                        tech_stack,
                        use_cases,
                        analysis.get("maturity", "Unknown"),
                        analysis.get("quality", 0.0),
                        analysis.get("potential", 0.0),
                        analysis.get("confidence", 0.0),
                        analysis.get("matched_by", "none"),
                    ),
                )

    # --- Stats ---

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        with self._conn() as conn:
            repo_count = conn.execute(
                "SELECT COUNT(*) FROM repositories"
            ).fetchone()[0]
            snapshot_count = conn.execute(
                "SELECT COUNT(*) FROM snapshots"
            ).fetchone()[0]
            score_count = conn.execute(
                "SELECT COUNT(*) FROM scores"
            ).fetchone()[0]
            total_stars = conn.execute(
                "SELECT COALESCE(SUM(stars), 0) FROM repositories"
            ).fetchone()[0]
            snapshot_dates = conn.execute(
                """SELECT DISTINCT SUBSTR(timestamp, 1, 10) as date
                FROM snapshots ORDER BY date DESC LIMIT 5"""
            ).fetchall()

            # Language distribution
            lang_rows = conn.execute(
                """SELECT language, COUNT(*) as count
                FROM repositories WHERE language IS NOT NULL
                GROUP BY language ORDER BY count DESC LIMIT 10"""
            ).fetchall()

            analyzed_count = conn.execute(
                "SELECT COUNT(*) FROM ai_analysis"
            ).fetchone()[0]

            return {
                "repos": repo_count,
                "snapshots": snapshot_count,
                "scores": score_count,
                "analyzed": analyzed_count,
                "total_stars": total_stars,
                "snapshot_dates": [r["date"] for r in snapshot_dates],
                "languages": {r["language"]: r["count"] for r in lang_rows},
            }
