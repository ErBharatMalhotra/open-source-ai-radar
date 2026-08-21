# Contributing to Open Source AI Radar

Thanks for your interest in contributing!

## Getting Started

1. Fork the repository
2. Clone your fork
3. Install dependencies: `uv sync`
4. Create a branch: `git checkout -b feature/your-feature`

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check src/ tests/

# Build website
cd web && npm run build
```

## Adding a Category

Edit `config/categories.yml` and add your category with topics and keywords.

## Reporting Issues

Use GitHub Issues for bug reports and feature requests.
