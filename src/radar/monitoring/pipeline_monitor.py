"""Pipeline Health Monitor — tracks system health and data freshness.

Monitors:
- Data freshness (when was last snapshot/score/discovery)
- Pipeline completeness (are all stages running?)
- Error rates (failed repos, API errors)
- Processing statistics (how many repos processed)
- Database health (table sizes, integrity)

Outputs health status for display on website and in reports.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from radar.storage.database import Database

logger = logging.getLogger(__name__)


class PipelineMonitor:
    """Tracks pipeline health and data freshness."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_health_report(self) -> dict[str, Any]:
        """Generate a comprehensive health report."""
        report = {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "overall_status": "healthy",
            "checks": [],
        }

        # Run all health checks
        checks = [
            self._check_data_freshness(),
            self._check_snapshot_coverage(),
            self._check_scoring_coverage(),
            self._check_category_coverage(),
            self._check_database_health(),
            self._check_processing_stats(),
        ]

        for check in checks:
            report["checks"].append(check)
            if check["status"] == "critical":
                report["overall_status"] = "critical"
            elif check["status"] == "warning" and report["overall_status"] == "healthy":
                report["overall_status"] = "warning"

        return report

    def _check_data_freshness(self) -> dict[str, Any]:
        """Check if data is fresh (updated within expected window)."""
        with self.db._conn() as conn:
            # Last snapshot
            last_snap = conn.execute(
                "SELECT MAX(timestamp) as ts FROM snapshots"
            ).fetchone()["ts"]

            # Last score
            last_score = conn.execute(
                "SELECT MAX(timestamp) as ts FROM scores"
            ).fetchone()["ts"]

            # Last discovery (new repos added)
            last_disc = conn.execute(
                "SELECT MAX(discovered_at) as ts FROM repositories"
            ).fetchone()["ts"]

        now = datetime.now(tz=UTC)
        issues = []

        # Check snapshot freshness (should be within 48 hours)
        if last_snap:
            snap_age = self._hours_since(last_snap, now)
            if snap_age > 48:
                issues.append(f"Snapshots are {snap_age:.0f}h old (expected < 48h)")
                status = "warning"
            elif snap_age > 72:
                status = "critical"
            else:
                status = "healthy"
        else:
            issues.append("No snapshots found")
            status = "critical"

        # Check scoring freshness
        if last_score:
            score_age = self._hours_since(last_score, now)
            if score_age > 48:
                issues.append(f"Scores are {score_age:.0f}h old")
                if status != "critical":
                    status = "warning"
        else:
            issues.append("No scores found")
            status = "critical"

        return {
            "name": "Data Freshness",
            "status": status,
            "last_snapshot": last_snap,
            "last_score": last_score,
            "last_discovery": last_disc,
            "issues": issues,
        }

    def _check_snapshot_coverage(self) -> dict[str, Any]:
        """Check what percentage of repos have snapshots."""
        with self.db._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
            snapshotted = conn.execute(
                """SELECT COUNT(DISTINCT repo_full_name) FROM snapshots"""
            ).fetchone()[0]

        coverage = (snapshotted / total * 100) if total > 0 else 0

        if coverage < 50:
            status = "warning"
            issues = [f"Only {coverage:.1f}% of repos have snapshots"]
        elif coverage < 10:
            status = "critical"
            issues = [f"Very low snapshot coverage: {coverage:.1f}%"]
        else:
            status = "healthy"
            issues = []

        return {
            "name": "Snapshot Coverage",
            "status": status,
            "total_repos": total,
            "snapshotted": snapshotted,
            "coverage_pct": round(coverage, 1),
            "issues": issues,
        }

    def _check_scoring_coverage(self) -> dict[str, Any]:
        """Check what percentage of repos have scores."""
        with self.db._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
            scored = conn.execute(
                """SELECT COUNT(DISTINCT repo_full_name) FROM scores
                WHERE timestamp = (SELECT MAX(timestamp) FROM scores)"""
            ).fetchone()[0]

        coverage = (scored / total * 100) if total > 0 else 0

        if coverage < 80:
            status = "warning"
            issues = [f"Only {coverage:.1f}% of repos have scores"]
        else:
            status = "healthy"
            issues = []

        return {
            "name": "Scoring Coverage",
            "status": status,
            "total_repos": total,
            "scored": scored,
            "coverage_pct": round(coverage, 1),
            "issues": issues,
        }

    def _check_category_coverage(self) -> dict[str, Any]:
        """Check what percentage of repos are classified."""
        with self.db._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
            classified = conn.execute(
                """SELECT COUNT(*) FROM ai_analysis WHERE category != ''"""
            ).fetchone()[0]

        coverage = (classified / total * 100) if total > 0 else 0

        if coverage < 50:
            status = "warning"
            issues = [f"Only {coverage:.1f}% of repos are classified"]
        else:
            status = "healthy"
            issues = []

        return {
            "name": "Category Coverage",
            "status": status,
            "total_repos": total,
            "classified": classified,
            "coverage_pct": round(coverage, 1),
            "issues": issues,
        }

    def _check_database_health(self) -> dict[str, Any]:
        """Check database size and integrity."""
        with self.db._conn() as conn:
            # Table sizes
            tables = {}
            for table in ["repositories", "snapshots", "scores", "growth_metrics", "ai_analysis"]:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                tables[table] = count

            # Check for orphaned records
            orphaned_snaps = conn.execute(
                """SELECT COUNT(*) FROM snapshots s
                WHERE NOT EXISTS (
                    SELECT 1 FROM repositories r
                    WHERE r.full_name = s.repo_full_name)"""
            ).fetchone()[0]

        issues = []
        if orphaned_snaps > 0:
            issues.append(f"{orphaned_snaps} orphaned snapshots")

        status = "healthy" if not issues else "warning"

        return {
            "name": "Database Health",
            "status": status,
            "table_sizes": tables,
            "issues": issues,
        }

    def _check_processing_stats(self) -> dict[str, Any]:
        """Check incremental processing statistics."""
        try:
            from radar.processing.change_detector import ChangeDetector
            detector = ChangeDetector(self.db)
            stats = detector.get_stats()

            total = stats.get("total_repos", 0)
            processed = stats.get("processed", 0)
            coverage = (processed / total * 100) if total > 0 else 0

            if coverage < 50:
                status = "warning"
                issues = [f"Only {coverage:.1f}% of repos have processing signatures"]
            else:
                status = "healthy"
                issues = []

            return {
                "name": "Processing Stats",
                "status": status,
                "total_repos": total,
                "processed": processed,
                "unprocessed": stats.get("unprocessed", 0),
                "last_run": stats.get("last_run"),
                "issues": issues,
            }
        except Exception as e:
            return {
                "name": "Processing Stats",
                "status": "unknown",
                "issues": [f"Could not check: {e}"],
            }

    def _hours_since(self, iso_str: str, now: datetime) -> float:
        """Calculate hours since an ISO timestamp."""
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return (now - dt).total_seconds() / 3600
        except (ValueError, AttributeError):
            return 9999

    def get_status_summary(self) -> dict[str, Any]:
        """Get a simple status summary for quick checks."""
        report = self.get_health_report()

        return {
            "status": report["overall_status"],
            "checks_total": len(report["checks"]),
            "checks_healthy": sum(1 for c in report["checks"] if c["status"] == "healthy"),
            "checks_warning": sum(1 for c in report["checks"] if c["status"] == "warning"),
            "checks_critical": sum(1 for c in report["checks"] if c["status"] == "critical"),
        }
