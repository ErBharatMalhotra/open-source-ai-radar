"""Weekly report generator for Open Source AI Radar.

Produces markdown intelligence reports:
  - Biggest risers
  - Fastest growing
  - Hidden gems
  - New discoveries
  - Category momentum
  - Losing momentum

Reports are saved to reports/ directory and can be published as
GitHub Releases or committed to the repo.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from radar.scoring.trends import TrendEngine
from radar.storage.database import Database

logger = logging.getLogger(__name__)


def _format_stars(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _score_emoji(score: float) -> str:
    if score >= 80:
        return "🔥"
    elif score >= 60:
        return "⭐"
    elif score >= 40:
        return "📊"
    else:
        return "📉"


class WeeklyReportGenerator:
    """Generates weekly intelligence reports from the database."""

    def __init__(self, db: Database, reports_dir: str | Path = "reports") -> None:
        self.db = db
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.trend_engine = TrendEngine(db)

    def generate(self, week_label: str | None = None) -> str:
        """Generate a weekly report and save to file.

        Args:
            week_label: Custom week label (e.g., "2026-W34").
                       Defaults to current ISO week.

        Returns:
            Path to the generated report file.
        """
        now = datetime.now(tz=timezone.utc)
        if week_label is None:
            week_label = now.strftime("%Y-W%W")

        trends = self.trend_engine.detect_all()
        categories = self.trend_engine.get_category_momentum()

        # Get stats
        stats = self.db.get_stats()

        # Build report
        lines = []
        lines.append(f"# Open Source AI Radar — Week {now.strftime('%W')} ({now.strftime('%Y')})")
        lines.append("")
        lines.append(f"> *Generated on {now.strftime('%Y-%m-%d %H:%M UTC')}*")
        lines.append(f"> *Tracking {stats['repos']:,} repositories with {_format_stars(stats['total_stars'])} total stars*")
        lines.append("")

        # ── Biggest Risers ──
        lines.append("## 🔥 Biggest Risers This Week")
        lines.append("")
        lines.append("Projects with the highest velocity — growing fast right now.")
        lines.append("")
        lines.append("| # | Project | Stars | Velocity | Score | Category |")
        lines.append("|---|---------|-------|----------|-------|----------|")
        for i, r in enumerate(trends["rising_stars"][:10], 1):
            lines.append(
                f"| {i} | [{r['repo_full_name']}](https://github.com/{r['repo_full_name']}) "
                f"| {_format_stars(r.get('stars', 0))} "
                f"| {r['velocity']:.0f} "
                f"| {_score_emoji(r['radar_score'])} {r['radar_score']:.0f} "
                f"| {r.get('category', '')} |"
            )
        lines.append("")

        # ── Hidden Gems ──
        lines.append("## 💎 Hidden Gems")
        lines.append("")
        lines.append("Low stars but high velocity + health — about to blow up.")
        lines.append("")
        lines.append("| # | Project | Stars | Velocity | Health | Score |")
        lines.append("|---|---------|-------|----------|--------|-------|")
        for i, r in enumerate(trends["hidden_gems"][:10], 1):
            lines.append(
                f"| {i} | [{r['repo_full_name']}](https://github.com/{r['repo_full_name']}) "
                f"| {_format_stars(r.get('stars', 0))} "
                f"| {r['velocity']:.0f} "
                f"| {r['health']:.0f} "
                f"| {r['radar_score']:.0f} |"
            )
        lines.append("")

        # ── New & Promising ──
        if trends.get("new_promising"):
            lines.append("## 🆕 New & Promising")
            lines.append("")
            lines.append("Recently created projects with strong early signals.")
            lines.append("")
            lines.append("| # | Project | Stars | Velocity | Score |")
            lines.append("|---|---------|-------|----------|-------|")
            for i, r in enumerate(trends["new_promising"][:10], 1):
                lines.append(
                    f"| {i} | [{r['repo_full_name']}](https://github.com/{r['repo_full_name']}) "
                    f"| {_format_stars(r.get('stars', 0))} "
                    f"| {r['velocity']:.0f} "
                    f"| {r['radar_score']:.0f} |"
                )
            lines.append("")

        # ── Losing Momentum ──
        if trends.get("losing_momentum"):
            lines.append("## 📉 Losing Momentum")
            lines.append("")
            lines.append("Previously strong projects with declining activity.")
            lines.append("")
            lines.append("| # | Project | Stars | Velocity | Health |")
            lines.append("|---|---------|-------|----------|--------|")
            for i, r in enumerate(trends["losing_momentum"][:5], 1):
                lines.append(
                    f"| {i} | [{r['repo_full_name']}](https://github.com/{r['repo_full_name']}) "
                    f"| {_format_stars(r.get('stars', 0))} "
                    f"| {r['velocity']:.0f} "
                    f"| {r['health']:.0f} |"
                )
            lines.append("")

        # ── Category Momentum ──
        lines.append("## 📊 Category Distribution")
        lines.append("")
        lines.append("| Category | Projects | Share |")
        lines.append("|----------|----------|-------|")
        total = sum(c["count"] for c in categories)
        for cat in categories:
            if cat["category"] == "Uncategorized":
                continue
            pct = (cat["count"] / total * 100) if total > 0 else 0
            lines.append(
                f"| {cat['category']} | {cat['count']:,} | {pct:.1f}% |"
            )
        lines.append("")

        # ── Top Established ──
        lines.append("## 👑 Established Leaders")
        lines.append("")
        lines.append("Mature, reliable projects with high impact and health.")
        lines.append("")
        for i, r in enumerate(trends.get("established", [])[:5], 1):
            lines.append(
                f"{i}. **[{r['repo_full_name']}](https://github.com/{r['repo_full_name']})** — "
                f"{_format_stars(r.get('stars', 0))} ⭐ | "
                f"Impact: {r['impact']:.0f} | Health: {r['health']:.0f}"
            )
        lines.append("")

        # ── Footer ──
        lines.append("---")
        lines.append("")
        lines.append("*Open Source AI Radar — Discover what is becoming important before everyone else does.*")
        lines.append("")
        lines.append(f"*Data: {stats['repos']:,} repos | {_format_stars(stats['total_stars'])} stars | {stats['scores']:,} scores*")

        # Write report
        report_content = "\n".join(lines)
        filename = f"week-{now.strftime('%Y-W%W')}.md"
        filepath = self.reports_dir / filename
        filepath.write_text(report_content, encoding="utf-8")

        logger.info(f"Generated weekly report: {filepath}")
        print(f"Report saved: {filepath}")

        return str(filepath)

    def get_latest_report(self) -> str | None:
        """Get the path to the most recent report."""
        reports = sorted(self.reports_dir.glob("week-*.md"), reverse=True)
        return str(reports[0]) if reports else None
