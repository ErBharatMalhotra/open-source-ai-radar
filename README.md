# Open Source AI Radar

> Discover what is becoming important before everyone else does.

Open Source AI Radar is a continuously updated intelligence platform that discovers, analyzes, scores, and tracks emerging open-source AI projects on GitHub.

Unlike traditional star-count leaderboards, Radar uses **three-axis scoring** (Impact, Velocity, Health) to find projects that are *becoming* important — not just ones that already are.

## Features

- **Automated Discovery** — Finds AI repos via topics, keywords, and activity signals
- **Three-Axis Scoring** — Impact (40%) + Velocity (35%) + Health (25%)
- **12 AI Categories** — Agents, LLM, Coding, RAG, MCP, Local AI, and more
- **Trend Detection** — Rising stars, hidden gems, losing momentum
- **Weekly Reports** — Auto-generated intelligence summaries
- **Static Website** — Search, filter, and explore rankings
- **RSS Feed** — Subscribe to trending discoveries

## Quick Start

```bash
# Install
uv sync

# Discover repos
uv run radar discover --limit 100

# Import to database
uv run radar import-json

# Score all repos
uv run radar score

# Classify into categories
uv run radar classify

# View trends
uv run radar trends

# Generate weekly report
uv run radar report

# Check status
uv run radar status
```

Run the discovery pipeline to populate the local dataset.

## Three-Axis Scoring

Every repository receives three independent scores (0-100):

| Axis | Weight | What it measures |
|------|--------|-----------------|
| **Impact** | 40% | Stars, forks, watchers (log-scaled percentile rank) |
| **Velocity** | 35% | Growth rate, acceleration, commit frequency |
| **Health** | 25% | Freshness, releases, issue health, community |

The **Radar Score** is: `Impact x 0.40 + Velocity x 0.35 + Health x 0.25`

## Categories

| Category | Focus |
|----------|-------|
| AI Agents | Autonomous agents, frameworks, multi-agent |
| LLM Frameworks | Inference, fine-tuning, serving |
| AI Coding | Coding agents, IDE tools, code generation |
| MCP | Model Context Protocol servers and tools |
| RAG | Retrieval-Augmented Generation, vector DBs |
| Local AI | Ollama-type tools, on-device AI |
| Generative AI | Image, video, audio generation |
| Multimodal | Vision-language, omni-modal models |
| Infrastructure | Model serving, GPU tools, orchestration |
| Evaluation | Benchmarks, model comparison |
| Safety | Guardrails, alignment, bias detection |

## CLI Commands

| Command | Description |
|---------|-------------|
| `radar discover` | Discover repos on GitHub |
| `radar repo <owner/name>` | Inspect a single repo |
| `radar import-json` | Load JSON into SQLite |
| `radar snapshot` | Capture current metrics |
| `radar score` | Compute three-axis scores |
| `radar classify` | Category classification |
| `radar trends` | Rising stars, hidden gems, anomalies |
| `radar categories` | Category distribution |
| `radar gems` | Hidden gems list |
| `radar top` | Top rankings |
| `radar report` | Generate weekly report |
| `radar feed` | Generate RSS feed |
| `radar export` | Export data to JSON |
| `radar status` | Database stats |

## Configuration

### Categories (`config/categories.yml`)

Define which topics and keywords map to each category.

### Scoring Weights (`config/scoring_weights.yml`)

```yaml
weights:
  impact: 0.40
  velocity: 0.35
  health: 0.25
```

### AI Provider (`AI_PROVIDER` env var)

```
AI_PROVIDER=rule      # Rule-based only (default, free)
AI_PROVIDER=github    # GitHub Models
AI_PROVIDER=openai    # OpenAI API
AI_PROVIDER=local     # Local model (Ollama)
```

## Project Structure

```
open-source-radar/
├── src/radar/           # Core Python package
│   ├── github/          # GraphQL + REST API client
│   ├── discovery/       # Layered discovery engine
│   ├── scoring/         # Three-axis scoring + trends
│   ├── analysis/        # Classification + AI analysis
│   ├── reports/         # Weekly reports + RSS
│   └── storage/         # SQLite + JSON storage
├── config/              # categories.yml, scoring_weights.yml
├── data/                # SQLite DB + JSON exports (gitignored)
├── web/                 # Astro website (5 pages)
├── reports/             # Auto-generated weekly reports
├── scripts/             # export.py
├── .github/workflows/   # 4 automation workflows
└── tests/               # Unit tests
```

## Website

Built with Astro, deployed to GitHub Pages:

- `/` — Homepage with top projects
- `/trends` — Rising stars, hidden gems, categories
- `/trending` — Top projects by velocity
- `/top` — Full rankings with axis bars
- `/languages` — Programming language distribution

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
```

## License

MIT
