"""Export SQLite data to JSON files for website and public consumption.

This script is called by GitHub Actions after scoring to produce
static JSON files that the Astro website reads at build time.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radar.storage.database import Database


def export_all(db_path: str = "data/radar.db", out_dir: str = "data/exports") -> None:
    """Export all data to JSON files."""
    db = Database(db_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    now = datetime.now(tz=UTC).isoformat()

    # ── repositories.json (all repos, sorted by stars) ──
    repos = db.get_all_repos()
    repos_data = {
        "generated_at": now,
        "total": len(repos),
        "repos": [_clean_repo(r) for r in repos],
    }
    (out / "repositories.json").write_text(
        json.dumps(repos_data, indent=2, default=str),
        encoding="utf-8",
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
        json.dumps(top_data, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Exported top {len(top)} repos")

    # ── trending.json (top 50 by velocity) ──
    trending = db.get_top_repos(50, "velocity")
    trending_data = {
        "generated_at": now,
        "repos": [_clean_scored(r) for r in trending],
    }
    (out / "trending.json").write_text(
        json.dumps(trending_data, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Exported {len(trending)} trending repos")

    # ── categories.json ──
    categories = _group_by_language(repos)
    (out / "categories.json").write_text(
        json.dumps(categories, indent=2, default=str),
        encoding="utf-8",
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
        json.dumps(stats, indent=2, default=str),
        encoding="utf-8",
    )
    print("Exported stats")

    # ── trends.json ──
    try:
        from radar.scoring.trends import TrendEngine
        trend_engine = TrendEngine(db)
        trends_summary = trend_engine.get_trending_summary()
        (out / "trends.json").write_text(
            json.dumps(trends_summary, indent=2, default=str),
            encoding="utf-8",
        )
        print("Exported trends")
    except Exception as e:
        print(f"Warning: Could not export trends: {e}")

    # ── project detail pages ──
    export_project_pages(db, out)

    # ── project index (for search/listing) ──
    export_project_index(db, out)

    # ── breakout detection ──
    export_breakouts(db, out)

    # ── anomaly detection ──
    export_anomalies(db, out)

    # ── category intelligence ──
    export_category_intelligence(db, out)

    # ── historical data for charts ──
    export_history(db, out)


def export_project_pages(db: Database, out: Path) -> None:
    """Export individual project detail pages."""
    projects_dir = out / "projects"
    projects_dir.mkdir(exist_ok=True)

    repos = db.get_all_repos()
    count = 0

    for repo in repos:
        fn = repo["full_name"]
        owner, name = fn.split("/") if "/" in fn else (fn, "")

        # Get latest score
        with db._conn() as conn:
            score_row = conn.execute(
                """SELECT * FROM scores WHERE repo_full_name = ?
                ORDER BY timestamp DESC LIMIT 1""",
                (fn,),
            ).fetchone()

        # Get AI analysis
        with db._conn() as conn:
            analysis_row = conn.execute(
                """SELECT * FROM ai_analysis WHERE repo_full_name = ?
                ORDER BY timestamp DESC LIMIT 1""",
                (fn,),
            ).fetchone()

        # Get latest growth
        with db._conn() as conn:
            growth_row = conn.execute(
                """SELECT * FROM growth_metrics WHERE repo_full_name = ?
                ORDER BY timestamp DESC LIMIT 1""",
                (fn,),
            ).fetchone()

        # Get snapshot count
        with db._conn() as conn:
            snap_count = conn.execute(
                "SELECT COUNT(*) FROM snapshots WHERE repo_full_name = ?",
                (fn,),
            ).fetchone()[0]

        project_data = {
            "full_name": fn,
            "url": repo.get("url", ""),
            "description": repo.get("description", ""),
            "language": repo.get("language"),
            "license": repo.get("license"),
            "topics": (
                json.loads(repo.get("topics", "[]"))
                if isinstance(repo.get("topics"), str)
                else repo.get("topics", [])
            ),
            "stars": repo.get("stars", 0),
            "forks": repo.get("forks", 0),
            "open_issues": repo.get("open_issues", 0),
            "watchers": repo.get("watchers", 0),
            "created_at": repo.get("created_at"),
            "pushed_at": repo.get("pushed_at"),
            "owner_login": repo.get("owner_login", ""),
            "owner_avatar": repo.get("owner_avatar", ""),
        }

        # Add score data
        if score_row:
            project_data["radar_score"] = score_row["radar_score"]
            project_data["impact"] = score_row["impact"]
            project_data["velocity"] = score_row["velocity"]
            project_data["health"] = score_row["health"]
            project_data["global_percentile"] = score_row["global_percentile"]
        else:
            project_data["radar_score"] = 0
            project_data["impact"] = 0
            project_data["velocity"] = 0
            project_data["health"] = 0
            project_data["global_percentile"] = 0

        # Add analysis
        if analysis_row:
            project_data["category"] = analysis_row["category"]
            project_data["sub_category"] = analysis_row["sub_category"]
            project_data["summary"] = analysis_row["summary"]
            project_data["maturity"] = analysis_row["maturity"]

        # Add growth
        if growth_row:
            project_data["stars_7d"] = growth_row["stars_7d"]
            project_data["stars_30d"] = growth_row["stars_30d"]
            project_data["stars_90d"] = growth_row["stars_90d"]
            project_data["star_growth_rate_7d"] = growth_row["star_growth_rate_7d"]
            project_data["star_growth_rate_30d"] = growth_row["star_growth_rate_30d"]
            project_data["star_growth_acceleration"] = growth_row["star_growth_acceleration"]
            project_data["forks_7d"] = growth_row["forks_7d"]
            project_data["forks_30d"] = growth_row["forks_30d"]
            project_data["days_since_last_push"] = growth_row["days_since_last_push"]
            project_data["freshness_score"] = growth_row["freshness_score"]

        project_data["snapshot_count"] = snap_count

        # Add why_trending
        why = db.get_why_trending(fn)
        if why:
            project_data["why_trending"] = why

        # Write to projects directory
        project_file = projects_dir / f"{owner}__{name}.json"
        project_file.write_text(json.dumps(project_data, indent=2, default=str), encoding="utf-8")
        count += 1

    print(f"Exported {count} project detail pages")


def export_project_index(db: Database, out: Path) -> None:
    """Export a lightweight project index for search/listing."""
    repos = db.get_all_repos()

    # Get latest scores for ranking
    with db._conn() as conn:
        score_rows = conn.execute(
            """SELECT repo_full_name, radar_score, impact, velocity, health
            FROM scores WHERE timestamp = (SELECT MAX(timestamp) FROM scores)
            ORDER BY radar_score DESC"""
        ).fetchall()

    score_map = {r["repo_full_name"]: dict(r) for r in score_rows}

    # Get categories
    with db._conn() as conn:
        analysis_rows = conn.execute(
            """SELECT repo_full_name, category, sub_category
            FROM ai_analysis"""
        ).fetchall()

    analysis_map = {r["repo_full_name"]: dict(r) for r in analysis_rows}

    index = []
    for repo in repos:
        fn = repo["full_name"]
        entry = {
            "full_name": fn,
            "description": repo.get("description", "")[:200],
            "language": repo.get("language"),
            "stars": repo.get("stars", 0),
            "owner_avatar": repo.get("owner_avatar", ""),
        }

        if fn in score_map:
            entry.update(score_map[fn])

        if fn in analysis_map:
            entry["category"] = analysis_map[fn].get("category", "")
            entry["sub_category"] = analysis_map[fn].get("sub_category", "")

        index.append(entry)

    index_data = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "total": len(index),
        "projects": index,
    }

    (out / "projects-index.json").write_text(
        json.dumps(index_data, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Exported project index ({len(index)} projects)")


def export_breakouts(db: Database, out: Path) -> None:
    """Export breakout detection results."""
    try:
        from radar.analysis.breakout_detector import BreakoutDetector
        detector = BreakoutDetector(db)
        summary = detector.get_breakout_summary()

        (out / "breakouts.json").write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Exported breakouts ({summary['total_candidates']} candidates)")
    except Exception as e:
        print(f"Warning: Could not export breakouts: {e}")


def export_anomalies(db: Database, out: Path) -> None:
    """Export anomaly detection results."""
    try:
        from radar.analysis.anomaly_detector import AnomalyDetector
        detector = AnomalyDetector(db)
        summary = detector.get_anomaly_summary()

        (out / "anomalies.json").write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Exported anomalies ({summary['total_anomalies']} detected)")
    except Exception as e:
        print(f"Warning: Could not export anomalies: {e}")


def export_category_intelligence(db: Database, out: Path) -> None:
    """Export category intelligence data."""
    try:
        from radar.analysis.category_tracker import CategoryTracker
        tracker = CategoryTracker(db)

        # Compute fresh momentum
        momentums = tracker.compute_momentum()

        # Export category rankings
        rankings = tracker.get_category_comparison()
        (out / "category-intelligence.json").write_text(
            json.dumps({
                "generated_at": datetime.now(tz=UTC).isoformat(),
                "categories": rankings,
            }, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Exported category intelligence ({len(rankings)} categories)")

        # Export category history for charts
        history_dir = out / "category-history"
        history_dir.mkdir(exist_ok=True)

        for m in momentums:
            cat = m["category"]
            history = db.get_category_momentum_history(cat, limit=90)
            if history:
                (history_dir / f"{cat}.json").write_text(
                    json.dumps({
                        "category": cat,
                        "history": [dict(h) for h in reversed(history)],
                    }, indent=2, default=str),
                    encoding="utf-8",
                )

        print(f"Exported category history for {len(momentums)} categories")
    except Exception as e:
        print(f"Warning: Could not export category intelligence: {e}")


def export_history(db: Database, out: Path) -> None:
    """Export historical data for charts on project pages."""
    history_dir = out / "history"
    history_dir.mkdir(exist_ok=True)

    # Get top 50 repos by score
    top_repos = db.get_top_repos(50)

    for repo in top_repos:
        fn = repo["full_name"]
        owner, name = fn.split("/") if "/" in fn else (fn, "")

        # Get snapshots history
        snapshots = db.get_snapshots(fn, limit=90)

        if not snapshots:
            continue

        # Get scores history
        with db._conn() as conn:
            score_rows = conn.execute(
                """SELECT timestamp, radar_score, impact, velocity, health
                FROM scores WHERE repo_full_name = ?
                ORDER BY timestamp ASC""",
                (fn,),
            ).fetchall()

        # Get growth history
        with db._conn() as conn:
            growth_rows = conn.execute(
                """SELECT timestamp, stars_7d, stars_30d, stars_90d,
                   star_growth_rate_7d, star_growth_rate_30d,
                   freshness_score
                FROM growth_metrics WHERE repo_full_name = ?
                ORDER BY timestamp ASC""",
                (fn,),
            ).fetchall()

        history = {
            "full_name": fn,
            "snapshots": [
                {
                    "timestamp": s["timestamp"],
                    "stars": s["stars"],
                    "forks": s["forks"],
                    "open_issues": s["open_issues"],
                    "contributors": s["contributors"],
                }
                for s in reversed(snapshots)  # oldest first
            ],
            "scores": [
                {
                    "timestamp": s["timestamp"],
                    "radar_score": s["radar_score"],
                    "impact": s["impact"],
                    "velocity": s["velocity"],
                    "health": s["health"],
                }
                for s in score_rows
            ],
            "growth": [
                {
                    "timestamp": g["timestamp"],
                    "stars_7d": g["stars_7d"],
                    "stars_30d": g["stars_30d"],
                    "stars_90d": g["stars_90d"],
                    "star_growth_rate_7d": g["star_growth_rate_7d"],
                    "star_growth_rate_30d": g["star_growth_rate_30d"],
                    "freshness_score": g["freshness_score"],
                }
                for g in growth_rows
            ],
        }

        history_file = history_dir / f"{owner}__{name}.json"
        history_file.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")

    print(f"Exported history for {len(top_repos)} top repos")


def _clean_repo(r: dict) -> dict:
    """Clean a repo dict for JSON export."""
    return {
        "full_name": r.get("full_name", ""),
        "url": r.get("url", ""),
        "description": r.get("description", ""),
        "language": r.get("language"),
        "license": r.get("license"),
        "topics": (
            json.loads(r.get("topics", "[]"))
            if isinstance(r.get("topics"), str)
            else r.get("topics", [])
        ),
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


def export_health(db_path: str = "data/radar.db", out_dir: str = "data/exports") -> None:
    """Export pipeline health report."""
    try:
        from radar.monitoring.pipeline_monitor import PipelineMonitor
        db = Database(db_path)
        monitor = PipelineMonitor(db)
        report = monitor.get_health_report()

        (Path(out_dir) / "health.json").write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Exported health report (status: {report['overall_status']})")
    except Exception as e:
        print(f"Warning: Could not export health report: {e}")


def export_api(db_path: str = "data/radar.db", out_dir: str = "data/exports/api") -> None:
    """Generate public API files."""
    try:
        from radar.api.endpoints import PublicAPI
        db = Database(db_path)
        api = PublicAPI(db, out_dir)
        counts = api.generate_all()
        print(f"Generated API endpoints: {counts}")
    except Exception as e:
        print(f"Warning: Could not generate API: {e}")


def export_badges(db_path: str = "data/radar.db", out_dir: str = "data/exports/api/badges") -> None:
    """Generate developer badges for top repos."""
    try:
        from radar.api.badges import BadgeGenerator
        db = Database(db_path)
        generator = BadgeGenerator(db, out_dir)
        count = generator.generate_all_badges()
        print(f"Generated {count} developer badges")
    except Exception as e:
        print(f"Warning: Could not generate badges: {e}")


if __name__ == "__main__":
    export_all()
    export_health()
    export_api()
    export_badges()
