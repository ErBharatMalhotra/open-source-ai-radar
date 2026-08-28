# Open Source AI Radar

> Discover what is becoming important before everyone else does.

Open Source AI Radar is a **continuously updated intelligence platform** that discovers, analyzes, scores, and tracks emerging open-source AI projects on GitHub.

Unlike traditional star-count leaderboards, Radar uses **three-axis scoring** (Impact, Velocity, Health) to find projects that are *becoming* important — not just ones that already are.

**[Live Radar](https://erbharatmalhotra.github.io/open-source-ai-radar/)** | **[API Docs](https://erbharatmalhotra.github.io/open-source-ai-radar/api-docs/)** | **[RSS](https://erbharatmalhotra.github.io/open-source-ai-radar/api/feed.xml)**

<!-- LIVE-STATS:START -->
**Tracking 7,778 repos · 73% auto-classified into 11 AI categories · 34.0M stars tracked · Updated 2026-08-28 23:34 UTC**
<!-- LIVE-STATS:END -->

---

## Features

- **Automated Discovery** — Four-layer discovery: topics, keywords, trending activity, plus free-text name/description search (most popular AI repos ship without topics) across 11 categories
- **Three-Axis Scoring** — Impact (40%) + Velocity (35%) + Health (25%) with historical tracking
- **Health Intelligence** — Freshness, release cadence, issue load, community shape, bus factor (maintainer count), license safety
- **Tier-Based Processing** — Smart scheduling: high-value repos processed more frequently
- **Rate-Limit-Aware** — Adaptive API client that stays within GitHub limits
- **Crash-Safe Scheduler** — Queue-based processing with persistent cursor; no work lost on failure
- **Anomaly Detection** — Detects unusual growth patterns and breaking changes
- **Breakout Detection** — Identifies projects entering breakout territory
- **Why Trending** — Explains why a project is trending with specific metrics
- **Weekly Reports** — Auto-generated intelligence summaries with social media drafts
- **Static Website** — 9,000+ project pages, search, filter, explore rankings, side-by-side comparison, and weekly digest archive
- **SEO Optimized** — OpenGraph, Twitter Cards, JSON-LD structured data, sitemap
- **RSS Feed** — Subscribe to trending discoveries
- **API Endpoints** — JSON API for programmatic access
- **Badges** — Dynamic SVG badges for project READMEs

## Show Your Project's Score

If your repo is tracked, grab a live badge for your README:

```markdown
![AI Radar Score](https://erbharatmalhotra.github.io/open-source-ai-radar/api/badges/OWNER__REPO/score.svg)
```

![score badge example](https://erbharatmalhotra.github.io/open-source-ai-radar/api/badges/BerriAI__litellm/score.svg)

More badges (velocity, stars) and the full docs: [api-docs page](https://erbharatmalhotra.github.io/open-source-ai-radar/api-docs/).

**Want your project tracked?** [Open a submission](https://github.com/ErBharatMalhotra/open-source-ai-radar/issues/new?template=submit-repo.yml) — reviewed within a few days.

### Explore

- [Weekly Digests](https://erbharatmalhotra.github.io/open-source-ai-radar/digests/) — browsable archive of weekly intelligence
- [Compare Projects](https://erbharatmalhotra.github.io/open-source-ai-radar/compare/) — side-by-side radar score comparison
- [llms.txt](https://erbharatmalhotra.github.io/open-source-ai-radar/api/llms.txt) — machine-readable dataset guide for AI agents

---

## Quick Start

```bash
# Install
uv sync

# Discover repos (finds new AI projects on GitHub)
uv run radar discover --limit 100

# Import to database
uv run radar import-json

# Process: snapshot + score all repos
uv run radar process

# Classify into categories
uv run radar classify

# View rankings
uv run radar top

# Check status
uv run radar status
```

## How It Works

```
GitHub API  ->  Discovery  ->  SQLite DB  ->  Scoring  ->  Exports  ->  Website
    ^                                                              |
    +---------- Rate-Limit-Aware Scheduler (tier-based) -----------+
```

### Pipeline Stages

1. **Discovery** — Searches GitHub for repos matching 11 AI categories (topics, keywords, trending, free-text name/description)
2. **Import** — Stores repo metadata in SQLite with deduplication
3. **Classification** — Assigns repos to categories using topic matching
4. **Snapshot** — Fetches current metrics (stars, forks, contributors, releases)
5. **Scoring** — Computes Impact/Velocity/Health scores and Radar Score
6. **Analysis** — Detects anomalies, breakouts, and explains why projects are trending
7. **Export** — Generates JSON, CSV, RSS, project pages, and API endpoints
8. **Deploy** — Builds static website with Astro and deploys to GitHub Pages

### Tier-Based Processing

The scheduler automatically distributes workload based on project importance:

| Tier | Stars | Process Every |
|------|-------|---------------|
| **T1** | >=1,000 | Daily |
| **T2** | 100-999 | Every 3 days |
| **T3** | 10-99 | Weekly |
| **T4** | <10 | Monthly |

Live per-tier counts: `uv run radar scheduler-stats` or the [status page](https://erbharatmalhotra.github.io/open-source-ai-radar/status/). Each workflow run stays within GitHub's 1,000 GraphQL points/hour budget.

---

## Three-Axis Scoring

Every repository receives three independent scores (0-100):

| Axis | Weight | What it measures |
|------|--------|-----------------|
| **Impact** | 40% | Stars, forks, watchers (log-scaled percentile rank) |
| **Velocity** | 35% | Growth rate, acceleration, commit frequency |
| **Health** | 25% | Freshness, releases, issue load, community shape, bus factor (maintainer count), license safety |

The **Radar Score** is: `Impact x 0.40 + Velocity x 0.35 + Health x 0.25`

Weights are configurable in `config/scoring_weights.yml`.

---

## Categories

| Category | Focus | Examples |
|----------|-------|----------|
| AI Agents | Autonomous agents, frameworks, multi-agent | AutoGPT, CrewAI, LangGraph |
| LLM Frameworks | Inference, fine-tuning, serving | vLLM, llama.cpp, Ollama |
| AI Coding | Coding agents, IDE tools, code generation | Continue, Aider, Cursor |
| MCP | Model Context Protocol servers and tools | MCP servers, clients |
| RAG | Retrieval-Augmented Generation, vector DBs | ChromaDB, Qdrant |
| Local AI | On-device AI, privacy-focused | Ollama, LM Studio |
| Generative AI | Image, video, audio generation | Stable Diffusion, ComfyUI |
| Multimodal | Vision-language, omni-modal models | LLaVA, GPT-4V tools |
| Infrastructure | Model serving, GPU tools, MLOps | Ray, BentoML |
| Evaluation | Benchmarks, model comparison | lm-evaluation-harness |
| Safety | Guardrails, alignment, bias detection | Guardrails AI, NeMo Guard |

Categories are configurable in `config/categories.yml`.

---

## CLI Commands

### Core Pipeline

| Command | Description |
|---------|-------------|
| `radar discover` | Discover repos on GitHub via search API |
| `radar repo <owner/name>` | Inspect a single repo in detail |
| `radar import-json` | Load discovered JSON into SQLite |
| `radar process` | Snapshot + score (incremental) |
| `radar score` | Compute three-axis scores |
| `radar classify` | Category classification |
| `radar anomalies` | Detect unusual patterns |
| `radar breakouts` | Detect breakout candidates |
| `radar why-trending` | Explain why projects are trending |

### Analysis & Reports

| Command | Description |
|---------|-------------|
| `radar trends` | Rising stars, hidden gems, anomalies |
| `radar categories` | Category distribution |
| `radar gems` | Hidden gems list |
| `radar top` | Top rankings |
| `radar report` | Generate weekly report |
| `radar social-drafts` | Generate Twitter/LinkedIn/HN drafts |
| `radar feed` | Generate RSS feed |

### Data & Export

| Command | Description |
|---------|-------------|
| `radar export` | Export data to JSON/CSV |
| `radar status` | Database stats |

### Scale & Monitoring

| Command | Description |
|---------|-------------|
| `radar sync-cursor` | Sync repos to processing scheduler |
| `radar schedule --dry-run` | Show next batch of repos to process |
| `radar scheduler-stats` | Detailed scheduler statistics |
| `radar retention-stats` | Snapshot storage statistics |
| `radar retention-cleanup` | Clean old snapshots (dry-run by default) |

---

## Automated Workflows

All workflows run automatically via GitHub Actions:

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| **Discover Repos** | 2x daily (02:00, 14:00 UTC) | Search + import + classify new repos |
| **Process Repos** | 4x daily (04:00, 10:00, 16:00, 22:00 UTC) | Snapshot + score + export due repos |
| **Deploy Website** | On push to main | Build Astro site + deploy to GitHub Pages |
| **Weekly Report** | Monday 08:00 UTC | Generate report + social drafts + RSS |

### Rate Limit Strategy

GitHub `GITHUB_TOKEN` provides 1,000 GraphQL points/hour. Each workflow run uses ~350 points (35% budget), leaving headroom for retries and discovery.

```
DISCOVER (2x/day):  ~120 GraphQL calls (search queries)
PROCESS (4x/day):   ~350 GraphQL calls (repo snapshots)
DEPLOY:             No API calls (build only)
WEEKLY REPORT:      ~50 GraphQL calls (analysis)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed rate limit analysis.

---

## Configuration

### Categories (`config/categories.yml`)

Define which topics and keywords map to each category. Each category has:
- `topics` — GitHub repository topics (high precision)
- `keywords` — Search terms for broader discovery
- `sub_categories` — Sub-category labels

### Scoring Weights (`config/scoring_weights.yml`)

```yaml
weights:
  impact: 0.40
  velocity: 0.35
  health: 0.25
```

### Scale Settings (`config/scale.yml`)

```yaml
tiers:
  1:
    min_stars: 1000
    interval_hours: 24     # daily
  2:
    min_stars: 100
    interval_hours: 72     # every 3 days
  3:
    min_stars: 10
    interval_hours: 168    # weekly
  4:
    min_stars: 0
    interval_hours: 720    # monthly

batch:
  size: 700                # max repos per run
  max_api_calls: 800       # budget per run

rate_limit:
  hourly_budget: 1000      # GITHUB_TOKEN limit
  safety_threshold: 0.80   # use 80% max
```

All timing and thresholds are configurable — no code changes needed.

### AI Provider (`AI_PROVIDER` env var)

```
AI_PROVIDER=rule      # Rule-based only (default, free)
AI_PROVIDER=github    # GitHub Models
AI_PROVIDER=openai    # OpenAI API
AI_PROVIDER=local     # Local model (Ollama)
```

---

## Website

Built with [Astro](https://astro.build/), deployed to GitHub Pages:

| Route | Description |
|-------|-------------|
| `/` | Homepage with leaderboard and highlights |
| `/top` | Full rankings with three-axis scores and sparklines |
| `/trending` | Top projects by velocity |
| `/trends` | Rising stars, hidden gems, category trends |
| `/breakouts` | Breakout detection results |
| `/categories` | Browse by AI category with momentum intelligence |
| `/compare` | Side-by-side project comparison (pick 2-3 repos) |
| `/digests` | Browsable archive of weekly intelligence digests |
| `/languages` | Programming language distribution |
| `/status` | Pipeline status and stats |
| `/api-docs` | API documentation |
| `/project/{owner}/{name}/` | Individual project pages (9,000+) with 90-day history charts |

SEO: OpenGraph tags, Twitter Cards, JSON-LD structured data, auto-generated sitemap.

---

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/repos.json` | All tracked repositories |
| `GET /api/repos.csv` | All repositories as CSV |
| `GET /api/top.json` | Top-ranked repositories |
| `GET /api/trending.json` | Trending repositories |
| `GET /api/gems.json` | Hidden gems |
| `GET /api/breakouts.json` | Breakout candidates |
| `GET /api/anomalies.json` | Detected anomalies |
| `GET /api/categories.json` | Category data |
| `GET /api/compare-index.json` | Slim dataset powering the [compare tool](https://erbharatmalhotra.github.io/open-source-ai-radar/compare/) |
| `GET /api/llms.txt` | Machine-readable guide for AI agents (llms.txt convention) |
| `GET /api/stats.json` | Database statistics |
| `GET /api/feed.xml` | RSS feed |

Full reference: [API docs](https://erbharatmalhotra.github.io/open-source-ai-radar/api-docs/).

---

## Project Structure

```
open-source-ai-radar/
+-- src/radar/               # Core Python package
|   +-- github/              # GraphQL + REST API client
|   +-- discovery/           # Layered discovery engine + telemetry
|   +-- scoring/             # Three-axis scoring + snapshots + trends
|   +-- analysis/            # Classification, anomalies, breakouts
|   +-- processing/          # Change detection for incremental runs
|   +-- reports/             # Weekly reports, RSS, social drafts
|   +-- api/                 # Endpoints + badge generation
|   +-- scale/               # Scheduler, rate limiter, retention
|   +-- storage/             # SQLite + JSON storage
|   +-- cli.py               # CLI entry point
+-- config/                  # categories.yml, scoring_weights.yml, scale.yml
+-- data/                    # SQLite DB + JSON exports (gitignored)
+-- web/                     # Astro website
+-- scripts/                 # export.py
+-- docs/                    # Architecture and scaling docs
+-- .github/workflows/       # 4 automation workflows
+-- tests/                   # Unit tests (50+)
```

---

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check src/ tests/

# Build website
cd web && npm run build

# Full pipeline (local)
uv run radar discover --limit 50
uv run radar import-json
uv run radar classify
uv run radar process --limit 50
uv run python scripts/export.py
```

---

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — System design, data flow, rate limits
- [docs/SCALING.md](docs/SCALING.md) — Roadmap from 5K to 500K repositories

---

## License

MIT
