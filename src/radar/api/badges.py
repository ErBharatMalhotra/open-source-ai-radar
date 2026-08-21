"""Dynamic SVG Badge Generator for Open Source AI Radar.

Generates embeddable badges that repository maintainers can add to their READMEs.

Badge types:
- radar-score: Overall radar score (0-100)
- trending: Trending position (#1-50)
- breakout: Breakout candidate indicator
- stars: Star count with radar branding

Usage in README.md:
![Radar Score](https://erbharatmalhotra.github.io/open-source-ai-radar/api/badges/{owner}__{repo}/score.svg)
"""

from __future__ import annotations

import logging
from pathlib import Path

from radar.storage.database import Database

logger = logging.getLogger(__name__)

FONT_FAMILY = "Verdana,Geneva,DejaVu Sans,sans-serif"


def _build_svg(
    label: str,
    value: str,
    color: str,
    label_w: int,
    value_w: int,
) -> str:
    """Build a shields.io-style SVG badge."""
    total = label_w + value_w
    lx = label_w / 2
    vx = label_w + value_w / 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' width="{total}" height="20">\n'
        '  <linearGradient id="s" x2="0" y2="100%">\n'
        '    <stop offset="0" stop-color="#fff" stop-opacity=".1"/>\n'
        '    <stop offset="1" stop-opacity=".1"/>\n'
        "  </linearGradient>\n"
        '  <clipPath id="r">\n'
        f'    <rect width="{total}" height="20" rx="3" fill="#fff"/>\n'
        "  </clipPath>\n"
        '  <g clip-path="url(#r)">\n'
        f'    <rect width="{label_w}" height="20" fill="#555"/>\n'
        f'    <rect x="{label_w}" width="{value_w}"'
        f' height="20" fill="{color}"/>\n'
        f'    <rect width="{total}" height="20" fill="url(#s)"/>\n'
        "  </g>\n"
        '  <g fill="#fff" text-anchor="middle"'
        f' font-family="{FONT_FAMILY}"'
        ' text-rendering="geometricPrecision" font-size="11">\n'
        f'    <text x="{lx}" y="15" fill="#010101"'
        f' fill-opacity=".3">{label}</text>\n'
        f'    <text x="{lx}" y="14">{label}</text>\n'
        f'    <text x="{vx}" y="15" fill="#010101"'
        f' fill-opacity=".3">{value}</text>\n'
        f'    <text x="{vx}" y="14">{value}</text>\n'
        "  </g>\n"
        "</svg>"
    )


def _text_width(text: str) -> int:
    """Estimate pixel width for badge text segments."""
    return len(text) * 8 + 16


def _label_width(text: str) -> int:
    """Estimate pixel width for badge label segments."""
    return len(text) * 7 + 10


class BadgeGenerator:
    """Generates dynamic SVG badges for repositories."""

    def __init__(
        self,
        db: Database,
        out_dir: str = "data/exports/api/badges",
    ) -> None:
        self.db = db
        self.out = Path(out_dir)

    def generate_all_badges(self) -> int:
        """Generate badges for all top repos. Returns count."""
        repos = self.db.get_top_repos(100)
        count = 0

        for repo in repos:
            fn = repo["full_name"]
            parts = fn.split("/") if "/" in fn else (fn, "")
            owner, name = parts[0], parts[1]

            badge_dir = self.out / f"{owner}__{name}"
            badge_dir.mkdir(parents=True, exist_ok=True)

            score = repo.get("radar_score", 0)
            (badge_dir / "score.svg").write_text(
                self._score_badge(score),
                encoding="utf-8",
            )
            count += 1

            velocity = repo.get("velocity", 0)
            (badge_dir / "velocity.svg").write_text(
                self._velocity_badge(velocity),
                encoding="utf-8",
            )
            count += 1

            stars = repo.get("stars", 0)
            (badge_dir / "stars.svg").write_text(
                self._stars_badge(stars),
                encoding="utf-8",
            )
            count += 1

        logger.info(
            f"Generated {count} badges for {len(repos)} repos"
        )
        return count

    def get_score_badge(self, full_name: str) -> str | None:
        """Get score badge SVG for a specific repo."""
        parts = (
            full_name.split("/")
            if "/" in full_name
            else (full_name, "")
        )
        owner, name = parts[0], parts[1]
        badge_path = self.out / f"{owner}__{name}" / "score.svg"

        if badge_path.exists():
            return badge_path.read_text()

        with self.db._conn() as conn:
            row = conn.execute(
                """SELECT radar_score FROM scores
                WHERE repo_full_name = ?
                ORDER BY timestamp DESC LIMIT 1""",
                (full_name,),
            ).fetchone()

        if row:
            return self._score_badge(row["radar_score"])
        return None

    def _score_badge(self, score: float) -> str:
        """Generate radar score badge SVG."""
        if score >= 75:
            color = "#00d2a0"
            label = "High"
        elif score >= 50:
            color = "#fdcb6e"
            label = "Mid"
        else:
            color = "#ff6b6b"
            label = "Low"

        value = f"{score:.1f}"
        return _build_svg(
            label, value, color,
            _label_width(label), _text_width(value),
        )

    def _velocity_badge(self, velocity: float) -> str:
        """Generate velocity badge SVG."""
        if velocity >= 70:
            color = "#6c5ce7"
        elif velocity >= 50:
            color = "#a29bfe"
        else:
            color = "#8888a0"

        value = f"{velocity:.0f}"
        label = "Velocity"
        return _build_svg(
            label, value, color,
            _label_width(label), _text_width(value),
        )

    def _stars_badge(self, stars: int) -> str:
        """Generate stars badge SVG."""
        if stars >= 100000:
            color = "#ffd700"
        elif stars >= 10000:
            color = "#fdcb6e"
        else:
            color = "#e0e0e8"

        if stars >= 1000000:
            value = f"{stars / 1_000_000:.1f}M"
        elif stars >= 1000:
            value = f"{stars / 1_000:.1f}k"
        else:
            value = str(stars)

        label = "Stars"
        return _build_svg(
            label, value, color,
            _label_width(label), _text_width(value),
        )
