"""Smart Discovery 2.0 — learns from existing data to find new repos.

Instead of just running static category queries, this system:
1. Analyzes trending repos to find emerging terms
2. Detects new keywords appearing in high-growth repos
3. Generates queries based on what's actually growing
4. Filters out stale queries that haven't yielded results

This makes discovery self-improving over time.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from radar.storage.database import Database

logger = logging.getLogger(__name__)


class SmartDiscoveryEngine:
    """Generates intelligent discovery queries from existing data patterns."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def generate_smart_queries(self, limit: int = 20) -> list[dict[str, Any]]:
        """Generate smart discovery queries based on existing data.

        Returns list of {query, source, category, label} dicts.
        """
        queries = []

        # 1. Extract trending terms from high-growth repos
        trending_terms = self._extract_trending_terms()
        for term in trending_terms[:10]:
            queries.append({
                "query": f'"{term}" stars:>10',
                "source": "trending_term",
                "category": "auto",
                "label": f"Trending term: {term}",
            })

        # 2. Detect emerging keywords from top repos
        emerging = self._detect_emerging_keywords()
        for keyword in emerging[:10]:
            queries.append({
                "query": f'"{keyword}" stars:>5 created:>2025-01-01',
                "source": "emerging_keyword",
                "category": "auto",
                "label": f"Emerging: {keyword}",
            })

        # 3. Category expansion queries
        category_gaps = self._find_category_gaps()
        for gap in category_gaps[:5]:
            queries.append({
                "query": gap["query"],
                "source": "category_gap",
                "category": gap["category"],
                "label": f"Gap fill: {gap['category']}",
            })

        # 4. Star velocity queries (repos gaining fast)
        velocity_queries = self._velocity_based_queries()
        for vq in velocity_queries[:5]:
            queries.append(vq)

        return queries[:limit]

    def _extract_trending_terms(self) -> list[str]:
        """Extract terms appearing frequently in high-velocity repos."""
        with self.db._conn() as conn:
            # Get top velocity repos with descriptions
            rows = conn.execute(
                """SELECT r.description, r.topics, a.category
                FROM scores s
                JOIN repositories r ON s.repo_full_name = r.full_name
                LEFT JOIN ai_analysis a ON s.repo_full_name = a.repo_full_name
                WHERE s.timestamp = (SELECT MAX(timestamp) FROM scores)
                  AND s.velocity >= 70
                  AND r.description != ''
                ORDER BY s.velocity DESC
                LIMIT 200"""
            ).fetchall()

        if not rows:
            return []

        # Extract terms from descriptions
        term_counter: Counter[str] = Counter()
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "is", "are", "was", "were",
            "be", "been", "being", "have", "has", "had", "do", "does", "did",
            "will", "would", "could", "should", "may", "might", "can",
            "this", "that", "these", "those", "it", "its", "your", "you",
            "we", "our", "they", "their", "he", "she", "him", "her",
            "not", "no", "nor", "if", "then", "than", "too", "very",
            "just", "about", "above", "after", "again", "all", "also",
            "any", "because", "before", "between", "both", "each",
            "few", "more", "most", "other", "some", "such", "into",
            "only", "own", "same", "so", "still", "while", "as", "until",
        }

        for row in rows:
            desc = (row["description"] or "").lower()
            topics = row["topics"] or "[]"
            if isinstance(topics, str):
                import json
                try:
                    topics = json.loads(topics)
                except (json.JSONDecodeError, TypeError):
                    topics = []

            # Extract meaningful 2-3 word phrases
            words = desc.split()
            for i in range(len(words) - 1):
                bigram = f"{words[i]} {words[i+1]}"
                if (words[i] not in stop_words and
                    words[i+1] not in stop_words and
                    len(words[i]) > 2 and len(words[i+1]) > 2):
                    term_counter[bigram] += 1

            # Count topics
            for topic in topics:
                if topic.lower() not in stop_words:
                    term_counter[topic] += 2  # Topics weighted higher

        # Return terms that appear multiple times
        return [term for term, count in term_counter.most_common(20) if count >= 3]

    def _detect_emerging_keywords(self) -> list[str]:
        """Detect keywords appearing in recently discovered high-growth repos."""
        with self.db._conn() as conn:
            # Get recently discovered repos (< 30 days) with good scores
            rows = conn.execute(
                """SELECT r.topics, r.description, s.velocity
                FROM repositories r
                JOIN scores s ON r.full_name = s.repo_full_name
                WHERE s.timestamp = (SELECT MAX(timestamp) FROM scores)
                  AND r.discovered_at > datetime('now', '-30 days')
                  AND s.velocity >= 50
                  AND r.stars >= 20"""
            ).fetchall()

        if not rows:
            return []

        import json
        keyword_counter: Counter[str] = Counter()

        for row in rows:
            topics = row["topics"] or "[]"
            if isinstance(topics, str):
                try:
                    topics = json.loads(topics)
                except (json.JSONDecodeError, TypeError):
                    topics = []

            for topic in topics:
                keyword_counter[topic] += 1

        # Return keywords that appear in multiple emerging repos
        return [kw for kw, count in keyword_counter.most_common(15) if count >= 2]

    def _find_category_gaps(self) -> list[dict[str, Any]]:
        """Find categories with low repo count that need more discovery."""
        with self.db._conn() as conn:
            # Get category distribution
            rows = conn.execute(
                """SELECT category, COUNT(*) as count
                FROM ai_analysis WHERE category != ''
                GROUP BY category ORDER BY count ASC"""
            ).fetchall()

        if not rows:
            return []

        gaps = []
        avg_count = sum(r["count"] for r in rows) / len(rows) if rows else 100

        # Load category config for query generation
        try:
            from pathlib import Path

            import yaml

            config_path = Path(__file__).parent.parent.parent.parent / "config" / "categories.yml"
            if config_path.exists():
                with open(config_path) as f:
                    config = yaml.safe_load(f)

                categories = config.get("categories", {})

                for row in rows:
                    if row["count"] < avg_count * 0.5:  # Below average
                        cat_slug = row["category"].lower().replace(" ", "-")
                        if cat_slug in categories:
                            cat = categories[cat_slug]
                            if cat.get("topics"):
                                gaps.append({
                                    "category": row["category"],
                                    "query": f"topic:{cat['topics'][0]} stars:>5",
                                    "current_count": row["count"],
                                })
        except Exception as e:
            logger.warning(f"Could not load category config: {e}")

        return gaps

    def _velocity_based_queries(self) -> list[dict[str, Any]]:
        """Generate queries based on velocity patterns."""
        queries = []

        with self.db._conn() as conn:
            # Find repos with high acceleration (growth speeding up)
            rows = conn.execute(
                """SELECT r.language, r.topics, s.velocity, g.star_growth_acceleration
                FROM scores s
                JOIN repositories r ON s.repo_full_name = r.full_name
                JOIN growth_metrics g ON s.repo_full_name = g.repo_full_name
                    AND g.timestamp = s.timestamp
                WHERE s.timestamp = (SELECT MAX(timestamp) FROM scores)
                  AND g.star_growth_acceleration > 1.5
                  AND s.velocity >= 60
                ORDER BY g.star_growth_acceleration DESC
                LIMIT 100"""
            ).fetchall()

        # Extract languages from accelerating repos
        lang_counter: Counter[str] = Counter()
        for row in rows:
            if row["language"]:
                lang_counter[row["language"]] += 1

        # Generate queries for hot languages
        for lang, count in lang_counter.most_common(5):
            if count >= 3:
                queries.append({
                    "query": f"language:{lang} stars:>50 pushed:>2025-06-01",
                    "source": "velocity_language",
                    "category": lang.lower(),
                    "label": f"Hot language: {lang}",
                })

        return queries

    def get_smart_stats(self) -> dict[str, Any]:
        """Get statistics about smart discovery patterns."""
        trending = self._extract_trending_terms()
        emerging = self._detect_emerging_keywords()
        gaps = self._find_category_gaps()

        return {
            "trending_terms": trending[:10],
            "emerging_keywords": emerging[:10],
            "category_gaps": len(gaps),
            "total_smart_queries": len(trending) + len(emerging) + len(gaps),
        }
