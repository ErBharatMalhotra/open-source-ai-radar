# Architecture

This document describes the system design, data flow, and rate limit strategy for Open Source AI Radar.

## System Overview

```
+------------------+     +------------------+     +------------------+
|   GitHub API     | --> |   Radar Backend  | --> |   Static Website |
|   (GraphQL/REST) |     |   (Python/SQLite)|     |   (Astro/GH Pgs)|
+------------------+     +------------------+     +------------------+
        ^                       |    ^                      |
        |                       v    |                      v
        |              +--------+    |              +-------+-------+
        |              | SQLite |    |              | JSON/CSV/RSS  |
        |              |   DB   |    |              |   Exports     |
        |              +--------+    |              +---------------+
        |                            |
        +--- Rate Limit Awareness ---+
```

## Data Flow

### Discovery Pipeline

```
1. GitHub Search API
   |
   v
2. Discovery Engine (search.py)
   - Builds queries from config/categories.yml
   - topic:{name} stars:>10
   - "keyword" stars:>5 created:>2025-01-01
   - Returns up to 1000 results per query (capped by GitHub)
   |
   v
3. Import to SQLite (import-json)
   - Deduplication by full_name
   - Quality filtering (min stars, not archived, not fork)
   - Stores in repositories table
   |
   v
4. Classification (classify)
   - Topic matching against categories.yml
   - Assigns primary category
   - Stores in ai_analysis table
```

### Processing Pipeline

```
1. Scheduler picks due repos
   |
   v
2. Snapshot (GitHub GraphQL API)
   - Fetches: stars, forks, issues, PRs, releases, contributors
   - One GraphQL query per repo
   - Stores in snapshots table
   |
   v
3. Change Detection (change_detector.py)
   - Computes processing signature from repo metrics
   - Skips repos that haven't changed since last run
   |
   v
4. Scoring (scoring/engine.py)
   - Impact: log-scaled percentile rank of stars/forks/watchers
   - Velocity: growth rate, acceleration, commit frequency
   - Health: freshness, releases, issue load, community shape,
     bus factor (maintainer count), license safety
   - Radar Score = Impact * 0.40 + Velocity * 0.35 + Health * 0.25
   |
   v
5. Analysis
   - Anomaly Detection: statistical outliers in growth
   - Breakout Detection: projects entering breakout territory
   - Why Trending: multi-signal explanation
   |
   v
6. Export (scripts/export.py)
   - JSON files for API endpoints
   - Project detail pages
   - SVG badges
   - RSS feed
   - CSV exports
```

### Website Pipeline

```
1. Astro builds static HTML from data
   - 9,000+ project pages
   - 13 main route pages (incl. /compare, /digests)
   - SEO metadata (OpenGraph, JSON-LD, sitemap)
   |
   v
2. GitHub Pages deploys
   - Push to gh-pages branch
   - CDN-served globally
```

## GitHub API Rate Limits

### Official Limits (docs.github.com)

```
GITHUB_TOKEN in Actions:
  REST API:  1,000 requests/hour per repository
  GraphQL:   1,000 points/hour per repository
  Secondary: 100 concurrent requests
             2,000 points/minute (GraphQL)
             900 points/minute (REST)
```

### Our Usage

| Operation | API Calls | Points | Time |
|-----------|-----------|--------|------|
| Discovery (11 categories, 4 layers, ~324 queries) | ~120 GraphQL | ~120 | ~11 min |
| Process (700 repos) | ~700 GraphQL | ~700 | ~10 min |
| **Total per run** | **~820** | **~820** | **~21 min** |

### Budget Allocation

```
Total budget:     1,000 points/hour
Safety margin:      800 points (80%)
Discovery reserve:  120 points
Process budget:     680 points (per run)
```

### Adaptive Rate Limiter

The `AdaptiveRateLimiter` in `src/radar/scale/rate_limiter.py`:

1. Tracks `x-ratelimit-remaining` from API responses
2. Increases delay as budget depletes (0.1s -> 2s)
3. Stops batch when budget < 200 points remaining
4. Waits for reset when rate limited (with timeout safety)

```python
# Delay calculation
ratio = used / budget  # 0.0 to 1.0
delay = 0.1 + (ratio * 2.0)  # 0.1s at start, 2s near limit
```

## Database Schema

Source of truth: `SCHEMA` in `src/radar/storage/database.py` (plus
`processing_cursor` created by `src/radar/scale/scheduler.py`).

### Core Tables

```sql
-- Repository metadata + denormalized latest values
CREATE TABLE repositories (
    full_name TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    description TEXT DEFAULT '',
    homepage TEXT DEFAULT '',
    language TEXT,
    license TEXT,
    topics TEXT DEFAULT '[]',          -- JSON array
    owner_login TEXT DEFAULT '',
    owner_avatar TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    created_at TEXT,
    pushed_at TEXT,
    discovered_at TEXT,
    last_analyzed_at TEXT,
    discovery_sources TEXT DEFAULT '[]',  -- JSON array
    stars INTEGER DEFAULT 0,
    forks INTEGER DEFAULT 0,
    open_issues INTEGER DEFAULT 0,
    watchers INTEGER DEFAULT 0,
    default_branch TEXT DEFAULT 'main',
    processing_signature TEXT DEFAULT '', -- incremental processing
    last_processed_at TEXT
);

-- Point-in-time snapshots (one per processed repo per run)
CREATE TABLE snapshots (
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

-- Three-axis scores (every run, every scored repo)
CREATE TABLE scores (
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

-- Growth metrics derived from snapshot deltas
CREATE TABLE growth_metrics (
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

-- AI analysis and classification (upserted per repo)
CREATE TABLE ai_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    category TEXT DEFAULT '',
    sub_category TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    why_trending TEXT DEFAULT '',
    tech_stack TEXT DEFAULT '[]',      -- JSON array
    use_cases TEXT DEFAULT '[]',       -- JSON array
    maturity TEXT DEFAULT 'Unknown',
    quality REAL DEFAULT 0.0,
    potential REAL DEFAULT 0.0,
    confidence REAL DEFAULT 0.0,
    matched_by TEXT DEFAULT 'none',    -- topic | keyword | none
    FOREIGN KEY (repo_full_name) REFERENCES repositories(full_name)
);
-- Enforced unique so upserts behave: idx_analysis_repo_unique

-- Category momentum history (per category per period)
CREATE TABLE category_momentum (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    total_tracked INTEGER DEFAULT 0,
    new_this_period INTEGER DEFAULT 0,
    avg_stars REAL DEFAULT 0.0,
    avg_growth_rate REAL DEFAULT 0.0,
    avg_velocity REAL DEFAULT 0.0,
    avg_health REAL DEFAULT 0.0,
    total_stars INTEGER DEFAULT 0,
    top_project TEXT DEFAULT '',
    trend TEXT DEFAULT 'stable',
    momentum_score REAL DEFAULT 0.0,
    UNIQUE(category, timestamp)
);

-- Processing scheduler (tier-based queue)
CREATE TABLE processing_cursor (
    repo_full_name TEXT PRIMARY KEY,
    tier INTEGER NOT NULL DEFAULT 4,
    last_processed_at TEXT,
    next_scheduled_at TEXT,
    processing_status TEXT DEFAULT 'pending',
    processing_attempts INTEGER DEFAULT 0,
    last_processing_error TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

### Performance Indexes

```sql
-- Scheduler queue queries
CREATE INDEX idx_cursor_schedule
    ON processing_cursor(next_scheduled_at, tier, processing_status);

CREATE INDEX idx_cursor_tier
    ON processing_cursor(tier, last_processed_at);

-- Scoring queries
CREATE INDEX idx_scores_repo_time
    ON scores(repo_full_name, timestamp);

-- Snapshot queries
CREATE INDEX idx_snapshots_repo_time
    ON snapshots(repo_full_name, timestamp);
```

## Configuration Files

| File | Purpose | Key Settings |
|------|---------|-------------|
| `config/categories.yml` | Category definitions | topics, keywords, sub_categories |
| `config/scoring_weights.yml` | Scoring weights | impact, velocity, health weights |
| `config/scale.yml` | Scale settings | tiers, batch size, rate limits, retention |

## Error Handling

### Rate Limit Errors

```
API returns 403/429 with x-ratelimit-remaining: 0
  |
  v
Check x-ratelimit-reset header
  |
  +-- Wait < 10 min: sleep until reset + 5s buffer
  |
  +-- Wait > 10 min: STOP batch, persist progress
  |
  v
Next run picks up where we left off
```

### Snapshot Failures

```
GitHub API error (404, 500, timeout)
  |
  v
Log error, increment processing_attempts
  |
  +-- attempts < 3: retry on next run
  |
  +-- attempts >= 3: mark as permanent_failure
  |
  v
Skip in future runs (manual intervention needed)
```

### Workflow Failures

```
GitHub Actions workflow fails
  |
  v
DB cache already saved (early save strategy)
  |
  v
Next run restores DB from cache
  |
  v
Continues from last successful state
```

## Scalability

See [SCALING.md](SCALING.md) for the roadmap from 5K to 500K repositories.

### Current Capacity

| Metric | Value |
|--------|-------|
| Tracked repositories | 7,000+ (live: [stats.json](https://erbharatmalhotra.github.io/open-source-ai-radar/api/stats.json)) |
| Website pages | 9,000+ |
| API endpoints | 12 + badges + per-repo history |
| Snapshots per day | ~2,800 (4 runs x 700 repos) |
| DB size | ~11 MB |
| Git repo size | ~6 MB |

Note: counts above are refreshed periodically; the stats.json link is always live.

### Growth Projections

| Repos | DB Size | Snapshots/Day | Runs/Day Needed |
|-------|---------|---------------|-----------------|
| 5,000 | 11 MB | 2,800 | 4 |
| 10,000 | 25 MB | 5,600 | 8 |
| 50,000 | 120 MB | 28,000 | 40 |
| 100,000 | 250 MB | 56,000 | 80 |
| 500,000 | 1.2 GB | 280,000 | 400 |

At 500K repos, multi-token strategy (3-5 GitHub Apps) would be needed.
