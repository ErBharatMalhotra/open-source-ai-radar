"""Analysis engine — combines rule-based classification with AI analysis.

Pipeline:
  1. Rule-based category classification (fast, deterministic)
  2. Optional: Groq LLM fallback for low-confidence repos
  3. Rule-based quality/potential estimation (fast, no API)
  4. Optional: AI-powered deep analysis (for top repos only)

Results stored in the database for scoring and display.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from radar.analysis.ai_provider import AIProvider, get_provider
from radar.analysis.classifier import HybridClassifier, RuleClassifier
from radar.storage.database import Database

logger = logging.getLogger(__name__)


class AnalysisEngine:
    """Runs classification + AI analysis on all repositories."""

    def __init__(
        self,
        db: Database,
        classifier: RuleClassifier | HybridClassifier | None = None,
        ai_provider: AIProvider | None = None,
    ) -> None:
        self.db = db
        self.classifier = classifier or RuleClassifier()
        self.ai_provider = ai_provider or get_provider()

    def analyze_all(
        self,
        max_ai_repos: int = 0,
        force: bool = False,
        use_groq: bool = False,
        groq_batch_size: int = 100,
    ) -> dict[str, int]:
        """Analyze all repositories.

        Args:
            max_ai_repos: Max repos to send to AI provider (0 = rules only).
            force: Re-analyze repos that already have analysis.
            use_groq: Use Groq LLM for low-confidence classifications.
            groq_batch_size: Repos per Groq API request.

        Returns:
            Stats: {"classified": N, "ai_analyzed": N, "skipped": N, "groq_classified": N}
        """
        repos = self.db.get_all_repos()
        stats = {"classified": 0, "ai_analyzed": 0, "skipped": 0, "groq_classified": 0}

        logger.info(f"Analyzing {len(repos)} repositories...")

        # Clean up orphaned analyses from repos no longer in the DB
        orphaned = self.db.cleanup_orphan_analyses()
        if orphaned:
            logger.info(f"Removed {orphaned} orphaned ai_analysis rows")

        # Step 1: Classify all repos (rules + optional Groq fallback)
        # Pre-fetch existing analyses if not forcing
        existing_map: dict[str, dict] = {}
        if not force:
            existing_map = self._get_all_existing_analyses()

        # Prepare repos for classification
        repos_to_classify = []
        skip_fns = set()
        for repo in repos:
            fn = repo["full_name"]

            # Skip if already analyzed (unless force)
            if not force and fn in existing_map:
                stats["skipped"] += 1
                skip_fns.add(fn)
                continue

            # topics is stored as a JSON string in the DB — parse it so the
            # rule classifier can match topics (iterating a raw string yields
            # characters, which silently broke topic matching for ~72% repos)
            repo = dict(repo)
            raw_topics = repo.get("topics")
            if isinstance(raw_topics, str):
                try:
                    import json as _json
                    repo["topics"] = _json.loads(raw_topics or "[]")
                except (ValueError, TypeError):
                    repo["topics"] = []

            repos_to_classify.append(repo)

        # Use HybridClassifier if Groq enabled, else RuleClassifier
        if use_groq:
            classifier = HybridClassifier(
                use_groq=True,
                groq_batch_size=groq_batch_size,
            )
            classifications = classifier.classify_all(repos_to_classify)
            # Count Groq-classified repos
            for fn, cls in classifications.items():
                if cls.get("matched_by") == "groq":
                    stats["groq_classified"] += 1
        else:
            classifications = {}
            for repo in repos_to_classify:
                fn = repo["full_name"]
                classifications[fn] = self.classifier.classify(repo)

        # Build analysis batch
        analysis_batch = []
        for fn, classification in classifications.items():
            repo = next((r for r in repos_to_classify if r["full_name"] == fn), {})
            analysis_batch.append({
                "repo_full_name": fn,
                "category": classification["category"],
                "sub_category": classification.get("sub_category", ""),
                "summary": repo.get("description", "")[:300],
                "confidence": classification.get("confidence", 0.0),
                "matched_by": classification.get("matched_by", "none"),
            })

        # Batch insert all analyses in one transaction
        self._save_analyses_batch(analysis_batch)
        stats["classified"] = len(analysis_batch)

        # Step 2: AI analysis for top repos (if enabled)
        if max_ai_repos > 0 and not isinstance(self.ai_provider, type(get_provider("none"))):
            stats["ai_analyzed"] = self._run_ai_analysis(max_ai_repos)

        logger.info(
            f"Analysis complete: {stats['classified']} classified, "
            f"{stats['ai_analyzed']} AI-analyzed, {stats['skipped']} skipped"
        )
        return stats

    def _run_ai_analysis(self, max_repos: int) -> int:
        """Run AI analysis on top repos."""
        # Get top repos by stars (most likely to benefit from AI analysis)
        repos = self.db.get_all_repos()[:max_repos]
        analyzed = 0

        for repo in repos:
            fn = repo["full_name"]

            try:
                result = self.ai_provider.analyze_repo(
                    full_name=fn,
                    description=repo.get("description", "") or "",
                    topics=self._parse_topics(repo.get("topics", "[]")),
                    language=repo.get("language"),
                )

                # Merge AI results with existing classification
                existing = self._get_existing_analysis(fn) or {}
                existing.update({
                    "repo_full_name": fn,
                    "quality": result.get("quality", 0),
                    "potential": result.get("potential", 0),
                    "maturity": result.get("maturity", "Unknown"),
                    "tech_stack": result.get("tech_stack", []),
                    "use_cases": result.get("use_cases", []),
                })

                if result.get("summary"):
                    existing["summary"] = result["summary"]

                self.db.save_analysis(existing)
                analyzed += 1

            except Exception as e:
                logger.error(f"AI analysis failed for {fn}: {e}")

        return analyzed

    def _get_all_existing_analyses(self) -> dict[str, dict]:
        """Get all existing analyses as a map {full_name: analysis}."""
        with self.db._conn() as conn:
            rows = conn.execute(
                "SELECT repo_full_name, category FROM ai_analysis "
                "WHERE category != ''"
            ).fetchall()
            return {r["repo_full_name"]: dict(r) for r in rows}

    def _save_analyses_batch(self, analyses: list[dict[str, Any]]) -> None:
        """Batch save analyses in a single transaction.

        Uses UPSERT so re-classification (--force) refreshes category fields
        but never clobbers AI-enriched columns (tech_stack, use_cases,
        maturity, quality, potential) set by _run_ai_analysis.
        """
        if not analyses:
            return
        timestamp = datetime.now(tz=UTC).isoformat()
        with self.db._conn() as conn:
            conn.executemany(
                """INSERT INTO ai_analysis
                    (repo_full_name, timestamp, category, sub_category,
                     summary, tech_stack, use_cases, maturity, quality,
                     potential, confidence, matched_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(repo_full_name) DO UPDATE SET
                        timestamp=excluded.timestamp,
                        category=excluded.category,
                        sub_category=excluded.sub_category,
                        summary=CASE
                            WHEN ai_analysis.tech_stack != '[]'
                            THEN ai_analysis.summary
                            ELSE excluded.summary END,
                        confidence=excluded.confidence,
                        matched_by=excluded.matched_by""",
                [
                    (
                        a["repo_full_name"],
                        timestamp,
                        a.get("category", ""),
                        a.get("sub_category", ""),
                        a.get("summary", ""),
                        "[]",  # tech_stack (only used on first insert)
                        "[]",  # use_cases (only used on first insert)
                        "Unknown",  # maturity (only used on first insert)
                        0.0,  # quality (only used on first insert)
                        0.0,  # potential (only used on first insert)
                        a.get("confidence", 0.0),
                        a.get("matched_by", "none"),
                    )
                    for a in analyses
                ],
            )

    def _parse_topics(self, topics_str: str | list) -> list[str]:
        """Parse topics from JSON string or list."""
        if isinstance(topics_str, list):
            return topics_str
        try:
            import json
            return json.loads(topics_str)
        except (json.JSONDecodeError, TypeError):
            return []

    def get_category_distribution(self) -> dict[str, int]:
        """Get distribution of repos across categories."""
        with self.db._conn() as conn:
            rows = conn.execute(
                """SELECT category, COUNT(*) as count
                FROM ai_analysis
                WHERE category != ''
                GROUP BY category
                ORDER BY count DESC"""
            ).fetchall()
            return {r["category"]: r["count"] for r in rows}

    def get_sub_category_distribution(self) -> dict[str, int]:
        """Get distribution of repos across sub-categories."""
        with self.db._conn() as conn:
            rows = conn.execute(
                """SELECT sub_category, COUNT(*) as count
                FROM ai_analysis
                WHERE sub_category != ''
                GROUP BY sub_category
                ORDER BY count DESC"""
            ).fetchall()
            return {r["sub_category"]: r["count"] for r in rows}
