# Contributing to Open Source AI Radar

Thanks for your interest in contributing! This guide will help you get started.

## Getting Started

1. Fork the repository
2. Clone your fork
3. Install dependencies: `uv sync`
4. Create a branch: `git checkout -b feature/your-feature`

## Development Setup

### Prerequisites

- Python 3.13+
- Node.js 22+
- [uv](https://docs.astral.sh/uv/) (package manager)
- GitHub token (for API access)

### Installation

```bash
# Clone the repo
git clone https://github.com/your-username/open-source-ai-radar.git
cd open-source-ai-radar

# Install Python dependencies
uv sync

# Install web dependencies
cd web && npm install && cd ..

# Enable repo hooks (commit message hygiene)
git config core.hooksPath scripts/hooks
```

### Environment Variables

```bash
# Required for GitHub API access
export GITHUB_TOKEN="your-github-token"

# Optional: AI provider for classification
export AI_PROVIDER="rule"  # rule, github, openai, or local
```

## Development Workflow

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=radar

# Run specific test
uv run pytest tests/test_scoring.py -v
```

### Linting

```bash
# Check for issues
uv run ruff check src/ tests/

# Auto-fix issues
uv run ruff check src/ tests/ --fix

# Format code
uv run ruff format src/ tests/
```

### Building the Website

```bash
cd web
npm run build
npm run preview  # Local preview at http://localhost:4321
```

### Running the Pipeline

```bash
# Full pipeline (local)
uv run radar discover --limit 50
uv run radar import-json
uv run radar classify
uv run radar process --limit 50
uv run python scripts/export.py

# Or run specific commands
uv run radar top
uv run radar trends
uv run radar report
```

## Project Structure

```
open-source-ai-radar/
+-- src/radar/               # Core Python package
|   +-- github/              # GitHub API client
|   +-- discovery/           # Repository discovery
|   +-- scoring/             # Three-axis scoring
|   +-- analysis/            # Classification, anomalies
|   +-- processing/          # Change detection
|   +-- reports/             # Weekly reports, RSS
|   +-- api/                 # Endpoints, badges
|   +-- scale/               # Scheduler, rate limiter
|   +-- storage/             # SQLite, JSON storage
|   +-- cli.py               # CLI entry point
+-- config/                  # Configuration files
+-- data/                    # Database, exports (gitignored)
+-- web/                     # Astro website
+-- scripts/                 # Utility scripts
+-- docs/                    # Documentation
+-- tests/                   # Unit tests
```

## Key Components

### GitHub Client (`src/radar/github/client.py`)

- GraphQL API for authenticated requests
- REST API fallback for unauthenticated
- Rate limit awareness with adaptive delays
- Retry logic with exponential backoff

### Scoring Engine (`src/radar/scoring/engine.py`)

- Impact: log-scaled percentile rank (stars, forks, watchers)
- Velocity: growth rate, acceleration, commit frequency
- Health: freshness, releases, issue load, community shape, bus factor, license safety
- Radar Score: weighted combination

### Processing Scheduler (`src/radar/scale/scheduler.py`)

- Queue-based with persistent cursor
- Tier-based scheduling (T1-T4)
- Crash-safe (progress preserved on failure)
- Rate-limit-aware (stops on budget exhaustion)

### Change Detection (`src/radar/processing/change_detector.py`)

- Computes processing signature from repo metrics
- Skips repos that haven't changed
- Reduces API calls by ~80%

## Adding a Category

1. Edit `config/categories.yml`
2. Add your category with topics and keywords:

```yaml
categories:
  my-category:
    name: "My Category"
    description: "Description of this category"
    topics:
      - "topic-1"
      - "topic-2"
    keywords:
      - "keyword 1"
      - "keyword 2"
    sub_categories:
      - "Sub Category 1"
      - "Sub Category 2"
```

3. Run discovery: `uv run radar discover --category my-category --limit 100`
4. Test classification: `uv run radar classify`

## Adding a Scoring Signal

1. Edit `config/scoring_weights.yml`
2. Add your signal to the appropriate axis:

```yaml
velocity:
  my_signal_weight: 0.10  # Must sum to 1.0 with other weights
```

3. Implement the signal in `src/radar/scoring/engine.py`
4. Add tests in `tests/test_scoring.py`

## Code Style

- **Formatter:** Ruff (configured in pyproject.toml)
- **Linter:** Ruff with E501 ignored for SQL strings
- **Type hints:** Required for all functions
- **Docstrings:** Required for public APIs
- **Tests:** Required for new features

### Example

```python
from radar.scoring.engine import ScoringEngine

def test_license_safety_penalises_missing_license():
    """Missing license should score 30, MIT should score 90."""
    engine = ScoringEngine(db=None)
    assert engine._license_score({"license": None}) == 30.0
    assert engine._license_score({"license": "MIT"}) == 90.0
```

## Testing

### Writing Tests

```python
import pytest
from radar.scoring.engine import ScoringEngine


@pytest.fixture
def engine():
    return ScoringEngine(db=None)

def test_bus_factor_single_maintainer_is_risky(engine):
    """A repo with one contributor should get the lowest bus factor score."""
    assert engine._bus_factor_score(1) == 20.0

def test_license_score_boundaries(engine):
    assert engine._license_score({"license": None}) == 30.0
    assert engine._license_score({"license": "Apache-2.0"}) == 90.0

def test_bus_factor_scales_with_team_size(engine):
    assert engine._bus_factor_score(50) > engine._bus_factor_score(2)
```

### Running Tests

```bash
# All tests
uv run pytest tests/

# With verbose output
uv run pytest tests/ -v

# Stop on first failure
uv run pytest tests/ -x

# Run specific file
uv run pytest tests/test_scoring.py
```

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes
3. Add tests for new functionality
4. Ensure all tests pass: `uv run pytest tests/`
5. Ensure linting passes: `uv run ruff check src/ tests/`
6. Update documentation if needed
7. Submit a pull request

### PR Template

```markdown
## Description

Brief description of changes.

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing

- [ ] Tests pass locally
- [ ] New tests added (if applicable)
- [ ] Manual testing completed

## Checklist

- [ ] Code follows project style
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
```

## Reporting Issues

Use GitHub Issues for bug reports and feature requests. Please include:

- **Bug reports:** Steps to reproduce, expected behavior, actual behavior
- **Feature requests:** Use case, proposed solution, alternatives considered

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
