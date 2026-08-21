"""Discovery telemetry — tracks per-query and run-level metrics.

Designed for future parallelization:
- query_started / query_finished / query_failed / retry are structured events
- Thread-safe via simple counters (asyncio is single-threaded anyway)
- Run summary computed from accumulated events
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QueryMetric:
    """Metrics for a single query execution."""

    query: str
    category: str
    layer: str
    started_at: float = 0.0
    finished_at: float = 0.0
    duration: float = 0.0
    success: bool = False
    repos_returned: int = 0
    retries: int = 0
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class RunSummary:
    """Aggregated metrics for a full discovery run."""

    # Query counts
    queries_attempted: int = 0
    queries_successful: int = 0
    queries_failed: int = 0
    total_retries: int = 0

    # Repository counts
    repos_returned: int = 0
    repos_unique: int = 0
    duplicates_removed: int = 0

    # Performance
    total_duration: float = 0.0
    avg_query_duration: float = 0.0
    slowest_query_duration: float = 0.0
    slowest_query: str = ""

    # Rate limit
    rate_remaining: int = 0
    rate_reset_at: str = ""

    # Errors by type
    errors_by_type: dict[str, int] = field(default_factory=dict)

    # Per-query details (debug logging)
    query_details: list[QueryMetric] = field(default_factory=list)


class DiscoveryTelemetry:
    """Tracks discovery pipeline metrics.

    Usage:
        telemetry = DiscoveryTelemetry()
        telemetry.query_started("topic:ai-agent stars:>10", "ai-agents", "topic")

        # ... execute query ...

        if success:
            telemetry.query_finished(repos_returned=50)
        else:
            telemetry.query_failed("RESOURCE_LIMITS_EXCEEDED", "Resource limits exceeded")

        summary = telemetry.finalize(unique_repos=5271)
        telemetry.log_summary(summary)
    """

    def __init__(self) -> None:
        self._queries: list[QueryMetric] = []
        self._current_query: QueryMetric | None = None
        self._run_start: float = time.time()
        self._rate_remaining: int = 0
        self._rate_reset_at: str = ""

    def query_started(self, query: str, category: str, layer: str) -> None:
        """Mark a query as started."""
        self._current_query = QueryMetric(
            query=query,
            category=category,
            layer=layer,
            started_at=time.time(),
        )
        logger.debug(f"QUERY_START [{len(self._queries) + 1}] {query}")

    def query_finished(self, repos_returned: int = 0) -> None:
        """Mark current query as successfully finished."""
        if not self._current_query:
            return

        q = self._current_query
        q.finished_at = time.time()
        q.duration = q.finished_at - q.started_at
        q.success = True
        q.repos_returned = repos_returned
        self._queries.append(q)
        logger.debug(
            f"QUERY_OK [{len(self._queries)}] {q.query} "
            f"→ {repos_returned} repos in {q.duration:.1f}s"
        )
        self._current_query = None

    def query_failed(self, error_type: str, error_message: str = "") -> None:
        """Mark current query as failed."""
        if not self._current_query:
            return

        q = self._current_query
        q.finished_at = time.time()
        q.duration = q.finished_at - q.started_at
        q.success = False
        q.error_type = error_type
        q.error_message = error_message
        self._queries.append(q)
        logger.debug(
            f"QUERY_FAIL [{len(self._queries)}] {q.query} "
            f"→ {error_type} in {q.duration:.1f}s"
        )
        self._current_query = None

    def retry(self) -> None:
        """Increment retry counter for current query."""
        if self._current_query:
            self._current_query.retries += 1
            logger.debug(
                f"RETRY [{len(self._queries) + 1}] "
                f"{self._current_query.query} "
                f"(attempt {self._current_query.retries})"
            )

    def update_rate_limit(self, remaining: int, reset_at: str) -> None:
        """Update rate limit state from API response."""
        self._rate_remaining = remaining
        self._rate_reset_at = reset_at

    def finalize(self, unique_repos: int = 0) -> RunSummary:
        """Compute final run summary."""
        total_duration = time.time() - self._run_start

        attempted = len(self._queries)
        successful = sum(1 for q in self._queries if q.success)
        failed = attempted - successful
        total_retries = sum(q.retries for q in self._queries)

        repos_returned = sum(q.repos_returned for q in self._queries)

        durations = [q.duration for q in self._queries if q.duration > 0]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        slowest_q = max(self._queries, key=lambda q: q.duration) if self._queries else None

        # Count errors by type
        errors_by_type: dict[str, int] = {}
        for q in self._queries:
            if q.error_type:
                errors_by_type[q.error_type] = errors_by_type.get(q.error_type, 0) + 1

        return RunSummary(
            queries_attempted=attempted,
            queries_successful=successful,
            queries_failed=failed,
            total_retries=total_retries,
            repos_returned=repos_returned,
            repos_unique=unique_repos,
            duplicates_removed=repos_returned - unique_repos if repos_returned > unique_repos else 0,
            total_duration=total_duration,
            avg_query_duration=avg_duration,
            slowest_query_duration=slowest_q.duration if slowest_q else 0.0,
            slowest_query=slowest_q.query if slowest_q else "",
            rate_remaining=self._rate_remaining,
            rate_reset_at=self._rate_reset_at,
            errors_by_type=errors_by_type,
            query_details=self._queries,
        )

    def log_summary(self, summary: RunSummary) -> None:
        """Log a concise run summary."""
        # Format duration
        mins = int(summary.total_duration // 60)
        secs = int(summary.total_duration % 60)
        duration_str = f"{mins}m {secs:02d}s"

        # Format slowest
        slowest_str = f"{summary.slowest_query_duration:.1f}s"

        # Format rate reset
        reset_str = summary.rate_reset_at or "N/A"
        if reset_str != "N/A":
            try:
                reset_dt = datetime.fromisoformat(reset_str.replace("Z", "+00:00"))
                reset_str = reset_dt.strftime("%H:%M UTC")
            except (ValueError, AttributeError):
                pass

        # Format errors
        error_lines = []
        for err_type, count in sorted(summary.errors_by_type.items()):
            error_lines.append(f"  {err_type:<24} {count:>4}")

        errors_section = "\n".join(error_lines) if error_lines else "  (none)"

        # Build summary
        msg = f"""
{'━' * 48}
RADAR DISCOVERY RUN
{'━' * 48}
Queries:
  attempted:          {summary.queries_attempted:>6}
  successful:         {summary.queries_successful:>6}
  failed:             {summary.queries_failed:>6}
  retries:            {summary.total_retries:>6}

Repositories:
  returned:           {summary.repos_returned:>6,}
  unique:             {summary.repos_unique:>6,}
  duplicates:         {summary.duplicates_removed:>6,}

Performance:
  duration:           {duration_str:>10}
  avg query:          {summary.avg_query_duration:.1f}s
  slowest:            {slowest_str}

GraphQL:
  rate remaining:     {summary.rate_remaining:>6}
  reset:              {reset_str:>10}

Errors:
{errors_section}
{'━' * 48}"""

        logger.info(msg)
