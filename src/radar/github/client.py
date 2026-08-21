"""GitHub GraphQL client with rate limiting and retry logic."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# GraphQL query to fetch comprehensive repo data in one call
REPO_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    url
    description
    homepageUrl
    primaryLanguage { name }
    licenseInfo { spdxId }
    repositoryTopics(first: 20) {
      nodes { topic { name } }
    }
    createdAt
    pushedAt
    isArchived
    isFork
    defaultBranchRef { name }
    stargazerCount
    forkCount
    issues(states: OPEN) { totalCount }
    pullRequests(states: OPEN) { totalCount }
    watchers { totalCount }
    mentionableUsers { totalCount }
    releases(first: 5, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes {
        tagName
        createdAt
      }
    }
    defaultBranchRef {
      target {
        ... on Commit {
          committedDate
          history(first: 0) { totalCount }
        }
      }
    }
  }
  rateLimit {
    remaining
    resetAt
    cost
  }
}
"""

SEARCH_QUERY = """
query($query: String!, $after: String) {
  search(query: $query, type: REPOSITORY, first: 50, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    repositoryCount
    nodes {
      ... on Repository {
        nameWithOwner
        url
        description
        homepageUrl
        primaryLanguage { name }
        licenseInfo { spdxId }
        repositoryTopics(first: 10) {
          nodes { topic { name } }
        }
        createdAt
        pushedAt
        isArchived
        isFork
        stargazerCount
        forkCount
        issues(states: OPEN) { totalCount }
        pullRequests(states: OPEN) { totalCount }
        watchers { totalCount }
        mentionableUsers { totalCount }
        releases(first: 3, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes { tagName, createdAt }
        }
        owner {
          login
          avatarUrl
        }
      }
    }
  }
  rateLimit {
    remaining
    resetAt
    cost
  }
}
"""

SEARCH_QUERY_LIGHT = """
query($query: String!, $after: String) {
  search(query: $query, type: REPOSITORY, first: 25, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    repositoryCount
    nodes {
      ... on Repository {
        nameWithOwner
        url
        description
        homepageUrl
        primaryLanguage { name }
        licenseInfo { spdxId }
        createdAt
        pushedAt
        isArchived
        isFork
        stargazerCount
        forkCount
        issues(states: OPEN) { totalCount }
        watchers { totalCount }
      }
    }
  }
  rateLimit {
    remaining
    resetAt
    cost
  }
}
"""


@dataclass
class RateLimitState:
    """Tracks GitHub API rate limit usage."""

    remaining: int = 5000
    limit: int = 5000
    reset_at: float = 0.0
    cost: int = 0
    _total_used: int = field(default=0, repr=False)

    def update(self, remaining: int, reset_at: str, cost: int) -> None:
        self.remaining = remaining
        self.cost = cost
        self._total_used += cost
        # Parse ISO timestamp to epoch
        try:
            from datetime import datetime

            reset_dt = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
            self.reset_at = reset_dt.timestamp()
        except (ValueError, AttributeError):
            self.reset_at = time.time() + 3600  # fallback: 1 hour

    @property
    def seconds_until_reset(self) -> float:
        return max(0, self.reset_at - time.time())

    @property
    def is_throttled(self) -> bool:
        return self.remaining < 100

    @property
    def total_used(self) -> int:
        return self._total_used


class GitHubClient:
    """Async GitHub API client with GraphQL-first approach.

    Features:
    - GraphQL-first for efficiency (one query = full repo data)
    - REST fallback for edge cases
    - Automatic rate limit tracking
    - Retry with exponential backoff
    """

    GRAPHQL_URL = "https://api.github.com/graphql"
    REST_BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 2.0,
    ) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        if not self.token:
            logger.warning("No GitHub token set — API rate limits will be very restrictive")

        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.rate_limit = RateLimitState()
        self._client: httpx.AsyncClient | None = None
        self.last_query_retries: int = 0

    async def __aenter__(self) -> GitHubClient:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"bearer {self.token}"
        self._client = httpx.AsyncClient(timeout=30.0, headers=headers)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self.token:
                headers["Authorization"] = f"bearer {self.token}"
            self._client = httpx.AsyncClient(timeout=30.0, headers=headers)
        return self._client

    async def _graphql_request(
        self, query: str, variables: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a GraphQL request with retry and rate limit handling."""
        client = await self._ensure_client()

        for attempt in range(self.max_retries + 1):
            # Wait if rate limited
            if self.rate_limit.is_throttled:
                wait_time = self.rate_limit.seconds_until_reset + 5
                if wait_time > 0:
                    logger.warning(
                        f"Rate limit low ({self.rate_limit.remaining} remaining). "
                        f"Waiting {wait_time:.0f}s..."
                    )
                    await asyncio.sleep(wait_time)

            try:
                response = await client.post(
                    self.GRAPHQL_URL,
                    json={"query": query, "variables": variables},
                )

                if response.status_code == 403 and "rate limit" in response.text.lower():
                    # Rate limited — extract reset time from headers
                    reset_header = response.headers.get("x-ratelimit-reset", "")
                    if reset_header:
                        self.rate_limit.reset_at = float(reset_header)
                    self.rate_limit.remaining = 0
                    logger.warning("Rate limited by GitHub API")
                    if attempt < self.max_retries:
                        wait = self.retry_base_delay * (2**attempt)
                        await asyncio.sleep(wait)
                        continue
                    raise RuntimeError("GitHub API rate limit exceeded after retries")

                if response.status_code == 200:
                    data = response.json()

                    # Update rate limit from response
                    if "data" in data and "rateLimit" in data.get("data", {}):
                        rl = data["data"]["rateLimit"]
                        self.rate_limit.update(rl["remaining"], rl["resetAt"], rl["cost"])

                    if "errors" in data:
                        errors = data["errors"]
                        # Handle "not found" gracefully
                        if any("Not Found" in str(e.get("message", "")) for e in errors):
                            return {"data": None, "not_found": True}
                        raise RuntimeError(f"GraphQL errors: {errors}")

                    return data.get("data", {})

                response.raise_for_status()

            except httpx.TimeoutException:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{self.max_retries + 1})")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_base_delay * (2**attempt))
                    continue
                raise

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error: {e.response.status_code} — {e.response.text[:200]}")
                if attempt < self.max_retries and e.response.status_code >= 500:
                    await asyncio.sleep(self.retry_base_delay * (2**attempt))
                    continue
                raise

        raise RuntimeError("Max retries exceeded")

    def _parse_repo(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Parse raw GraphQL repo data into a clean dictionary."""
        if not data:
            return None

        topics = [
            t["topic"]["name"]
            for t in data.get("repositoryTopics", {}).get("nodes", [])
        ]

        releases = data.get("releases", {}).get("nodes", [])
        latest_release = releases[0] if releases else None

        owner = data.get("owner", {})

        return {
            "full_name": data.get("nameWithOwner", ""),
            "url": data.get("url", ""),
            "description": data.get("description", "") or "",
            "homepage": data.get("homepageUrl", "") or "",
            "language": (data.get("primaryLanguage") or {}).get("name"),
            "license": (data.get("licenseInfo") or {}).get("spdxId"),
            "topics": topics,
            "is_archived": data.get("isArchived", False),
            "is_fork": data.get("isFork", False),
            "owner_login": owner.get("login", ""),
            "owner_avatar": owner.get("avatarUrl", ""),
            "created_at": data.get("createdAt"),
            "pushed_at": data.get("pushedAt"),
            "stars": data.get("stargazerCount", 0),
            "forks": data.get("forkCount", 0),
            "open_issues": data.get("issues", {}).get("totalCount", 0),
            "open_prs": data.get("pullRequests", {}).get("totalCount", 0),
            "watchers": data.get("watchers", {}).get("totalCount", 0),
            "mentionable_users": data.get("mentionableUsers", {}).get("totalCount", 0),
            "default_branch": (data.get("defaultBranchRef") or {}).get("name", "main"),
            "latest_release_tag": (latest_release or {}).get("tagName"),
            "latest_release_date": (latest_release or {}).get("createdAt"),
        }

    async def get_repo(self, owner: str, name: str) -> dict[str, Any] | None:
        """Fetch full details for a single repository."""
        # Try GraphQL first, fall back to REST if needed
        if self.token:
            try:
                result = await self._graphql_request(
                    REPO_QUERY, {"owner": owner, "name": name}
                )
                if result.get("not_found"):
                    return None
                return self._parse_repo(result.get("repository", {}))
            except Exception as e:
                logger.warning(f"GraphQL failed, trying REST: {e}")

        # REST fallback
        return await self._get_repo_rest(owner, name)

    async def _get_repo_rest(self, owner: str, name: str) -> dict[str, Any] | None:
        """Fetch repo via REST API (works without auth)."""
        client = await self._ensure_client()
        try:
            response = await client.get(f"{self.REST_BASE_URL}/repos/{owner}/{name}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()

            # Also fetch topics
            topics_response = await client.get(
                f"{self.REST_BASE_URL}/repos/{owner}/{name}/topics",
                headers={"Accept": "application/vnd.github+json"},
            )
            topics = []
            if topics_response.status_code == 200:
                topics = topics_response.json().get("names", [])

            # Fetch latest release
            release_response = await client.get(
                f"{self.REST_BASE_URL}/repos/{owner}/{name}/releases/latest"
            )
            latest_release = None
            latest_release_date = None
            if release_response.status_code == 200:
                rel = release_response.json()
                latest_release = rel.get("tag_name")
                latest_release_date = rel.get("published_at")

            return {
                "full_name": data["full_name"],
                "url": data["html_url"],
                "description": data.get("description", "") or "",
                "homepage": data.get("homepage", "") or "",
                "language": data.get("language"),
                "license": (data.get("license") or {}).get("spdx_id"),
                "topics": topics,
                "is_archived": data.get("archived", False),
                "is_fork": data.get("fork", False),
                "owner_login": data["owner"]["login"],
                "owner_avatar": data["owner"]["avatar_url"],
                "created_at": data.get("created_at"),
                "pushed_at": data.get("pushed_at"),
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "open_issues": data.get("open_issues_count", 0),
                "open_prs": 0,  # Not available in single repo endpoint
                "watchers": data.get("watchers_count", 0),
                "mentionable_users": 0,
                "default_branch": data.get("default_branch", "main"),
                "latest_release_tag": latest_release,
                "latest_release_date": latest_release_date,
            }
        except Exception as e:
            logger.error(f"REST fetch failed for {owner}/{name}: {e}")
            return None

    async def search_repos(
        self,
        query: str,
        max_results: int = 1000,
        sort: str = "stars",
        order: str = "desc",
    ) -> list[dict[str, Any]]:
        """Search repositories using GitHub's search API.

        Note: GitHub search API caps at 1,000 results per query.
        Use narrow queries with date/language filters to discover more.
        """
        if self.token:
            return await self._search_repos_graphql(query, max_results)
        return await self._search_repos_rest(query, max_results)

    async def _search_repos_graphql(
        self, query: str, max_results: int
    ) -> list[dict[str, Any]]:
        """Search via GraphQL (authenticated) with lightweight query and retry."""
        all_repos: list[dict[str, Any]] = []
        after_cursor: str | None = None
        remaining = min(max_results, 1000)
        max_retries = 3
        self.last_query_retries = 0

        while remaining > 0:
            retries = 0
            result = None

            while retries < max_retries:
                try:
                    result = await self._graphql_request(
                        SEARCH_QUERY_LIGHT,
                        {"query": query, "after": after_cursor},
                    )
                    break
                except Exception as e:
                    err_str = str(e)
                    if "RESOURCE_LIMITS_EXCEEDED" in err_str or "502" in err_str or "504" in err_str:
                        retries += 1
                        self.last_query_retries += 1
                        wait = min(5 * (2 ** (retries - 1)), 30)
                        logger.warning(
                            f"GraphQL rate limit/timeout for '{query}' "
                            f"(attempt {retries}/{max_retries}), waiting {wait}s..."
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"GraphQL search failed for '{query}': {e}")
                        return all_repos

            if result is None:
                logger.error(f"GraphQL search exhausted retries for '{query}'")
                break

            search_data = result.get("search", {})
            repos = search_data.get("nodes", [])
            page_info = search_data.get("pageInfo", {})

            for repo_data in repos:
                if repo_data and "nameWithOwner" in repo_data:
                    parsed = self._parse_repo(repo_data)
                    if parsed:
                        all_repos.append(parsed)

            remaining -= len(repos)

            if not page_info.get("hasNextPage") or remaining <= 0:
                break

            after_cursor = page_info.get("endCursor")

        return all_repos

    async def _search_repos_rest(
        self, query: str, max_results: int
    ) -> list[dict[str, Any]]:
        """Search via REST API (works without auth, 10 results/page)."""
        client = await self._ensure_client()
        all_repos: list[dict[str, Any]] = []
        page = 1
        per_page = min(100, max_results)  # REST max is 100

        while len(all_repos) < max_results:
            try:
                response = await client.get(
                    f"{self.REST_BASE_URL}/search/repositories",
                    params={
                        "q": query,
                        "sort": "stars",
                        "order": "desc",
                        "per_page": per_page,
                        "page": page,
                    },
                )

                if response.status_code == 403:
                    # Check if it's a rate limit or secondary limit
                    reset_header = response.headers.get("x-ratelimit-reset", "")
                    if reset_header:
                        wait_time = max(0, float(reset_header) - time.time()) + 5
                    else:
                        wait_time = 65  # Default wait for search rate limit
                    logger.warning(
                        f"Search rate limited. Waiting {wait_time:.0f}s..."
                    )
                    await asyncio.sleep(wait_time)
                    continue  # Retry the same page

                response.raise_for_status()
                data = response.json()

                items = data.get("items", [])
                if not items:
                    break

                for item in items:
                    repo = {
                        "full_name": item["full_name"],
                        "url": item["html_url"],
                        "description": item.get("description", "") or "",
                        "homepage": item.get("homepage", "") or "",
                        "language": item.get("language"),
                        "license": (item.get("license") or {}).get("spdx_id"),
                        "topics": item.get("topics", []),
                        "is_archived": item.get("archived", False),
                        "is_fork": item.get("fork", False),
                        "owner_login": item["owner"]["login"],
                        "owner_avatar": item["owner"]["avatar_url"],
                        "created_at": item.get("created_at"),
                        "pushed_at": item.get("pushed_at"),
                        "stars": item.get("stargazers_count", 0),
                        "forks": item.get("forks_count", 0),
                        "open_issues": item.get("open_issues_count", 0),
                        "open_prs": 0,
                        "watchers": item.get("watchers_count", 0),
                        "mentionable_users": 0,
                        "default_branch": item.get("default_branch", "main"),
                        "latest_release_tag": None,
                        "latest_release_date": None,
                    }
                    all_repos.append(repo)

                # Check if there are more pages
                total_count = data.get("total_count", 0)
                if page * per_page >= total_count or page * per_page >= 1000:
                    break

                page += 1
                # Small delay to respect rate limits
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"REST search failed for '{query}': {e}")
                break

        return all_repos[:max_results]

    async def get_rate_limit(self) -> dict[str, Any]:
        """Check current rate limit status."""
        client = await self._ensure_client()
        response = await client.get(f"{self.REST_BASE_URL}/rate_limit")
        if response.status_code == 200:
            return response.json()
        return {"error": response.status_code}

    def log_status(self) -> None:
        """Log current client status."""
        logger.info(
            f"GitHub API: {self.rate_limit.remaining} requests remaining, "
            f"{self.rate_limit.total_used} total used this session"
        )
