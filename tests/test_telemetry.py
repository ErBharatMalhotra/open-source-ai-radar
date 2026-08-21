"""Tests for discovery telemetry module."""

from __future__ import annotations

import time
from unittest.mock import patch

from radar.discovery.telemetry import DiscoveryTelemetry, QueryMetric, RunSummary


class TestQueryMetric:
    def test_creation(self):
        q = QueryMetric(query="test", category="cat", layer="topic")
        assert q.query == "test"
        assert q.category == "cat"
        assert q.layer == "topic"
        assert q.success is False
        assert q.repos_returned == 0
        assert q.retries == 0

    def test_with_data(self):
        q = QueryMetric(
            query="topic:ai-agent",
            category="ai-agents",
            layer="topic",
            started_at=100.0,
            finished_at=105.0,
            duration=5.0,
            success=True,
            repos_returned=50,
            retries=1,
        )
        assert q.duration == 5.0
        assert q.repos_returned == 50


class TestRunSummary:
    def test_defaults(self):
        s = RunSummary()
        assert s.queries_attempted == 0
        assert s.queries_successful == 0
        assert s.total_retries == 0
        assert s.repos_returned == 0
        assert s.errors_by_type == {}


class TestDiscoveryTelemetry:
    def test_empty_run(self):
        t = DiscoveryTelemetry()
        summary = t.finalize(unique_repos=0)
        assert summary.queries_attempted == 0
        assert summary.total_duration >= 0

    def test_single_query_success(self):
        t = DiscoveryTelemetry()
        t.query_started("topic:ai-agent", "ai-agents", "topic")
        t.query_finished(repos_returned=50)
        summary = t.finalize(unique_repos=45)
        assert summary.queries_attempted == 1
        assert summary.queries_successful == 1
        assert summary.queries_failed == 0
        assert summary.repos_returned == 50
        assert summary.repos_unique == 45
        assert summary.duplicates_removed == 5

    def test_multiple_queries(self):
        t = DiscoveryTelemetry()
        for i in range(5):
            t.query_started(f"query_{i}", "cat", "layer")
            t.query_finished(repos_returned=10)
        summary = t.finalize(unique_repos=40)
        assert summary.queries_attempted == 5
        assert summary.repos_returned == 50
        assert summary.repos_unique == 40
        assert summary.duplicates_removed == 10

    def test_failed_query(self):
        t = DiscoveryTelemetry()
        t.query_started("query1", "cat", "layer")
        t.query_finished(repos_returned=10)
        t.query_started("query2", "cat", "layer")
        t.query_failed("RESOURCE_LIMITS_EXCEEDED", "Resource limits exceeded")
        summary = t.finalize(unique_repos=10)
        assert summary.queries_attempted == 2
        assert summary.queries_successful == 1
        assert summary.queries_failed == 1
        assert summary.errors_by_type.get("RESOURCE_LIMITS_EXCEEDED") == 1

    def test_retries(self):
        t = DiscoveryTelemetry()
        t.query_started("query1", "cat", "layer")
        t.retry()
        t.retry()
        t.query_finished(repos_returned=10)
        summary = t.finalize(unique_repos=10)
        assert summary.total_retries == 2

    def test_rate_limit_tracking(self):
        t = DiscoveryTelemetry()
        t.update_rate_limit(remaining=800, reset_at="2026-08-21T12:00:00Z")
        summary = t.finalize(unique_repos=0)
        assert summary.rate_remaining == 800
        assert summary.rate_reset_at == "2026-08-21T12:00:00Z"

    def test_query_duration_tracking(self):
        t = DiscoveryTelemetry()
        with patch("radar.discovery.telemetry.time") as mock_time:
            mock_time.time.side_effect = [100.0, 105.0, 100.0, 102.0, 100.0]
            t.query_started("q1", "cat", "layer")
            t.query_finished(repos_returned=10)
            t.query_started("q2", "cat", "layer")
            t.query_finished(repos_returned=20)
        summary = t.finalize(unique_repos=30)
        assert summary.avg_query_duration > 0

    def test_slowest_query(self):
        t = DiscoveryTelemetry()
        with patch("radar.discovery.telemetry.time") as mock_time:
            mock_time.time.side_effect = [100.0, 103.0, 100.0, 110.0, 100.0]
            t.query_started("fast_query", "cat", "layer")
            t.query_finished(repos_returned=10)
            t.query_started("slow_query", "cat", "layer")
            t.query_finished(repos_returned=20)
        summary = t.finalize(unique_repos=30)
        assert summary.slowest_query == "slow_query"

    def test_error_type_counting(self):
        t = DiscoveryTelemetry()
        for err_type in ["RESOURCE_LIMITS_EXCEEDED", "502", "RESOURCE_LIMITS_EXCEEDED"]:
            t.query_started("q", "cat", "layer")
            t.query_failed(err_type, "error")
        summary = t.finalize(unique_repos=0)
        assert summary.errors_by_type["RESOURCE_LIMITS_EXCEEDED"] == 2
        assert summary.errors_by_type["502"] == 1
