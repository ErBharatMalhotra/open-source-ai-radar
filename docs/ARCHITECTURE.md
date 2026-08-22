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
   - Health: freshness, releases, issues, contributors
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
   - 5,000+ project pages
   - 9 main route pages
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
| Discovery (6 categories) | ~120 GraphQL | ~120 | ~2 min |
| Process (700 repos) | ~700 GraphQL | ~700 | ~10 min |
| **Total per run** | **~820** | **~820** | **~12 min** |

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

### Core Tables

```sql
-- Repository metadata
CREATE TABLE repositories (
    full_name TEXT PRIMARY KEY,
    description TEXT,
    language TEXT,
    license TEXT,
    topics TEXT,  -- JSON array
    stars INTEGER,
    forks INTEGER,
    open_issues INTEGER,
    created_at TEXT,
    pushed_at TEXT,
    is_archived BOOLEAN,
    is_fork BOOLEAN,
    owner_login TEXT,
    owner_avatar TEXT,
    homepage TEXT,
    default_branch TEXT,
    mentionable_users INTEGER,
    latest_release_tag TEXT,
    latest_release_date TEXT,
    total_commits INTEGER,
    discovery_sources TEXT  -- JSON array
);

-- Point-in-time snapshots
CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name TEXT,
    timestamp TEXT,
    stars INTEGER,
    forks INTEGER,
    open_issues INTEGER,
    open_prs INTEGER,
    watchers INTEGER,
    contributors INTEGER,
    days_since_last_push INTEGER,
    freshness_score REAL,
    star_growth_rate_7d REAL,
    star_growth_rate_30d REAL,
    star_growth_acceleration REAL,
    forks_7d INTEGER,
    forks_30d INTEGER,
    contributors_7d INTEGER
);

-- Three-axis scores
CREATE TABLE scores (
    repo_full_name TEXT,
    timestamp TEXT,
    impact REAL,
    velocity REAL,
    health REAL,
    radar_score REAL
);

-- AI analysis and classification
CREATE TABLE ai_analysis (
    repo_full_name TEXT PRIMARY KEY,
    category TEXT,
    sub_category TEXT,
    why_trending TEXT,
    anomaly_score REAL,
    is_breakout BOOLEAN
);

-- Processing scheduler (tier-based)
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
| Tracked repositories | 5,271 |
| Website pages | 5,280 |
| API endpoints | 7 |
| Snapshots per day | ~2,800 (4 runs x 700 repos) |
| DB size | ~11 MB |
| Git repo size | ~6 MB |

### Growth Projections

| Repos | DB Size | Snapshots/Day | Runs/Day Needed |
|-------|---------|---------------|-----------------|
| 5,000 | 11 MB | 2,800 | 4 |
| 10,000 | 25 MB | 5,600 | 8 |
| 50,000 | 120 MB | 28,000 | 40 |
| 100,000 | 250 MB | 56,000 | 80 |
| 500,000 | 1.2 GB | 280,000 | 400 |

At 500K repos, multi-token strategy (3-5 GitHub Apps) would be needed.
