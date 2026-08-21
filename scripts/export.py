"""Export SQLite data to JSON files for website and public consumption.

This script is called by GitHub Actions after scoring to produce
static JSON files that the Astro website reads at build time.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radar.storage.database import Database


def export_all(db_path: str = "data/radar.db", out_dir: str = "data/exports") -> None:
    """Export all data to JSON files."""
    db = Database(db_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    now = datetime.now(tz=timezone.utc).isoformat()

    # ── repositories.json (all repos, sorted by stars) ──
    repos = db.get_all_repos()
    repos_data = {
        "generated_at": now,
        "total": len(repos),
        "repos": [_clean_repo(r) for r in repos],
    }
    (out / "repositories.json").write_text(
        json.dumps(repos_data, indent=2, default=str)
    )
    print(f"Exported {len(repos)} repos")

    # ── top.json (top 100 by Radar Score) ──
    top = db.get_top_repos(100)
    top_data = {
        "generated_at": now,
        "total": len(repos),
        "repos": [_clean_scored(r) for r in top],
    }
    (out / "top.json").write_text(
        json.dumps(top_data, indent=2, default=str)
    )
    print(f"Exported top {len(top)} repos")

    # ── trending.json (top 50 by velocity) ──
    trending = db.get_top_repos(50, "velocity")
    trending_data = {
        "generated_at": now,
        "repos": [_clean_scored(r) for r in trending],
    }
    (out / "trending.json").write_text(
        json.dumps(trending_data, indent=2, default=str)
    )
    print(f"Exported {len(trending)} trending repos")

    # ── categories.json ──
    categories = _group_by_language(repos)
    (out / "categories.json").write_text(
        json.dumps(categories, indent=2, default=str)
    )
    print(f"Exported {len(categories)} language categories")

    # ── stats.json (summary) ──
    stats = {
        "generated_at": now,
        "total_repos": len(repos),
        "total_stars": sum(r.get("stars", 0) for r in repos),
        "top_languages": _top_languages(repos, 10),
    }
    (out / "stats.json").write_text(
        json.dumps(stats, indent=2, default=str)
    )
    print(f"Exported stats")

    # ── trends.json ──
    try:
        from radar.scoring.trends import TrendEngine
        trend_engine = TrendEngine(db)
        trends_summary = trend_engine.get_trending_summary()
        (out / "trends.json").write_text(
            json.dumps(trends_summary, indent=2, default=str)
        )
        print(f"Exported trends")
    except Exception as e:
        print(f"Warning: Could not export trends: {e}")


def _clean_repo(r: dict) -> dict:
    """Clean a repo dict for JSON export."""
    return {
        "full_name": r.get("full_name", ""),
        "url": r.get("url", ""),
        "description": r.get("description", ""),
        "language": r.get("language"),
        "license": r.get("license"),
        "topics": json.loads(r.get("topics", "[]")) if isinstance(r.get("topics"), str) else r.get("topics", []),
        "stars": r.get("stars", 0),
        "forks": r.get("forks", 0),
        "open_issues": r.get("open_issues", 0),
        "created_at": r.get("created_at"),
        "pushed_at": r.get("pushed_at"),
        "owner_login": r.get("owner_login", ""),
        "owner_avatar": r.get("owner_avatar", ""),
    }


def _clean_scored(r: dict) -> dict:
    """Clean a scored repo dict for JSON export."""
    base = _clean_repo(r)
    base.update({
        "radar_score": r.get("radar_score", 0),
        "impact": r.get("impact", 0),
        "velocity": r.get("velocity", 0),
        "health": r.get("health", 0),
        "global_percentile": r.get("global_percentile", 0),
        "category": r.get("category", ""),
        "sub_category": r.get("sub_category", ""),
        "maturity": r.get("maturity", ""),
    })
    return base


def _group_by_language(repos: list[dict]) -> dict:
    """Group repos by language with counts."""
    langs: dict[str, int] = {}
    for r in repos:
        lang = r.get("language") or "Unknown"
        langs[lang] = langs.get(lang, 0) + 1
    return dict(sorted(langs.items(), key=lambda x: -x[1]))


def _top_languages(repos: list[dict], n: int = 10) -> dict:
    """Top N languages by repo count."""
    langs = _group_by_language(repos)
    return dict(list(langs.items())[:n])


if __name__ == "__main__":
    export_all()
