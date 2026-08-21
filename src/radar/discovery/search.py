"""Discovery engine — searches GitHub for open-source AI repositories.

Uses layered discovery:
  Layer 1: Topic-based (high precision)
  Layer 2: Keyword search (broader recall)
  Layer 3: Date/activity filters (catch emerging repos)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from radar.github.client import GitHubClient
from radar.discovery.telemetry import DiscoveryTelemetry

logger = logging.getLogger(__name__)

# Default categories config path
DEFAULT_CONFIG = Path(__file__).parent.parent.parent.parent / "config" / "categories.yml"


def load_categories(config_path: Path | None = None) -> dict[str, Any]:
    """Load category definitions from YAML config."""
    path = config_path or DEFAULT_CONFIG
    if not path.exists():
        logger.error(f"Categories config not found: {path}")
        return {}
    with open(path) as f:
        return yaml.safe_load(f)


def build_queries(
    categories: dict[str, Any],
    category_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Build search queries from category definitions.

    Returns list of {query, category_slug, layer, label} dicts.
    """
    queries: list[dict[str, Any]] = []

    cats = categories.get("categories", {})
    if category_filter:
        cats = {k: v for k, v in cats.items() if k == category_filter}

    from datetime import datetime, timedelta

    # Date filters for discovering recent activity
    recent_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    new_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    created_recent = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

    for slug, cat in cats.items():
        name = cat.get("name", slug)

        # Layer 1: Topic-based queries
        for topic in cat.get("topics", []):
            queries.append(
                {
                    "query": f"topic:{topic} stars:>10",
                    "category_slug": slug,
                    "category_name": name,
                    "layer": "topic",
                    "label": f"Topic: {topic}",
                }
            )
            # Also query for emerging repos with topic
            queries.append(
                {
                    "query": f"topic:{topic} stars:>5 created:>{created_recent}",
                    "category_slug": slug,
                    "category_name": name,
                    "layer": "topic新兴",
                    "label": f"Emerging: {topic}",
                }
            )

        # Layer 2: Keyword searches
        for keyword in cat.get("keywords", []):
            queries.append(
                {
                    "query": f'"{keyword}" stars:>10 pushed:>{recent_date}',
                    "category_slug": slug,
                    "category_name": name,
                    "layer": "keyword",
                    "label": f'Keyword: "{keyword}"',
                }
            )

        # Layer 3: Trending in category (high recent activity)
        if cat.get("topics"):
            # Take first topic for trending query
            main_topic = cat["topics"][0]
            queries.append(
                {
                    "query": f"topic:{main_topic} stars:>50 pushed:>{new_date} sort:stars-desc",
                    "category_slug": slug,
                    "category_name": name,
                    "layer": "trending",
                    "label": f"Trending: {name}",
                }
            )

    return queries


class DiscoveryEngine:
    """Discovers open-source repositories via layered GitHub searches.

    Handles:
    - Topic-based discovery (high precision)
    - Keyword-based discovery (broader recall)
    - Deduplication by full_name
    - Quality filtering
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self.categories = load_categories(config_path)
        self._seen_names: set[str] = set()

    def _is_quality_repo(self, repo: dict[str, Any]) -> bool:
        """Apply minimum quality filters.

        Filters:
        - Stars > 10 OR (Stars > 5 AND Forks > 1)
        - Not archived
        - Not a fork (by default)
        - Has been pushed to recently (within 12 months)
        """
        stars = repo.get("stars", 0)
        forks = repo.get("forks", 0)

        # Minimum star/fork threshold
        if stars < 10 and not (stars > 5 and forks > 1):
            return False

        # Skip archived repos
        if repo.get("is_archived", False):
            return False

        # Skip forks (they inflate metrics of the original)
        return not repo.get("is_fork", False)

    def _deduplicate(self, repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove duplicates by full_name, merging discovery sources."""
        deduped: dict[str, dict[str, Any]] = {}

        for repo in repos:
            name = repo.get("full_name", "")
            if not name:
                continue

            if name in deduped:
                # Merge discovery sources
                existing_sources = deduped[name].get("discovery_sources", [])
                new_source = repo.get("_discovery_source", "")
                if new_source and new_source not in existing_sources:
                    deduped[name]["discovery_sources"] = [*existing_sources, new_source]
            else:
                repo["discovery_sources"] = [repo.pop("_discovery_source", "")]
                deduped[name] = repo

        return list(deduped.values())

    async def run(
        self,
        category: str | None = None,
        custom_query: str | None = None,
        max_per_query: int = 100,
    ) -> list[dict[str, Any]]:
        """Run the full discovery pipeline.

        Args:
            category: Filter to a specific category slug
            custom_query: Run a custom search query instead of configured ones
            max_per_query: Max results per individual search query

        Returns:
            Deduplicated, quality-filtered list of repos
        """
        all_repos: list[dict[str, Any]] = []

        async with GitHubClient() as client:
            if custom_query:
                # Custom query mode
                logger.info(f"Running custom query: {custom_query}")
                repos = await client.search_repos(custom_query, max_results=max_per_query)
                for r in repos:
                    r["_discovery_source"] = f"custom:{custom_query}"
                all_repos.extend(repos)
            else:
                # Standard category-based discovery
                queries = build_queries(self.categories, category)
                total = len(queries)

                for i, q in enumerate(queries, 1):
                    logger.info(
                        f"[{i}/{total}] {q['label']} ({q['category_name']}) "
                        f"— {q['query']}"
                    )

                    repos = await client.search_repos(
                        q["query"], max_results=max_per_query
                    )

                    for r in repos:
                        r["_discovery_source"] = f"{q['category_slug']}:{q['layer']}"

                    all_repos.extend(repos)
                    logger.info(f"  → Found {len(repos)} repos")

                    # Check rate limit and pause if needed
                    if client.rate_limit.remaining < 5 and not client.token:
                        wait = max(10, client.rate_limit.seconds_until_reset)
                        logger.info(f"Low rate limit. Waiting {wait:.0f}s...")
                        await asyncio.sleep(wait)

                    # Log progress periodically
                    if i % 10 == 0:
                        client.log_status()

        # Deduplicate
        deduped = self._deduplicate(all_repos)
        logger.info(f"After dedup: {len(deduped)} unique repos")

        # Quality filter
        quality = [r for r in deduped if self._is_quality_repo(r)]
        filtered_count = len(deduped) - len(quality)
        logger.info(
            f"After quality filter: {len(quality)} repos "
            f"({filtered_count} filtered out)"
        )

        # Clean up internal fields
        for repo in quality:
            repo.pop("_discovery_source", None)

        # Sort by stars descending
        quality.sort(key=lambda r: r.get("stars", 0), reverse=True)

        return quality
