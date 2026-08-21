"""Social media draft generator for Open Source AI Radar."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from radar.scoring.trends import TrendEngine

logger = logging.getLogger(__name__)


def _fmt(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


class SocialDraftGenerator:
    def __init__(self, db, reports_dir="reports"):
        self.db = db
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.trend_engine = TrendEngine(db)

    def generate_all(self, week_label=None):
        now = datetime.now(tz=UTC)
        if week_label is None:
            week_label = now.strftime("%Y-W%W")
        trends = self.trend_engine.detect_all()
        stats = self.db.get_stats()
        cats = self.trend_engine.get_category_momentum()
        paths = {}
        paths["twitter"] = self._twitter(trends, stats, cats, week_label)
        paths["linkedin"] = self._linkedin(trends, stats, cats, week_label)
        paths["hackernews"] = self._hn(trends, stats, week_label)
        print(f"  Generated {len(paths)} social drafts")
        return paths

    def _twitter(self, trends, stats, cats, wl):
        """Generate a Twitter/X thread draft."""
        now = datetime.now(tz=UTC)
        lines = []
        wk = now.strftime("%W")
        lines.append("AI Open Source Radar - Week " + wk)
        lines.append("")
        repo_count = stats["repos"]
        lines.append(f"I track {repo_count:,} AI repos on GitHub.")
        lines.append("Here is what is becoming important this week.")
        lines.append("")
        rising = trends.get("rising_stars", [])[:5]
        if rising:
            lines.append("FASTEST GROWING:")
            lines.append("")
            for i, r in enumerate(rising, 1):
                name = r["repo_full_name"]
                stars = _fmt(r.get("stars", 0))
                vel = r["velocity"]
                lines.append(f"{i}. {name} - {stars} stars (+{vel:.0f} velocity)")
            lines.append("")
        gems = trends.get("hidden_gems", [])[:5]
        if gems:
            lines.append("HIDDEN GEMS (low stars, high momentum):")
            lines.append("")
            for i, r in enumerate(gems, 1):
                name = r["repo_full_name"]
                stars = _fmt(r.get("stars", 0))
                lines.append(f"{i}. {name} - {stars} stars")
            lines.append("")
        top = [c for c in cats
               if c["category"] != "Uncategorized"][:3]
        if top:
            lines.append("TOP CATEGORIES:")
            lines.append("")
            total = sum(c["count"] for c in cats)
            for c in top:
                pct = (c["count"] / total * 100) if total > 0 else 0
                cat_name = c["category"]
                cat_count = c["count"]
                lines.append(f"  {cat_name}: {cat_count:,} repos ({pct:.0f}%)")
            lines.append("")
        lines.append("Full radar: erbharatmalhotra.github.io/open-source-ai-radar/")
        lines.append("")
        lines.append("Discover what is becoming important before everyone else does.")
        fp = self.reports_dir / ("social-twitter-" + wl + ".txt")
        fp.write_text("\n".join(lines), encoding="utf-8")
        print(f"  Twitter: {fp}")
        return str(fp)

    def _linkedin(self, trends, stats, cats, wl):
        """Generate a LinkedIn post draft."""
        now = datetime.now(tz=UTC)
        lines = []
        wk = now.strftime("%W")
        lines.append("AI Open Source Radar -")
        lines.append("Weekly Intelligence Report (Week " + wk + ")")
        lines.append("")
        repo_count = stats["repos"]
        lines.append(f"I track {repo_count:,} open-source AI repos on GitHub.")
        lines.append("Here is what I found this week:")
        lines.append("")
        rising = trends.get("rising_stars", [])[:5]
        if rising:
            lines.append("Fastest Growing Projects:")
            lines.append("")
            for i, r in enumerate(rising, 1):
                name = r["repo_full_name"]
                stars = _fmt(r.get("stars", 0))
                vel = r["velocity"]
                cat = r.get("category", "AI")
                lines.append(f"{i}. {name} - {stars} stars")
                lines.append(f"   velocity: {vel:.0f}, category: {cat}")
            lines.append("")
        gems = trends.get("hidden_gems", [])[:3]
        if gems:
            lines.append("Hidden Gems (low stars, high potential):")
            lines.append("")
            for i, r in enumerate(gems, 1):
                name = r["repo_full_name"]
                stars = _fmt(r.get("stars", 0))
                lines.append(f"{i}. {name} - {stars} stars")
            lines.append("")
        lines.append("The signal is not just star count -")
        lines.append("its velocity, acceleration, and project health.")
        lines.append("")
        lines.append("Full analysis: erbharatmalhotra.github.io/")
        lines.append("open-source-ai-radar/")
        lines.append("")
        lines.append("#AI #OpenSource #GitHub")
        lines.append("#MachineLearning #DeepLearning #TechTrends")
        fp = self.reports_dir / ("social-linkedin-" + wl + ".txt")
        fp.write_text("\n".join(lines), encoding="utf-8")
        print(f"  LinkedIn: {fp}")
        return str(fp)

    def _hn(self, trends, stats, wl):
        """Generate a Hacker News Show HN post draft."""
        now = datetime.now(tz=UTC)
        lines = []
        wk = now.strftime("%W")
        title = "Show HN: AI Open Source Radar -"
        title += " Week " + wk + " Intelligence Report"
        lines.append(title)
        lines.append("")
        repo_count = stats["repos"]
        desc = f"I built a system that tracks {repo_count:,} open-source AI repos"
        desc += " on GitHub and generates weekly intelligence reports."
        lines.append(desc)
        lines.append("")
        lines.append("What it detects:")
        lines.append("- Velocity: which projects are growing fastest")
        lines.append("- Hidden gems: low stars but high momentum")
        lines.append("- Breakout candidates: about to blow up")
        lines.append("- Category momentum: which AI spaces are heating up")
        lines.append("")
        rising = trends.get("rising_stars", [])[:5]
        if rising:
            lines.append("This weeks biggest risers:")
            lines.append("")
            for r in rising:
                name = r["repo_full_name"]
                stars = _fmt(r.get("stars", 0))
                vel = r["velocity"]
                lines.append(f"- {name} ({stars} stars, vel: {vel:.0f})")
            lines.append("")
        lines.append("Live: erbharatmalhotra.github.io/")
        lines.append("open-source-ai-radar/")
        lines.append("GitHub: github.com/ErBharatMalhotra/")
        lines.append("open-source-ai-radar")
        lines.append("")
        lines.append("Would love feedback on the scoring algorithm")
        lines.append("and what other signals would be useful.")
        fp = self.reports_dir / ("social-hn-" + wl + ".txt")
        fp.write_text("\n".join(lines), encoding="utf-8")
        print(f"  HN: {fp}")
        return str(fp)
