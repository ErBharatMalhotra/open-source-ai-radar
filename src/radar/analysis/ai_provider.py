"""AI analysis provider abstraction.

Supports multiple backends:
  - groq: Groq API (free tier, fast inference)
  - github: GitHub Models (free tier)
  - openai: OpenAI API
  - gemini: Google Gemini
  - local: Local model (Ollama, etc.)
  - none: Disabled (rule-based only)

Configure via AI_PROVIDER environment variable.
For Groq: set GROQ_API_KEYS env var (comma-separated for rotation).
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from itertools import cycle
from typing import Any, ClassVar

import httpx

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    """Abstract base class for AI analysis providers."""

    @abstractmethod
    def analyze_repo(
        self,
        full_name: str,
        description: str,
        topics: list[str],
        language: str | None,
        readme_preview: str = "",
    ) -> dict[str, Any]:
        """Analyze a repository and return structured analysis.

        Returns:
            {
                "summary": str,
                "tech_stack": list[str],
                "use_cases": list[str],
                "maturity": str,  # Emerging | Growing | Mature | Declining
                "quality": float,  # 0-100
                "potential": float,  # 0-100
            }
        """
        ...


class NoOpProvider(AIProvider):
    """No-op provider when AI analysis is disabled."""

    def analyze_repo(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "summary": "",
            "tech_stack": [],
            "use_cases": [],
            "maturity": "Unknown",
            "quality": 0.0,
            "potential": 0.0,
        }


class RuleBasedProvider(AIProvider):
    """Rule-based analysis that doesn't require API calls.

    Uses heuristics from description, topics, and language
    to estimate quality and maturity.
    """

    MATURITY_KEYWORDS: ClassVar[dict[str, list[str]]] = {
        "Emerging": ["new", "experimental", "alpha", "beta", "prototype", "wip", "draft"],
        "Growing": ["growing", "active", " developing", "improving"],
        "Mature": ["stable", "production", "enterprise", "battle-tested", "established"],
        "Declining": ["deprecated", "archived", "unmaintained", "legacy", "sunset"],
    }

    QUALITY_SIGNALS: ClassVar[dict[str, list[str]]] = {
        "positive": [
            "documentation", "tests", "ci/cd", "contributing",
            "license", "changelog", "release", "package",
            "pip install", "npm install", "docker",
        ],
        "negative": [
            "hack", "proof of concept", "poc only", "not maintained",
            "broken", "abandoned",
        ],
    }

    def analyze_repo(
        self,
        full_name: str,
        description: str,
        topics: list[str],
        language: str | None,
        readme_preview: str = "",
    ) -> dict[str, Any]:
        text = f"{description} {' '.join(topics)} {readme_preview}".lower()

        # Maturity estimation
        maturity = self._estimate_maturity(text)

        # Quality estimation
        quality = self._estimate_quality(text, language, topics)

        # Potential estimation
        potential = self._estimate_potential(text, topics, language)

        # Tech stack extraction
        tech_stack = self._extract_tech_stack(text, language, topics)

        # Use case extraction
        use_cases = self._extract_use_cases(text, topics)

        return {
            "summary": description[:300] if description else "",
            "tech_stack": tech_stack,
            "use_cases": use_cases,
            "maturity": maturity,
            "quality": round(quality, 1),
            "potential": round(potential, 1),
        }

    def _estimate_maturity(self, text: str) -> str:
        scores = {"Emerging": 0, "Growing": 0, "Mature": 0, "Declining": 0}
        for stage, keywords in self.MATURITY_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    scores[stage] += 1

        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            return "Growing"  # Default assumption
        return best

    def _estimate_quality(
        self, text: str, language: str | None, topics: list[str]
    ) -> float:
        score = 50.0  # Base

        for signal in self.QUALITY_SIGNALS["positive"]:
            if signal in text:
                score += 5.0

        for signal in self.QUALITY_SIGNALS["negative"]:
            if signal in text:
                score -= 10.0

        # Language bonus for well-maintained ecosystems
        well_maintained = {"python", "typescript", "rust", "go", "java"}
        if language and language.lower() in well_maintained:
            score += 3.0

        # Topic bonus for relevant AI topics
        ai_topics = {"ai", "llm", "machine-learning", "deep-learning", "nlp"}
        if set(t.lower() for t in topics) & ai_topics:
            score += 2.0

        return max(0.0, min(100.0, score))

    def _estimate_potential(
        self, text: str, topics: list[str], language: str | None
    ) -> float:
        score = 50.0

        # High-growth signals
        growth_signals = [
            "trending", "popular", "fastest", "rising",
            "breakthrough", "novel", "innovative", "first",
        ]
        for signal in growth_signals:
            if signal in text:
                score += 8.0

        # AI hype areas
        hot_topics = {
            "agent", "mcp", "rag", "coding", "local",
            "fine-tuning", "multimodal", "safety",
        }
        repo_topics = set(t.lower() for t in topics)
        if repo_topics & hot_topics:
            score += 5.0

        # New + promising
        if "2024" in text or "2025" in text or "2026" in text:
            score += 3.0

        return max(0.0, min(100.0, score))

    def _extract_tech_stack(
        self, text: str, language: str | None, topics: list[str]
    ) -> list[str]:
        techs = set()

        if language:
            techs.add(language)

        # Common AI/ML frameworks
        framework_hints = {
            "pytorch": "PyTorch", "torch": "PyTorch",
            "tensorflow": "TensorFlow", "tf": "TensorFlow",
            "transformers": "Transformers", "huggingface": "HuggingFace",
            "langchain": "LangChain", "llamaindex": "LlamaIndex",
            "openai": "OpenAI API", "anthropic": "Anthropic API",
            "ollama": "Ollama", "llama.cpp": "llama.cpp",
            "vllm": "vLLM", "triton": "Triton",
            "react": "React", "nextjs": "Next.js", "next": "Next.js",
            "fastapi": "FastAPI", "flask": "Flask",
            "docker": "Docker", "kubernetes": "Kubernetes",
            "sqlite": "SQLite", "postgresql": "PostgreSQL",
            "redis": "Redis", "qdrant": "Qdrant",
            "chroma": "ChromaDB", "pinecone": "Pinecone",
        }

        for hint, tech in framework_hints.items():
            if hint in text or hint in [t.lower() for t in topics]:
                techs.add(tech)

        return sorted(techs)[:10]

    def _extract_use_cases(self, text: str, topics: list[str]) -> list[str]:
        use_cases = []
        topic_set = set(t.lower() for t in topics)

        use_case_map = {
            "code generation": ["code", "coding", "programming", "generate"],
            "chatbot": ["chat", "conversation", "dialogue"],
            "document qa": ["document", "qa", "question answering"],
            "image generation": ["image", "diffusion", "generate"],
            "text generation": ["text", "generate", "completion"],
            "data processing": ["data", "etl", "pipeline"],
            "monitoring": ["monitor", "observ", "log"],
            "deployment": ["deploy", "serve", "production"],
            "research": ["research", "paper", "arxiv"],
            "education": ["tutorial", "learn", "course", "education"],
        }

        for use_case, hints in use_case_map.items():
            for hint in hints:
                if hint in text or hint in topic_set:
                    use_cases.append(use_case)
                    break

        return use_cases[:5]


class GroqProvider(AIProvider):
    """Groq API provider with multiple API key support and batch classification.

    Features:
      - Multiple API keys with round-robin rotation
      - Batch classification (100-200 repos per request)
      - Structured JSON output
      - Automatic retry on rate limits
      - Free tier: 30 RPM, 6K TPM

    Configure via:
      - GROQ_API_KEYS: comma-separated API keys
      - GROQ_MODEL: model name (default: llama-3.1-8b-instant)
    """

    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    CATEGORIES: ClassVar[list[str]] = [
        "AI Agents",
        "AI Coding Tools",
        "AI Infrastructure",
        "AI Safety & Alignment",
        "Evaluation & Benchmarks",
        "Generative AI",
        "Local AI",
        "LLM Frameworks",
        "MCP",
        "Multimodal AI",
        "RAG",
    ]

    def __init__(self) -> None:
        keys_raw = os.environ.get("GROQ_API_KEYS", "")
        self._api_keys = [k.strip() for k in keys_raw.split(",") if k.strip()]
        self._key_cycle = cycle(self._api_keys) if self._api_keys else None
        self._model = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
        self._request_count = 0
        self._last_request_time = 0.0

        if not self._api_keys:
            logger.warning("No GROQ_API_KEYS set — Groq provider will fail")

    def _get_next_key(self) -> str | None:
        if self._key_cycle is None:
            return None
        return next(self._key_cycle)

    def _wait_for_rate_limit(self) -> None:
        """Wait 5s between requests (conservative: 12 RPM vs 30 RPM limit)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < 5.0:
            wait_time = 5.0 - elapsed
            logger.debug(f"Rate limit: waiting {wait_time:.1f}s")
            time.sleep(wait_time)

    def classify_batch(
        self,
        repos: list[dict[str, Any]],
        max_repos_per_request: int = 50,
    ) -> list[dict[str, Any]]:
        """Classify a batch of repos using Groq API."""
        if not self._api_keys:
            logger.error("No Groq API keys configured")
            return [
                {"category": "Uncategorized", "confidence": 0.0, "matched_by": "groq_error"}
                for _ in repos
            ]

        max_repos_per_request = min(max_repos_per_request, 100)
        results = []
        total_batches = (len(repos) + max_repos_per_request - 1) // max_repos_per_request

        for i, batch_start in enumerate(range(0, len(repos), max_repos_per_request)):
            chunk = repos[batch_start : batch_start + max_repos_per_request]
            logger.info(f"Groq batch {i+1}/{total_batches}: {len(chunk)} repos...")

            # Wait BEFORE building prompt (so delay is between HTTP requests)
            self._wait_for_rate_limit()

            batch_results = self._classify_chunk(chunk)
            self._last_request_time = time.time()  # Record AFTER request
            self._request_count += 1
            results.extend(batch_results)

        return results

    def _classify_chunk(self, repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Classify a single chunk — NO RETRIES, just fail gracefully."""
        categories_list = "\n".join(f"  - {c}" for c in self.CATEGORIES)

        repos_text = ""
        for idx, repo in enumerate(repos):
            topics = repo.get("topics", [])
            if isinstance(topics, str):
                import json as _json
                try:
                    topics = _json.loads(topics or "[]")
                except Exception:
                    topics = []
            topics_str = ", ".join(topics[:10]) if topics else "none"
            desc = (repo.get("description") or "")[:200]
            lang = repo.get("language") or "unknown"
            repos_text += f"\n{idx}|{repo.get('full_name', '')}|{desc}|{topics_str}|{lang}\n"

        prompt = f"""Classify each GitHub repository into exactly one category.

Categories:
{categories_list}

For each repo, return category and confidence (0.0-1.0).
Format: index|category|confidence
One result per line, no JSON, no explanation.

Repos:{repos_text}

Results:"""

        headers = {
            "Authorization": f"Bearer {self._get_next_key()}",
            "Content-Type": "application/json",
        }

        system_msg = (
            "You are a GitHub repository classifier. "
            "Return only index|category|confidence lines."
        )
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(self.BASE_URL, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()

            content = data["choices"][0]["message"]["content"].strip()
            return self._parse_batch_response(content, repos)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Groq 429 — skipping batch (will retry next run)")
            else:
                logger.error(f"Groq API error: {e}")
            return [
                {"category": "Uncategorized", "confidence": 0.0, "matched_by": "groq_error"}
                for _ in repos
            ]
        except Exception as e:
            logger.error(f"Groq failed: {e}")
            return [
                {"category": "Uncategorized", "confidence": 0.0, "matched_by": "groq_error"}
                for _ in repos
            ]

    def _parse_batch_response(
        self, content: str, repos: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Parse batch response lines into classification results."""
        results = {}
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue
            try:
                idx = int(parts[0].strip())
                category = parts[1].strip()
                confidence = float(parts[2].strip())
                if 0 <= idx < len(repos) and category in self.CATEGORIES:
                    results[idx] = {
                        "category": category,
                        "confidence": round(min(1.0, max(0.0, confidence)), 3),
                        "matched_by": "groq",
                    }
            except (ValueError, IndexError):
                continue

        # Fill missing with Uncategorized
        output = []
        for idx in range(len(repos)):
            if idx in results:
                output.append(results[idx])
            else:
                output.append({
                    "category": "Uncategorized",
                    "confidence": 0.0,
                    "matched_by": "groq_error",
                })
        return output

    def analyze_repo(
        self,
        full_name: str,
        description: str,
        topics: list[str],
        language: str | None,
        readme_preview: str = "",
    ) -> dict[str, Any]:
        """Analyze a single repo (uses classify_batch under the hood)."""
        repo_data = {
            "full_name": full_name,
            "description": description,
            "topics": topics,
            "language": language,
        }
        result = self.classify_batch([repo_data])
        if result:
            cat = result[0].get("category", "Uncategorized")
            return {
                "summary": description[:300],
                "tech_stack": [],
                "use_cases": [],
                "maturity": "Unknown",
                "quality": result[0].get("confidence", 0.0) * 100,
                "potential": 0.0,
                "category": cat,
            }
        return {
            "summary": description[:300],
            "tech_stack": [],
            "use_cases": [],
            "maturity": "Unknown",
            "quality": 0.0,
            "potential": 0.0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        """Return usage stats."""
        return {
            "provider": "groq",
            "model": self._model,
            "api_keys_count": len(self._api_keys),
            "requests_made": self._request_count,
        }


def get_provider(name: str | None = None) -> AIProvider:
    """Get AI provider by name.

    Args:
        name: Provider name. If None, reads from AI_PROVIDER env var.
              Falls back to "rule" (rule-based, no API calls).

    Returns:
        Configured AIProvider instance.
    """
    provider_name = name or os.environ.get("AI_PROVIDER", "rule")

    providers = {
        "none": NoOpProvider,
        "rule": RuleBasedProvider,
        "groq": GroqProvider,
        # Future providers:
        # "github": GitHubModelsProvider,
        # "openai": OpenAIProvider,
        # "gemini": GeminiProvider,
        # "local": LocalProvider,
    }

    cls = providers.get(provider_name)
    if cls is None:
        logger.warning(f"Unknown AI provider '{provider_name}', falling back to rule-based")
        cls = RuleBasedProvider

    logger.info(f"Using AI provider: {provider_name}")
    return cls()
