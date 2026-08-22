# Scaling Roadmap

This document outlines the plan to scale Open Source AI Radar from 5,000 to 500,000 repositories while maintaining zero-maintenance operation.

## Current State (Phase 1)

| Metric | Value |
|--------|-------|
| Repositories | 5,271 |
| API rate limit | 1,000 points/hour (single GITHUB_TOKEN) |
| Processing | 4 runs/day x 700 repos = 2,800/day |
| Full rotation | ~2 days (5,271 / 2,800) |
| DB size | 11 MB |
| Website pages | 5,280 |

## Scaling Phases

### Phase 2: Optimize Single Token (10K repos)

**Timeline:** Month 2

**Goal:** Maximize throughput within single GITHUB_TOKEN limits.

**Changes:**
- Reduce discovery queries from 420 to ~120 (merge topics, use REST)
- Optimize snapshot batching (10 concurrent requests)
- Implement smart change detection (skip unchanged repos)
- Add processing cursor with tier-based scheduling

**Capacity:** 10,000 repos, 4 runs/day, full rotation in ~4 days

### Phase 3: GitHub Apps (50K repos)

**Timeline:** Month 3

**Goal:** Higher rate limits via GitHub App authentication.

**Changes:**
- Create 3 GitHub Apps (discovery, process, backup)
- Each gets 5,000 points/hour base + 50/repo
- Total capacity: 15,000-37,500 points/hour
- Implement token rotation in GitHubClient

**Capacity:** 50,000 repos, 4 runs/day, full rotation in ~3 days

### Phase 4: Multi-Token + Tiering (100K repos)

**Timeline:** Month 4

**Goal:** Distribute workload across tokens and tiers.

**Changes:**
- Implement tier-based token assignment
- T1 repos: primary token (highest priority)
- T2-T3 repos: secondary tokens
- T4 repos: tertiary token (lowest priority)
- Add SQLite partitioning for snapshots (monthly)

**Capacity:** 100,000 repos, 8 runs/day, full rotation in ~3 days

### Phase 5: Database Optimization (250K repos)

**Timeline:** Month 5

**Goal:** Handle large datasets efficiently.

**Changes:**
- Implement snapshot partitioning by month
- Add data retention with configurable cleanup
- Optimize queries with proper indexes
- Add connection pooling for concurrent access
- Implement background cleanup jobs

**Capacity:** 250,000 repos, 8 runs/day, full rotation in ~5 days

### Phase 6: Full Scale (500K repos)

**Timeline:** Month 6

**Goal:** Handle 500K+ repositories with zero maintenance.

**Changes:**
- Deploy 5 GitHub Apps for maximum throughput
- Implement distributed processing (multiple runners)
- Add data archival (cold storage for old snapshots)
- Implement predictive scheduling (ML-based tier assignment)
- Add self-healing mechanisms (auto-retry, auto-cleanup)

**Capacity:** 500,000 repos, 12 runs/day, full rotation in ~7 days

## Rate Limit Strategy

### Single Token (Current)

```
Budget: 1,000 points/hour
Per run: ~350 points (35% budget)
Runs per day: 4
Total: 1,400 points/day (1.4x budget)
```

### GitHub Apps (Phase 3+)

```
3 Apps x 5,000 points/hour = 15,000 points/hour
Per run: ~350 points
Runs per day: 8
Total: 2,800 points/day (0.19x budget)
```

### Multi-Token (Phase 4+)

```
5 Tokens x 5,000 points/hour = 25,000 points/hour
Per run: ~350 points
Runs per day: 12
Total: 4,200 points/day (0.17x budget)
```

## Database Growth

### Snapshot Retention Policy

| Tier | Stars | Keep Period | Rationale |
|------|-------|-------------|-----------|
| T1 | >=1,000 | 2 years | High-value, need long history |
| T2 | 100-999 | 1 year | Growing projects |
| T3 | 10-99 | 6 months | Long-tail projects |
| T4 | <10 | 3 months | Small/new projects |

### Storage Projections

| Repos | Snapshots (1 year) | DB Size | Growth Rate |
|-------|-------------------|---------|-------------|
| 5,000 | 1M | 11 MB | Baseline |
| 10,000 | 2M | 25 MB | 2x |
| 50,000 | 10M | 120 MB | 10x |
| 100,000 | 20M | 250 MB | 20x |
| 500,000 | 100M | 1.2 GB | 100x |

### Partitioning Strategy

```sql
-- Monthly partitions for snapshots
CREATE TABLE snapshots_2026_08 AS
SELECT * FROM snapshots
WHERE timestamp >= '2026-08-01'
  AND timestamp < '2026-09-01';

-- Auto-create next month's partition
-- Auto-drop partitions older than retention period
```

## Website Scaling

### Current Capacity

- 5,280 static pages
- 100 GB bandwidth/month (GitHub Pages free tier)
- ~33 MB average page size

### Growth Projections

| Repos | Pages | Bandwidth/Month | Hosting |
|-------|-------|-----------------|---------|
| 5,000 | 5,280 | 50 GB | GitHub Pages |
| 10,000 | 10,280 | 100 GB | GitHub Pages |
| 50,000 | 50,280 | 500 GB | Cloudflare Pages |
| 100,000 | 100,280 | 1 TB | Cloudflare Pages |
| 500,000 | 500,280 | 5 TB | Vercel/Netlify |

### Migration Triggers

- **50K repos:** Migrate to Cloudflare Pages (free tier: unlimited bandwidth)
- **100K repos:** Consider Vercel Pro ($20/month, 1TB bandwidth)
- **500K repos:** Enterprise hosting or self-hosted solution

## Performance Optimization

### Database Queries

```sql
-- BEFORE: Slow full scan
SELECT * FROM snapshots
WHERE repo_full_name = 'owner/repo'
ORDER BY timestamp DESC
LIMIT 90;

-- AFTER: Indexed, fast lookup
SELECT * FROM snapshots
WHERE repo_full_name = 'owner/repo'
  AND timestamp >= '2026-07-01'
ORDER BY timestamp DESC
LIMIT 90;
```

### API Call Optimization

```python
# BEFORE: Sequential requests
for repo in repos:
    await fetch_repo(repo)  # 1 second each
    await sleep(0.5)  # Rate limit protection

# AFTER: Batched concurrent requests
async with semaphore:  # Limit 10 concurrent
    await asyncio.gather(*[fetch_repo(r) for r in batch])
```

### Caching Strategy

```
GitHub API Response Cache (1 hour)
  |
  v
SQLite Query Cache (5 minutes)
  |
  v
Static File Cache (CDN, 1 hour)
  |
  v
Browser Cache (1 day)
```

## Monitoring & Alerts

### Key Metrics

```
- API calls per hour (should stay < 800)
- Repos processed per run (should be ~700)
- Failed repos (should be < 1%)
- DB size growth (should be linear)
- Website build time (should be < 60 seconds)
- Deploy success rate (should be > 99%)
```

### Alert Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| API calls/hour | > 700 | > 900 |
| Failed repos/run | > 10 | > 50 |
| DB size growth | > 10%/day | > 50%/day |
| Build time | > 30s | > 60s |
| Deploy failures | > 1/day | > 3/day |

## Cost Analysis

### Current (Free Tier)

- GitHub Actions: Free (public repo)
- GitHub Pages: Free (100GB bandwidth)
- GitHub API: Free (1,000 points/hour)
- **Total: $0/month**

### Phase 3 (GitHub Apps)

- GitHub Apps: Free
- GitHub Actions: Free
- GitHub Pages: Free
- **Total: $0/month**

### Phase 6 (500K repos)

- GitHub Apps: Free
- GitHub Actions: Free ($20/month for private repos if needed)
- Cloudflare Pages: Free
- **Total: $0-20/month**

## Maintenance Schedule

### Daily (Automated)

- Run discovery (2x/day)
- Run processing (4x/day)
- Deploy website (on push)
- Generate weekly report (Monday)

### Weekly (Manual Check)

- Review failed repos
- Check rate limit usage
- Monitor DB size growth

### Monthly (Manual)

- Review tier distribution
- Adjust retention policy if needed
- Update category definitions
- Review performance metrics

### Quarterly (Strategic)

- Evaluate scaling phase progress
- Plan next phase implementation
- Review cost optimization opportunities
- Update documentation

## Zero-Maintenance Principles

1. **Self-Healing:** Failed repos retried automatically (max 3 attempts)
2. **Auto-Scaling:** Tier-based scheduling distributes workload
3. **Rate-Limit-Safe:** Adaptive limiter prevents API exhaustion
4. **Crash-Safe:** Persistent cursor preserves progress
5. **Self-Cleaning:** Retention policy removes old data
6. **Self-Monitoring:** Stats available via CLI and website
7. **Self-Deploying:** Automated CI/CD pipeline
8. **Self-Documenting:** Auto-generated reports and API docs
