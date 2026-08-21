"""Core data models for Open Source AI Radar."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RepoStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    FORK = "fork"
    INACTIVE = "inactive"


class Repository(BaseModel):
    """A tracked open-source repository."""

    full_name: str  # owner/name — primary key
    url: str
    description: str = ""
    homepage: str = ""
    language: str | None = None
    license: str | None = None
    topics: list[str] = Field(default_factory=list)
    status: RepoStatus = RepoStatus.ACTIVE

    owner_login: str = ""
    owner_avatar: str = ""

    # Timestamps
    created_at: datetime | None = None
    pushed_at: datetime | None = None
    discovered_at: datetime | None = None
    last_analyzed_at: datetime | None = None

    # Discovery metadata
    discovery_sources: list[str] = Field(default_factory=list)

    # Latest snapshot values (denormalized for quick access)
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    watchers: int = 0
    default_branch: str = "main"


class Snapshot(BaseModel):
    """A point-in-time capture of repository metrics."""

    repo_full_name: str
    timestamp: datetime

    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    closed_issues: int = 0
    pull_requests: int = 0
    contributors: int = 0
    commits_7d: int = 0
    commits_30d: int = 0
    releases: int = 0
    latest_release: str | None = None
    latest_release_date: datetime | None = None


class GrowthMetrics(BaseModel):
    """Derived growth signals from snapshot history."""

    repo_full_name: str
    timestamp: datetime

    # Star growth
    stars_7d: int = 0
    stars_30d: int = 0
    stars_90d: int = 0
    star_growth_rate_7d: float = 0.0  # stars per day
    star_growth_rate_30d: float = 0.0
    star_growth_acceleration: float = 0.0  # rate_7d vs rate_30d

    # Fork growth
    forks_7d: int = 0
    forks_30d: int = 0

    # Contributor growth
    contributors_7d: int = 0

    # Freshness
    days_since_last_push: int = 0
    freshness_score: float = 0.0  # 0-1, exponential decay


class Score(BaseModel):
    """Three-axis radar scoring for a repository."""

    repo_full_name: str
    timestamp: datetime

    # Individual axes (0-100)
    impact: float = 0.0
    velocity: float = 0.0
    health: float = 0.0

    # Combined
    radar_score: float = 0.0

    # Percentile ranks
    global_percentile: float = 0.0
    category_percentile: float = 0.0


class AIAnalysis(BaseModel):
    """AI-generated analysis of a repository."""

    repo_full_name: str
    timestamp: datetime

    category: str = ""
    sub_category: str = ""
    summary: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    maturity: str = "Unknown"  # Emerging, Growing, Mature, Declining
    quality: float = 0.0  # 0-100
    potential: float = 0.0  # 0-100


class Category(BaseModel):
    """A tracked category of projects."""

    slug: str
    name: str
    description: str = ""
    topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    sub_categories: list[str] = Field(default_factory=list)


class CategoryMomentum(BaseModel):
    """Weekly momentum snapshot for a category."""

    category_slug: str
    week: str  # ISO week: "2026-W34"

    total_tracked: int = 0
    new_this_week: int = 0
    avg_stars: float = 0.0
    avg_growth_rate: float = 0.0
    top_project: str = ""
    trend: str = "stable"  # rising, stable, declining
