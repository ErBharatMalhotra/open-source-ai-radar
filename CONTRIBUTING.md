# Getting Started & Contributing

Welcome to Open Source AI Radar! This guide walks you through setting up your local environment, running tests, executing the data pipeline, and contributing changes.

---

## Local Development Setup

### Prerequisites
- **Python 3.13+**
- **uv** (fast Python package manager: `curl -LsSf https://astral.sh/uv/install.sh | sh` or `winget install astral-sh.uv`)
- **Node.js 20+** (for Astro website)

### Clone & Install

```bash
git clone https://github.com/ErBharatMalhotra/open-source-ai-radar.git
cd open-source-ai-radar

# Install Python backend dependencies
uv sync

# Install web dashboard dependencies
cd web
npm install
cd ..
```

---

## Running the Data Pipeline Locally

You can test individual stages of the intelligence pipeline using the `radar` CLI:

```bash
# 1. Discover newly created or trending AI repositories (limit 50 for local testing)
uv run radar discover --limit 50

# 2. Import newly discovered candidates into SQLite database
uv run radar import-json

# 3. Classify unclassified repos into 11 AI categories
uv run radar classify

# 4. Take snapshots and score pending repositories
uv run radar process --limit 50

# 5. Export JSON and CSV endpoints to data/exports/
uv run python scripts/export.py
```

---

## Running the Web Dashboard

```bash
cd web
npm run dev
```
Open `http://localhost:4321/open-source-ai-radar/` in your browser.

---

## Code Quality & Testing

Before creating a Pull Request, please ensure tests and lint checks pass:

```bash
# Run backend test suite
uv run pytest tests/ -v

# Run code style and lint checks
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Build static website
cd web && npm run build
```

---

## How to Contribute

1. Check our [Good First Issues](https://github.com/ErBharatMalhotra/open-source-ai-radar/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) for beginner-friendly tasks.
2. Fork the repository and create a feature branch (`git checkout -b feature/my-feature`).
3. Commit your changes with a clear, conventional commit message (`feat: ...` or `fix: ...`).
4. Push to your fork and submit a Pull Request against `main`.
