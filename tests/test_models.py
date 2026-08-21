"""Tests for core data models."""

from datetime import UTC, datetime

from radar.models import (
    AIAnalysis,
    Category,
    CategoryMomentum,
    GrowthMetrics,
    Repository,
    Score,
    Snapshot,
)


def test_repository_creation():
    """Test creating a repository model."""
    repo = Repository(
        full_name="test/repo",
        url="https://github.com/test/repo",
        description="A test repo",
        language="Python",
        stars=1000,
        forks=200,
        topics=["ai", "llm"],
    )
    assert repo.full_name == "test/repo"
    assert repo.stars == 1000
    assert repo.forks == 200
    assert "ai" in repo.topics


def test_snapshot_creation():
    """Test creating a snapshot."""
    snap = Snapshot(
        repo_full_name="test/repo",
        timestamp=datetime.now(tz=UTC),
        stars=1000,
        forks=200,
        open_issues=50,
        contributors=15,
        commits_7d=42,
        releases=3,
    )
    assert snap.stars == 1000
    assert snap.commits_7d == 42


def test_score_creation():
    """Test creating a score."""
    score = Score(
        repo_full_name="test/repo",
        timestamp=datetime.now(tz=UTC),
        impact=80.0,
        velocity=70.0,
        health=90.0,
        radar_score=79.5,  # 80*0.4 + 70*0.35 + 90*0.25
    )
    assert score.impact == 80.0
    assert score.radar_score == 79.5


def test_growth_metrics():
    """Test growth metrics model."""
    growth = GrowthMetrics(
        repo_full_name="test/repo",
        timestamp=datetime.now(tz=UTC),
        stars_7d=500,
        stars_30d=1500,
        star_growth_rate_7d=71.4,
        star_growth_rate_30d=50.0,
        star_growth_acceleration=1.43,
        freshness_score=0.95,
    )
    assert growth.stars_7d == 500
    assert growth.freshness_score == 0.95


def test_category():
    """Test category model."""
    cat = Category(
        slug="ai-agents",
        name="AI Agents",
        topics=["ai-agent", "autonomous-agent"],
        keywords=["AI agent framework"],
    )
    assert cat.slug == "ai-agents"
    assert len(cat.topics) == 2


def test_category_momentum():
    """Test category momentum model."""
    mom = CategoryMomentum(
        category_slug="ai-agents",
        week="2026-W34",
        total_tracked=150,
        new_this_week=12,
        avg_growth_rate=340.0,
        trend="rising",
    )
    assert mom.total_tracked == 150
    assert mom.trend == "rising"


def test_ai_analysis():
    """Test AI analysis model."""
    analysis = AIAnalysis(
        repo_full_name="test/repo",
        timestamp=datetime.now(tz=UTC),
        category="AI Agents",
        sub_category="Coding Agent",
        summary="A coding agent framework",
        tech_stack=["Python", "TypeScript"],
        use_cases=["code generation", "pair programming"],
        maturity="Growing",
        quality=85.0,
        potential=92.0,
    )
    assert analysis.category == "AI Agents"
    assert "Python" in analysis.tech_stack
    assert analysis.potential == 92.0
