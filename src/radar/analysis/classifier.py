"""Rule-based category classifier for open-source AI repositories.

Uses three signal layers (in priority order):
  1. GitHub topics (high precision)
  2. Description + README keywords (broader recall)
  3. Language + metadata heuristics (fallback)

Each repo gets a primary category + sub-category + confidence score.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = Path(__file__).parent.parent.parent.parent / "config" / "categories.yml"


def _load_categories(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_CONFIG
    if not p.exists():
        return {}
    with open(p) as f:
        return yaml.safe_load(f)


class RuleClassifier:
    """Classifies repositories into AI categories using deterministic rules.

    No API calls — pure rule matching on existing metadata.
    Fast enough to run on all 5,000+ repos in <1 second.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self.config = _load_categories(config_path)
        self.categories = self.config.get("categories", {})
        self._compiled_rules = self._compile_rules()

    def _compile_rules(self) -> list[dict[str, Any]]:
        """Pre-compile category matching rules for speed."""
        rules = []
        for slug, cat in self.categories.items():
            # Normalize topics to sets for O(1) lookup
            topics = set(t.lower() for t in cat.get("topics", []))

            # Normalize keywords to lowercase patterns
            keywords = [k.lower() for k in cat.get("keywords", [])]

            # Build regex patterns for keywords
            patterns = []
            for kw in keywords:
                # Escape special regex chars, then make flexible
                escaped = re.escape(kw)
                # Allow flexible whitespace between words
                flexible = escaped.replace(r"\ ", r"\s+")
                patterns.append(re.compile(rf"\b{flexible}\b", re.IGNORECASE))

            rules.append({
                "slug": slug,
                "name": cat.get("name", slug),
                "topics": topics,
                "keywords": keywords,
                "patterns": patterns,
                "sub_categories": cat.get("sub_categories", []),
            })

        return rules

    def classify(self, repo: dict[str, Any]) -> dict[str, Any]:
        """Classify a single repository.

        Returns:
            {
                "category": str,
                "category_slug": str,
                "sub_category": str,
                "confidence": float,  # 0-1
                "matched_by": str,    # "topic" | "keyword" | "language" | "none"
            }
        """
        repo_topics = set(t.lower() for t in repo.get("topics", []))
        description = (repo.get("description", "") or "").lower()
        name = (repo.get("full_name", "") or "").lower()
        language = (repo.get("language", "") or "").lower()

        best_match = {
            "category": "Uncategorized",
            "category_slug": "uncategorized",
            "sub_category": "",
            "confidence": 0.0,
            "matched_by": "none",
        }

        best_score = 0.0

        for rule in self._compiled_rules:
            score = 0.0
            matched_by = "none"

            # Layer 1: Topic match (highest confidence)
            topic_overlap = repo_topics & rule["topics"]
            if topic_overlap:
                # More topic matches = higher confidence
                score = 0.7 + min(0.3, len(topic_overlap) * 0.1)
                matched_by = "topic"

            # Layer 2: Keyword match in description/name
            if score < 0.6:
                text = f"{description} {name}"
                keyword_hits = 0
                for pattern in rule["patterns"]:
                    if pattern.search(text):
                        keyword_hits += 1

                if keyword_hits > 0:
                    kw_score = 0.5 + min(0.3, keyword_hits * 0.1)
                    if kw_score > score:
                        score = kw_score
                        matched_by = "keyword"

            # Boost: sub-category detection
            sub_cat = ""
            if score > 0:
                sub_cat = self._detect_sub_category(repo, rule)

            if score > best_score:
                best_score = score
                best_match = {
                    "category": rule["name"],
                    "category_slug": rule["slug"],
                    "sub_category": sub_cat,
                    "confidence": round(score, 3),
                    "matched_by": matched_by,
                }

        return best_match

    def _detect_sub_category(self, repo: dict[str, Any], rule: dict) -> str:
        """Detect sub-category within a matched category."""
        desc = (repo.get("description", "") or "").lower()
        topics = set(t.lower() for t in repo.get("topics", []))
        name = (repo.get("full_name", "") or "").lower()
        text = f"{desc} {name} {' '.join(topics)}"

        # Sub-category heuristics
        sub_hints = {
            # AI Agents
            "coding agent": ["code", "coding", "editor", "ide", "copilot", "assistant"],
            "research agent": ["research", "paper", "arxiv", "academic"],
            "task agent": ["task", "automation", "workflow", "orchestrat"],
            "conversational agent": ["chat", "conversation", "dialogue", "assistant"],

            # LLM
            "inference engine": ["inference", "serve", "deploy", "runtime", "engine"],
            "fine-tuning": ["fine-tun", "finetun", "lora", "qlora", "adapter", "train"],
            "quantization": ["quantiz", "gguf", "gptq", "awq", "bitsandbytes"],
            "serving": ["serve", "deployment", "api", "endpoint"],

            # AI Coding
            "cli tool": ["cli", "terminal", "command-line", "console"],
            "ide extension": ["extension", "plugin", "vscode", "jetbrains", "ide"],
            "code completion": ["completion", "autocomplete", "copilot", "inline"],
            "code review": ["review", "lint", "pr", "pull request"],

            # RAG
            "vector database": ["vector", "embedding", "ann", "similarity search"],
            "rag framework": ["rag", "retrieval", "augmented", "knowledge"],
            "embeddings": ["embedding", "encode", "vectorize"],
            "knowledge management": ["knowledge", "wiki", "document", "docs"],

            # MCP
            "server": ["server", "mcp server", "provider"],
            "client": ["client", "consumer", "connector"],
            "tool": ["tool", "utility", "helper"],
            "integration": ["integration", "plugin", "connector", "bridge"],

            # Local AI
            "local runner": ["local", "offline", "on-device", "self-host"],
            "privacy tool": ["privacy", "private", "secure", "encrypted"],
            "edge ai": ["edge", "mobile", "arm", "embedded"],
            "offline ai": ["offline", "no internet", "air-gapped"],

            # Generative AI
            "image": ["image", "photo", "picture", "diffusion", "stable diffusion"],
            "video": ["video", "animation", "motion"],
            "audio": ["audio", "voice", "speech", "tts", "music"],
            "3d": ["3d", "mesh", "nerf", "gaussian"],

            # Multimodal
            "vision-language": ["vision", "vlm", "image understanding", "visual"],
            "audio-language": ["audio", "speech", "voice"],
            "omni-modal": ["omni", "multi-modal", "multimodal"],

            # AI Infrastructure
            "model serving": ["serve", "inference", "deploy", "triton", "vllm"],
            "gpu management": ["gpu", "cuda", "vram", "memory"],
            "orchestration": ["orchestrat", "pipeline", "workflow", "kubeflow"],
            "monitoring": ["monitor", "observ", "metric", "log"],

            # Evaluation
            "benchmark": ["benchmark", "eval", "leaderboard", "comparison"],
            "evaluation framework": ["eval", "test", "measure", "metric"],
            "comparison tool": ["compare", "versus", "vs", "comparison"],

            # AI Safety
            "guardrails": ["guardrail", "safety", "filter", "moderation"],
            "content filtering": ["filter", "content", "toxicity", "harmful"],
            "bias detection": ["bias", "fairness", "equity"],
            "alignment research": ["alignment", "rlhf", "constitutional"],
        }

        for sub_cat, hints in sub_hints.items():
            if sub_cat in [s.lower() for s in rule.get("sub_categories", [])]:
                for hint in hints:
                    if hint in text:
                        return sub_cat

        return ""

    def classify_all(self, repos: list[dict[str, Any]]) -> dict[str, dict]:
        """Classify all repos. Returns {full_name: classification}."""
        results = {}
        for repo in repos:
            fn = repo.get("full_name", "")
            if fn:
                results[fn] = self.classify(repo)
        return results

    def get_category_stats(self, repos: list[dict[str, Any]]) -> dict[str, int]:
        """Get distribution of repos across categories."""
        counts: dict[str, int] = {}
        for repo in repos:
            result = self.classify(repo)
            cat = result["category"]
            counts[cat] = counts.get(cat, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))
