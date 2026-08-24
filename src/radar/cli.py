"""CLI entry point for Open Source AI Radar."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import click

from radar import __version__

# Fix Windows console encoding for emoji output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("radar")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.version_option(version=__version__)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def main(verbose: bool) -> None:
    """Open Source AI Radar — Discover what is becoming important."""
    setup_logging(verbose)


@main.command()
def smart_queries() -> None:
    """Show smart discovery queries generated from existing data."""
    from radar.discovery.smart_discovery import SmartDiscoveryEngine
    from radar.storage.database import Database

    db = Database()
    engine = SmartDiscoveryEngine(db)

    click.echo("\n  🧠 Smart Discovery Queries")
    click.echo(f"  {'─' * 60}")

    queries = engine.generate_smart_queries()

    if not queries:
        click.echo("  No smart queries generated yet.")
        click.echo("  Need more data for pattern detection.")
        return

    for i, q in enumerate(queries, 1):
        click.echo(f"  {i:>2}. [{q['source']}] {q['label']}")
        click.echo(f"      Query: {q['query']}")

    click.echo(f"\n  Total: {len(queries)} smart queries")

    # Show stats
    stats = engine.get_smart_stats()
    click.echo(f"  Trending terms: {len(stats['trending_terms'])}")
    click.echo(f"  Emerging keywords: {len(stats['emerging_keywords'])}")
    click.echo(f"  Category gaps: {stats['category_gaps']}")
    click.echo()


@main.command()
@click.option("--category", "-c", help="Discover repos for a specific category")
@click.option("--query", "-q", help="Custom search query")
@click.option("--limit", "-n", default=100, help="Max repos per query")
@click.option("--output", "-o", default="data/repositories.json", help="Output file")
def discover(category: str | None, query: str | None, limit: int, output: str) -> None:
    """Discover open-source AI repositories on GitHub."""
    asyncio.run(_discover(category, query, limit, output))


async def _discover(
    category: str | None, query: str | None, limit: int, output: str
) -> None:
    from radar.discovery.search import DiscoveryEngine

    engine = DiscoveryEngine()

    click.echo("🔍 Starting repository discovery...")
    if category:
        click.echo(f"   Category: {category}")
    if query:
        click.echo(f"   Query: {query}")

    results = await engine.run(category=category, custom_query=query, max_per_query=limit)

    # Save results
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    existing: list[dict] = []
    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text())
        except (json.JSONDecodeError, ValueError):
            existing = []

    # Deduplicate by full_name
    seen = {r["full_name"] for r in existing}
    new_count = 0
    for repo in results:
        if repo["full_name"] not in seen:
            existing.append(repo)
            seen.add(repo["full_name"])
            new_count += 1

    # Sort by stars descending
    existing.sort(key=lambda r: r.get("stars", 0), reverse=True)

    output_path.write_text(json.dumps(existing, indent=2, default=str))

    click.echo("\n✅ Discovery complete!")
    click.echo(f"   Found: {len(results)} repos this run")
    click.echo(f"   New: {new_count} repos added")
    click.echo(f"   Total: {len(existing)} repos in database")
    click.echo(f"   Saved to: {output}")

    from radar.github.client import GitHubClient

    client = GitHubClient()
    client.log_status()


@main.command()
@click.argument("full_name")  # owner/name
def repo(full_name: str) -> None:
    """Show details for a single repository."""
    asyncio.run(_repo(full_name))


async def _repo(full_name: str) -> None:
    from radar.github.client import GitHubClient

    parts = full_name.split("/")
    if len(parts) != 2:
        click.echo("❌ Format: owner/name (e.g., anthropics/claude-code)")
        sys.exit(1)

    owner, name = parts

    async with GitHubClient() as client:
        click.echo(f"📡 Fetching {full_name}...")
        data = await client.get_repo(owner, name)

        if not data:
            click.echo(f"❌ Repository not found: {full_name}")
            sys.exit(1)

        click.echo(f"\n{'=' * 60}")
        click.echo(f"  {data['full_name']}")
        click.echo(f"{'=' * 60}")
        click.echo(f"  ⭐ Stars:      {data['stars']:,}")
        click.echo(f"  🍴 Forks:      {data['forks']:,}")
        click.echo(f"  📋 Open Issues: {data['open_issues']:,}")
        click.echo(f"  👁️  Watchers:    {data['watchers']:,}")
        click.echo(f"  🗣️  Users:       {data['mentionable_users']:,}")
        click.echo(f"  💻 Language:    {data['language'] or 'N/A'}")
        click.echo(f"  📜 License:     {data['license'] or 'N/A'}")
        click.echo(f"  🏷️  Topics:      {', '.join(data['topics']) or 'None'}")
        click.echo(f"  📅 Created:     {data['created_at']}")
        click.echo(f"  🔄 Last push:   {data['pushed_at']}")
        if data["latest_release_tag"]:
            tag = data["latest_release_tag"]
            date = data["latest_release_date"]
            click.echo(f"  🚀 Latest:      {tag} ({date})")
        click.echo(f"  🔗 URL:         {data['url']}")
        if data["description"]:
            click.echo(f"\n  📝 {data['description'][:200]}")

        client.log_status()


@main.command()
def rate_limit() -> None:
    """Check GitHub API rate limit status."""
    asyncio.run(_rate_limit())


async def _rate_limit() -> None:
    from radar.github.client import GitHubClient

    async with GitHubClient() as client:
        data = await client.get_rate_limit()
        if "resources" in data:
            for name, info in data["resources"].items():
                remaining = info["remaining"]
                limit = info["limit"]
                reset = datetime.fromtimestamp(info["reset"], tz=UTC)
                click.echo(
                    f"  {name}: {remaining}/{limit} remaining "
                    f"(resets {reset.strftime('%H:%M:%S UTC')})"
                )
        else:
            click.echo(f"  Error: {data}")


@main.command()
def health() -> None:
    """Run pipeline health checks."""
    from radar.monitoring.pipeline_monitor import PipelineMonitor
    from radar.storage.database import Database

    db = Database()
    monitor = PipelineMonitor(db)

    report = monitor.get_health_report()

    status_icons = {
        "healthy": "✅",
        "warning": "⚠️",
        "critical": "🚨",
        "unknown": "❓",
    }

    click.echo("\n  🏥 Pipeline Health Report")
    click.echo(f"  {'─' * 50}")
    icon = status_icons.get(report['overall_status'], '?')
    status = report['overall_status'].upper()
    click.echo(f"  Overall Status: {icon} {status}")
    click.echo()

    for check in report["checks"]:
        icon = status_icons.get(check["status"], "?")
        click.echo(f"  {icon} {check['name']}")

        for key, value in check.items():
            if key not in ("name", "status", "issues"):
                if isinstance(value, dict):
                    for k, v in value.items():
                        msg = f"      {k}: {v:,}" if isinstance(v, int) else f"      {k}: {v}"
                        click.echo(msg)
                elif isinstance(value, (int, float)):
                    if isinstance(value, int):
                        msg = f"      {key}: {value:,}"
                    else:
                        msg = f"      {key}: {value}"
                    click.echo(msg)
                elif isinstance(value, str) and value:
                    click.echo(f"      {key}: {value}")

        for issue in check.get("issues", []):
            click.echo(f"      ❌ {issue}")

        click.echo()

    click.echo()


@main.command()
def status() -> None:
    """Show project status and database stats."""
    click.echo(f"\n  Open Source AI Radar v{__version__}")
    click.echo(f"  {'─' * 40}")

    # Try SQLite first, fall back to JSON
    db_path = Path("data/radar.db")
    json_path = Path("data/repositories.json")

    if db_path.exists():
        from radar.storage.database import Database

        db = Database(db_path)
        stats = db.get_stats()
        click.echo(f"  Repos tracked: {stats['repos']:,}")
        click.echo(f"  Total stars:   {stats['total_stars']:,}")
        click.echo(f"  Snapshots:     {stats['snapshots']:,}")
        click.echo(f"  Analyzed:      {stats.get('analyzed', 0):,}")
        click.echo(f"  Scores:        {stats['scores']:,}")
        if stats.get("snapshot_dates"):
            click.echo(f"  Latest data:   {stats['snapshot_dates'][-1]}")
        if stats.get("languages"):
            top_langs = list(stats["languages"].items())[:5]
            langs_str = ", ".join(f"{lang}({c})" for lang, c in top_langs)
            click.echo(f"  Top langs:     {langs_str}")
    elif json_path.exists():
        repos = json.loads(json_path.read_text())
        click.echo(f"  Repos tracked: {len(repos)}")
        if repos:
            top = repos[0]
            click.echo(f"  Top repo: {top.get('full_name', 'N/A')} ({top.get('stars', 0):,})")
            total_stars = sum(r.get("stars", 0) for r in repos)
            click.echo(f"  Total stars: {total_stars:,}")
    else:
        click.echo("  No data yet. Run: radar discover")

    click.echo()


@main.command()
@click.option("--limit", "-n", default=100, help="Max repos to snapshot")
def snapshot(limit: int) -> None:
    """Capture current metrics for all tracked repositories."""
    asyncio.run(_snapshot(limit))


async def _snapshot(limit: int) -> None:
    from radar.github.client import GitHubClient
    from radar.scoring.snapshots import SnapshotEngine
    from radar.storage.database import Database

    db = Database()
    engine = SnapshotEngine(db)

    click.echo(f"\n  Capturing snapshots (max {limit} repos)...")

    async with GitHubClient() as client:
        count = await engine.snapshot_all(client, max_repos=limit)

    click.echo(f"  Done! {count} repos snapshotted.")
    click.echo(f"  Database: {db.db_path}")


@main.command()
def score() -> None:
    """Compute three-axis scores for all tracked repositories."""
    from radar.scoring.engine import ScoringEngine
    from radar.storage.database import Database

    db = Database()
    engine = ScoringEngine(db)

    click.echo("\n  Computing scores...")
    count = engine.compute_all_scores()

    click.echo(f"  Scored {count} repositories.")

    # Show top 10
    top = engine.get_rankings(10)
    if top:
        click.echo("\n  Top 10 by Radar Score:")
        hdr = f"  {'#':>3}  {'Score':>6}  {'Impact':>6}  {'Vel':>6}"
        hdr += f"  {'Health':>6}  {'Repo':<40}"
        click.echo(hdr)
        click.echo(f"  {'─' * 80}")
        for i, r in enumerate(top, 1):
            click.echo(
                f"  {i:>3}  {r['radar_score']:>6.1f}  "
                f"{r['impact']:>6.1f}  {r['velocity']:>6.1f}  "
                f"{r['health']:>6.1f}  {r['repo_full_name']:<40}"
            )


@main.command()
def import_json() -> None:
    """Import repos from JSON into SQLite database."""
    from radar.storage.database import Database

    json_path = Path("data/repositories.json")
    if not json_path.exists():
        click.echo("  No data/repositories.json found. Run: radar discover")
        return

    repos = json.loads(json_path.read_text())
    db = Database()

    click.echo(f"  Importing {len(repos)} repos into SQLite...")
    new, updated = db.upsert_repos(repos)
    click.echo(f"  Done! {new} new, {updated} updated.")
    click.echo(f"  Database: {db.db_path}")


@main.command()
@click.option("--ai", is_flag=True, help="Also run AI analysis on top repos")
@click.option("--ai-limit", default=100, help="Max repos for AI analysis")
@click.option("--force", is_flag=True, help="Re-analyze all repos")
def classify(ai: bool, ai_limit: int, force: bool) -> None:
    """Classify all repos into AI categories."""
    from radar.analysis.engine import AnalysisEngine
    from radar.storage.database import Database

    db = Database()
    engine = AnalysisEngine(db)

    click.echo("  Running category classification...")
    max_ai = ai_limit if ai else 0
    stats = engine.analyze_all(max_ai_repos=max_ai, force=force)

    click.echo(f"  Classified: {stats['classified']} repos")
    click.echo(f"  AI analyzed: {stats['ai_analyzed']} repos")
    click.echo(f"  Skipped (already analyzed): {stats['skipped']} repos")

    # Show category distribution
    dist = engine.get_category_distribution()
    if dist:
        click.echo("\n  Category Distribution:")
        for cat, count in list(dist.items())[:15]:
            bar = "#" * min(30, count // 10)
            click.echo(f"    {cat:<30} {count:>5}  {bar}")


@main.command()
def trends() -> None:
    """Show current trends — rising stars, hidden gems, anomalies."""
    from radar.scoring.trends import TrendEngine
    from radar.storage.database import Database

    db = Database()
    engine = TrendEngine(db)
    data = engine.detect_all()

    click.echo("\n  Rising Stars (high velocity)")
    click.echo(f"  {'-'*70}")
    for i, r in enumerate(data["rising_stars"][:10], 1):
        click.echo(
            f"  {i:>3}. Vel:{r['velocity']:>5.0f}  "
            f"Score:{r['radar_score']:>5.0f}  "
            f"Stars:{r['stars']:>7,}  {r['repo_full_name'][:38]}"
        )

    click.echo("\n  Hidden Gems (low stars, high potential)")
    click.echo(f"  {'-'*70}")
    for i, r in enumerate(data["hidden_gems"][:10], 1):
        click.echo(
            f"  {i:>3}. Vel:{r['velocity']:>5.0f}  "
            f"Health:{r['health']:>5.0f}  "
            f"Stars:{r['stars']:>7,}  {r['repo_full_name'][:38]}"
        )

    click.echo("\n  Losing Momentum")
    click.echo(f"  {'-'*70}")
    for i, r in enumerate(data["losing_momentum"][:5], 1):
        click.echo(
            f"  {i:>3}. Vel:{r['velocity']:>5.0f}  "
            f"Health:{r['health']:>5.0f}  "
            f"Stars:{r['stars']:>7,}  {r['repo_full_name'][:38]}"
        )

    click.echo(f"\n  Summary: {len(data['rising_stars'])} rising, "
              f"{len(data['hidden_gems'])} gems, "
              f"{len(data['losing_momentum'])} losing momentum")
    click.echo()


@main.command()
def category_momentum() -> None:
    """Compute and display category momentum scores."""
    from radar.analysis.category_tracker import CategoryTracker
    from radar.storage.database import Database

    db = Database()
    tracker = CategoryTracker(db)

    click.echo("\n  Computing category momentum...")
    momentums = tracker.compute_momentum()

    if not momentums:
        click.echo("  No categorized repos found. Run: radar classify")
        return

    click.echo("\n  Category Intelligence")
    click.echo(f"  {'─' * 75}")
    hdr = f"  {'#':>3}  {'Category':<25} {'Tracked':>8} {'New':>5}"
    hdr += f"  {'Vel':>6}  {'Health':>6}  {'Trend':<10}"
    click.echo(hdr)
    click.echo(f"  {'─' * 75}")

    for i, m in enumerate(momentums, 1):
        trend_icon = {
            "rising": "🔥",
            "stable": "➡️ ",
            "declining": "📉",
            "new": "🆕",
        }.get(m["trend"], "  ")

        click.echo(
            f"  {i:>3}  {m['category']:<25} {m['total_tracked']:>8} "
            f"{m['new_this_period']:>5} {m['avg_velocity']:>6.1f} "
            f"{m['avg_health']:>6.1f} {trend_icon} {m['trend']}"
        )

    click.echo(f"\n  Total: {len(momentums)} categories")
    click.echo()


@main.command()
@click.option(
    "--type", "anomaly_type",
    help="Filter by anomaly type: star_spikes, fork_spikes, "
         "score_jumps, velocity_anomalies, health_drops",
)
@click.option("--limit", "-n", default=10, help="Max anomalies to show")
def anomalies(anomaly_type: str | None, limit: int) -> None:
    """Detect anomalies — sudden spikes, score jumps, health drops."""
    from radar.analysis.anomaly_detector import AnomalyDetector
    from radar.storage.database import Database

    db = Database()
    detector = AnomalyDetector(db)

    if anomaly_type:
        # Single type
        method = getattr(detector, f"detect_{anomaly_type}", None)
        if not method:
            click.echo(f"  Unknown anomaly type: {anomaly_type}")
            types = ("star_spikes, fork_spikes, score_jumps,"
                     " velocity_anomalies, health_drops")
            click.echo(f"  Types: {types}")
            return
        results = {anomaly_type: method()}
    else:
        results = detector.detect_all()

    click.echo("\n  🚨 Anomaly Detection")
    click.echo(f"  {'─' * 70}")

    type_labels = {
        "star_spikes": "⭐ Star Spikes",
        "fork_spikes": "🍴 Fork Spikes",
        "score_jumps": "📊 Score Jumps",
        "velocity_anomalies": "🚀 Velocity Anomalies",
        "health_drops": "🏥 Health Drops",
    }

    total = 0
    for atype, items in results.items():
        if not items:
            continue

        label = type_labels.get(atype, atype)
        click.echo(f"\n  {label} ({len(items)} detected)")
        click.echo(f"  {'-' * 60}")

        for i, a in enumerate(items[:limit], 1):
            dev = a.get("deviation", a.get("change", 0))
            click.echo(
                f"  {i:>3}. {a['repo_full_name'][:35]:<35} "
                f"Stars:{a.get('stars', 0):>7,}  "
                f"Dev:{dev:>6.1f}x"
            )
            if a.get("cause"):
                click.echo(f"      Cause: {a['cause']}")
            total += 1

    click.echo(f"\n  Total: {total} anomalies detected")
    click.echo()


@main.command()
@click.option("--limit", "-n", default=25, help="Max breakout candidates to show")
def breakouts(limit: int) -> None:
    """Detect breakout candidates — repos about to blow up."""
    from radar.analysis.breakout_detector import BreakoutDetector
    from radar.storage.database import Database

    db = Database()
    detector = BreakoutDetector(db)

    click.echo("\n  🔥 Detecting breakout candidates...")
    candidates = detector.detect_breakouts(limit)

    if not candidates:
        click.echo("  No breakout candidates found yet.")
        click.echo("  Need more snapshot data for detection.")
        return

    click.echo(f"\n  Breakout Candidates ({len(candidates)} detected)")
    click.echo(f"  {'─' * 85}")
    hdr = f"  {'#':>3}  {'Score':>6}  {'Vel':>5}  {'Accel':>6}"
    hdr += f"  {'Health':>6}  {'Stars':>7}  {'Repo':<35}"
    click.echo(hdr)
    click.echo(f"  {'─' * 85}")

    for i, c in enumerate(candidates[:limit], 1):
        click.echo(
            f"  {i:>3}  {c['breakout_score']:>6.1f}  "
            f"{c['velocity']:>5.0f}  {c['star_growth_acceleration']:>5.2f}x  "
            f"{c['health']:>6.0f}  {c['stars']:>7,}  {c['repo_full_name'][:35]}"
        )
        if c.get('stars_7d', 0) > 0:
            click.echo(
                f"      7d: +{c['stars_7d']} ⭐  "
                f"Rate: {c['star_growth_rate_7d']:.1f}/day  "
                f"Cat: {c.get('category', 'N/A')}"
            )

    click.echo(f"\n  Total: {len(candidates)} breakout candidates")
    click.echo()


@main.command()
@click.option("--limit", "-n", default=25, help="Max repos to analyze")
def why_trending(limit: int) -> None:
    """Analyze why top trending repos are gaining attention."""
    from radar.analysis.why_trending import WhyTrendingAnalyzer
    from radar.storage.database import Database

    db = Database()
    analyzer = WhyTrendingAnalyzer(db)

    click.echo("\n  💡 Analyzing why repos are trending...")
    results = analyzer.analyze_all_trending(limit)

    if not results:
        click.echo("  No trending repos found. Run: radar score")
        return

    click.echo("\n  Why is it trending?")
    click.echo(f"  {'─' * 75}")

    for i, r in enumerate(results[:15], 1):
        click.echo(f"\n  {i}. {r['repo_full_name']}")
        click.echo(f"     {r['explanation']}")
        click.echo(f"     Confidence: {r['confidence']:.0%}")

    click.echo(f"\n  Analyzed {len(results)} repos")
    click.echo()


@main.command()
def category_compare() -> None:
    """Compare categories across key metrics."""
    from radar.analysis.category_tracker import CategoryTracker
    from radar.storage.database import Database

    db = Database()
    tracker = CategoryTracker(db)
    comparison = tracker.get_category_comparison()

    if not comparison:
        click.echo("  No category data. Run: radar category-momentum")
        return

    click.echo("\n  Category Comparison")
    click.echo(f"  {'─' * 90}")
    hdr = f"  {'Category':<25} {'Tracked':>8} {'New':>5} {'Avg ⭐':>8}"
    hdr += f"  {'Vel':>6}  {'Health':>6}  {'Momentum':>9}  {'Trend':<10}"
    click.echo(hdr)
    click.echo(f"  {'─' * 90}")

    for c in comparison:
        trend_icon = {
            "rising": "🔥",
            "stable": "➡️ ",
            "declining": "📉",
            "new": "🆕",
        }.get(c["trend"], "  ")

        click.echo(
            f"  {c['category']:<25} {c['tracked']:>8} {c['new']:>5} "
            f"{c['avg_stars']:>8,.0f} {c['velocity']:>6.1f} "
            f"{c['health']:>6.1f} {c['momentum']:>9.1f} {trend_icon} {c['trend']}"
        )
    click.echo()


@main.command()
def categories() -> None:
    """Show category distribution and momentum."""
    from radar.scoring.trends import TrendEngine
    from radar.storage.database import Database

    db = Database()
    engine = TrendEngine(db)
    cats = engine.get_category_momentum()

    click.echo("\n  Category Distribution")
    click.echo(f"  {'-'*50}")
    total = sum(c["count"] for c in cats)
    for c in cats:
        bar = "#" * min(35, c["count"] // 15)
        pct = (c["count"] / total * 100) if total > 0 else 0
        click.echo(
            f"  {c['category']:<30} {c['count']:>5}  ({pct:>4.1f}%)  {bar}"
        )
    click.echo(f"  {'-'*50}")
    click.echo(f"  {'Total':<30} {total:>5}")
    click.echo()


@main.command()
def gems() -> None:
    """Show hidden gems — low stars, high potential."""
    from radar.scoring.trends import TrendEngine
    from radar.storage.database import Database

    db = Database()
    engine = TrendEngine(db)
    gems_list = engine.get_hidden_gems(25)

    click.echo("\n  Hidden Gems (10-5k stars, high velocity + health)")
    click.echo(f"  {'-'*75}")
    click.echo(f"  {'#':>3}  {'Vel':>5}  {'Health':>6}  {'Score':>6}  {'Stars':>7}  {'Repo':<38}")
    click.echo(f"  {'-'*75}")
    for i, r in enumerate(gems_list, 1):
        click.echo(
            f"  {i:>3}  {r['velocity']:>5.0f}  "
            f"{r['health']:>6.0f}  {r['radar_score']:>6.0f}  "
            f"{r['stars']:>7,}  {r['repo_full_name'][:38]}"
        )
    click.echo()


@main.command()
@click.option("--full", is_flag=True, help="Force full processing (ignore change detection)")
@click.option("--limit", "-n", default=None, type=int, help="Max repos to process")
def process(full: bool, limit: int | None) -> None:
    """Incremental pipeline: detect changes, snapshot, score, export.

    This is the main entry point for daily operations.
    It only processes repos that have changed since last run.
    """
    asyncio.run(_process(full, limit))


async def _process(full: bool, limit: int | None) -> None:
    from radar.github.client import GitHubClient
    from radar.processing.change_detector import ChangeDetector
    from radar.scoring.engine import ScoringEngine
    from radar.scoring.snapshots import SnapshotEngine
    from radar.storage.database import Database

    db = Database()
    detector = ChangeDetector(db)

    # Step 1: Get all repos
    all_repos = db.get_all_repos()
    if not all_repos:
        click.echo("  No repos found. Run: radar discover")
        return

    click.echo("\n  🛰️  Incremental Pipeline")
    click.echo(f"  {'─' * 40}")
    click.echo(f"  Total repos: {len(all_repos):,}")

    # Step 2: Determine what needs processing
    if full:
        click.echo("  Mode: FULL (ignoring change detection)")
        repos_to_process = all_repos[:limit] if limit else all_repos
        changed_names = [r["full_name"] for r in repos_to_process]
    else:
        # Compute signatures from DB data (stars, forks, etc.)
        # We use the DB's current values — these were updated by last discovery/snapshot
        click.echo("  Mode: INCREMENTAL (change detection)")
        repos_to_process = detector.find_changed(all_repos)

        if limit:
            repos_to_process = repos_to_process[:limit]

        changed_names = [r["full_name"] for r in repos_to_process]

        if not repos_to_process:
            click.echo("  ✅ All repos up to date — nothing to process")
            stats = detector.get_stats()
            click.echo(f"  Last run: {stats.get('last_run', 'never')}")
            return

    click.echo(f"  Repos to process: {len(repos_to_process):,}")
    click.echo()

    # Step 3: Snapshot changed repos
    click.echo("  📸 Snapshotting...")
    snap_engine = SnapshotEngine(db)

    async with GitHubClient() as client:
        if full:
            success = await snap_engine.snapshot_all(
                client, max_repos=limit, delay_between=0.5
            )
            click.echo(f"  Snapshot: {success}/{len(repos_to_process)} success")
        else:
            success, failed = await snap_engine.snapshot_incremental(
                client, repos_to_process, delay_between=0.5
            )
            click.echo(f"  Snapshot: {success} success, {failed} failed")

    # Step 4: Score
    click.echo("\n  📊 Scoring...")
    score_engine = ScoringEngine(db)

    if full:
        count = score_engine.compute_all_scores()
    else:
        count = score_engine.compute_incremental_scores(changed_names)

    click.echo(f"  Scored: {count} repos")

    # Step 4.5: Classify uncategorized repos (rules only, skips already-analyzed)
    click.echo("\n  🏷️  Classifying...")
    from radar.analysis.engine import AnalysisEngine

    classify_stats = AnalysisEngine(db).analyze_all(max_ai_repos=0)
    click.echo(f"  Classified: {classify_stats['classified']} new repos")

    # Step 4.6: Why Trending analysis
    click.echo("\n  Why Trending analysis...")
    from radar.analysis.why_trending import WhyTrendingAnalyzer
    wt_analyzer = WhyTrendingAnalyzer(db)
    wt_results = wt_analyzer.analyze_all_trending(limit=50)
    if wt_results:
        explanations = {r["repo_full_name"]: r["explanation"] for r in wt_results}
        db.save_why_trending_batch(explanations)
        click.echo(f"  Analyzed: {len(explanations)} repos")
    else:
        click.echo("  No trending repos to analyze yet")

    # Step 5: Mark as processed
    click.echo("\n  ✅ Updating signatures...")
    detector.mark_processed(repos_to_process)

    # Step 6: Show stats
    click.echo("\n  📈 Pipeline Stats")
    click.echo(f"  {'─' * 40}")
    stats = detector.get_stats()
    click.echo(f"  Total repos:     {stats['total_repos']:,}")
    click.echo(f"  Processed:       {stats['processed']:,}")
    click.echo(f"  Unprocessed:     {stats['unprocessed']:,}")
    click.echo(f"  Last run:        {stats.get('last_run', 'never')}")

    # Show top 5
    top = score_engine.get_rankings(5)
    if top:
        click.echo("\n  Top 5 by Radar Score:")
        for i, r in enumerate(top, 1):
            click.echo(
                f"  {i}. {r['repo_full_name'][:38]:<38} "
                f"Score: {r['radar_score']:>5.1f}  "
                f"Stars: {r.get('stars', 0):>7,}"
            )
    click.echo()


@main.command()
def process_stats() -> None:
    """Show incremental processing statistics."""
    from radar.processing.change_detector import ChangeDetector
    from radar.storage.database import Database

    db = Database()
    detector = ChangeDetector(db)
    stats = detector.get_stats()

    click.echo("\n  📊 Processing Stats")
    click.echo(f"  {'─' * 40}")
    click.echo(f"  Total repos:     {stats['total_repos']:,}")
    click.echo(f"  Processed:       {stats['processed']:,}")
    click.echo(f"  Unprocessed:     {stats['unprocessed']:,}")
    click.echo(f"  Last run:        {stats.get('last_run', 'never')}")
    click.echo()


@main.command()
@click.option("--week", "-w", help="Week label (e.g., 2026-W34)")
def report(week: str | None) -> None:
    """Generate weekly intelligence report."""
    from radar.reports.weekly import WeeklyReportGenerator
    from radar.storage.database import Database

    db = Database()
    gen = WeeklyReportGenerator(db)
    filepath = gen.generate(week_label=week)
    click.echo(f"  Report generated: {filepath}")


@main.command()
def feed() -> None:
    """Generate RSS feed of trending repositories."""
    from radar.reports.rss import RSSGenerator
    from radar.storage.database import Database

    db = Database()
    gen = RSSGenerator(db)
    filepath = gen.generate_trending_feed()
    click.echo(f"  RSS feed generated: {filepath}")


@main.command()
def api() -> None:
    """Generate public API files (JSON, CSV, RSS)."""
    from radar.api.endpoints import PublicAPI
    from radar.storage.database import Database

    db = Database()
    api = PublicAPI(db)

    click.echo("\n  📡 Generating Public API...")
    counts = api.generate_all()

    click.echo("\n  API Endpoints Generated:")
    click.echo(f"  {'─' * 40}")
    for endpoint, count in counts.items():
        click.echo(f"    /api/{endpoint}: {count} items")
    click.echo()


@main.command()
def badges() -> None:
    """Generate dynamic SVG badges for top repos."""
    from radar.api.badges import BadgeGenerator
    from radar.storage.database import Database

    db = Database()
    generator = BadgeGenerator(db)

    click.echo("\n  🏷️  Generating Developer Badges...")
    count = generator.generate_all_badges()

    click.echo(f"  Generated {count} badges for top 100 repos")
    click.echo("  Badges available at: /api/badges/{owner}__{repo}/score.svg")
    click.echo()


@main.command()
def export() -> None:
    """Export all data to JSON files for website."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/export.py"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        click.echo(result.stdout)
    else:
        click.echo(f"  Export failed: {result.stderr}")


@main.command()
def top() -> None:
    """Show top repositories by Radar Score."""
    from radar.scoring.engine import ScoringEngine
    from radar.storage.database import Database

    db = Database()
    engine = ScoringEngine(db)

    top = engine.get_rankings(25)
    if not top:
        click.echo("  No scores yet. Run: radar score")
        return

    click.echo("\n  Top 25 Repositories by Radar Score")
    click.echo(f"  {'─' * 75}")
    hdr = f"  {'#':>3}  {'Score':>6}  {'Stars':>8}  {'Impact':>6}"
    hdr += f"  {'Vel':>6}  {'Health':>6}  {'Repo':<35}"
    click.echo(hdr)
    click.echo(f"  {'─' * 75}")
    for i, r in enumerate(top, 1):
        click.echo(
            f"  {i:>3}  {r['radar_score']:>6.1f}  "
            f"{r.get('stars', 0):>8,}  "
            f"{r['impact']:>6.1f}  {r['velocity']:>6.1f}  "
            f"{r['health']:>6.1f}  {r['repo_full_name']:<35}"
        )
    click.echo()
@main.command()
def social_drafts(week: str | None = None) -> None:
    """Generate social media drafts (Twitter, LinkedIn, HN)."""
    from radar.reports.social import SocialDraftGenerator
    from radar.storage.database import Database

    db = Database()
    gen = SocialDraftGenerator(db)
    paths = gen.generate_all(week_label=week)
    click.echo(f"  Generated {len(paths)} social media drafts:")
    for platform, path in paths.items():
        click.echo(f"    {platform}: {path}")



# ── Scale-aware commands ──

@main.command()
def sync_cursor():
    """Sync all repos to the processing scheduler cursor table."""
    from radar.scale.scheduler import ProcessingScheduler
    scheduler = ProcessingScheduler()
    new = scheduler.sync_repos_to_cursor()
    stats = scheduler.get_stats()
    click.echo()
    click.echo('  Processing Scheduler')
    click.echo(f"  {chr(9472) * 40}")
    click.echo(f'  Total repos:      {stats["total_repos"]:,}')
    click.echo(f'  New synced:       {new:,}')
    click.echo(f'  Due now:          {stats["due_for_processing"]:,}')
    click.echo(f'  Failed:           {stats["failed"]:,}')
    click.echo(f'  Permanent fails:  {stats["permanent_failures"]:,}')
    click.echo()
    click.echo('  By tier:')
    for tier, count in sorted(stats.get('by_tier', {}).items()):
        click.echo(f'    Tier {tier}: {count:,} repos')
    click.echo()

@main.command()
@click.option('--batch-size', '-n', default=None, type=int, help='Max repos to process')
@click.option('--dry-run', is_flag=True, help='Show what would be processed')
def schedule(batch_size: int | None, dry_run: bool):
    """Show or run the processing schedule (tier-aware, rate-limited)."""
    from radar.scale.scheduler import ProcessingScheduler
    scheduler = ProcessingScheduler()

    if dry_run:
        batch = scheduler.get_next_batch(batch_size)
        click.echo()
        click.echo(f'  Next batch: {len(batch)} repos')
        for r in batch[:20]:
            click.echo(f"    T{r['tier']} {r['stars']:>7,}  {r['full_name']}")
        if len(batch) > 20:
            click.echo(f'    ... and {len(batch) - 20} more')
        click.echo()
        return

    batch = scheduler.get_next_batch(batch_size)
    if not batch:
        click.echo('  No repos due for processing')
        return

    click.echo(f'  Processing {len(batch)} repos...')
    scheduler.mark_processing(batch)
    stats = scheduler.get_stats()
    click.echo(f'  Marked {len(batch)} repos as processing')
    click.echo(f'  Remaining due: {stats["due_for_processing"]:,}')

@main.command()
def scheduler_stats():
    """Show detailed processing scheduler statistics."""
    from radar.scale.scheduler import ProcessingScheduler
    scheduler = ProcessingScheduler()
    stats = scheduler.get_stats()

    click.echo()
    click.echo('  Processing Scheduler Stats')
    click.echo(f'  {chr(9472) * 40}')
    click.echo(f'  Total repos:       {stats["total_repos"]:,}')
    click.echo(f'  Due for processing: {stats["due_for_processing"]:,}')
    click.echo(f'  Failed:            {stats["failed"]:,}')
    click.echo(f'  Permanent fails:   {stats["permanent_failures"]:,}')
    click.echo(f'  Last successful:   {stats.get("last_successful_run", "never")}')
    click.echo()
    click.echo('  By status:')
    for status, count in sorted(stats.get('by_status', {}).items()):
        click.echo(f'    {status:<20} {count:,}')
    click.echo()
    click.echo('  By tier:')
    for tier, count in sorted(stats.get('by_tier', {}).items()):
        click.echo(f'    Tier {tier}: {count:,} repos')
    click.echo()

@main.command()
def retention_stats():
    """Show snapshot retention and storage statistics."""
    from radar.scale.retention import SnapshotRetention
    retention = SnapshotRetention()
    storage = retention.get_storage_stats()

    click.echo()
    click.echo('  Snapshot Storage')
    click.echo(f'  {chr(9472) * 40}')
    click.echo(f'  Total snapshots:   {storage["total_snapshots"]:,}')
    click.echo(f'  Unique repos:      {storage["unique_repos"]:,}')
    click.echo(f'  Oldest:            {storage["oldest_snapshot"]}')
    click.echo(f'  Newest:            {storage["newest_snapshot"]}')
    click.echo(f'  DB size:           {storage["db_size_mb"]} MB')
    click.echo()

@main.command()
@click.option('--execute', is_flag=True, help='Actually delete old snapshots (default is dry-run)')
def retention_cleanup(execute: bool):
    """Clean up old snapshots based on retention policy (dry-run by default)."""
    from radar.scale.retention import SnapshotRetention
    retention = SnapshotRetention()

    candidates = retention.get_cleanup_candidates(dry_run=True)
    if not candidates:
        click.echo('  No old snapshots to clean up')
        return

    total = sum(c['count'] for c in candidates)
    click.echo(f'  Found {total:,} old snapshots across {len(candidates)} repos')
    if not execute:
        click.echo('  (Dry run — use --execute to actually delete)')
        result = retention.cleanup(dry_run=True)
        click.echo(f'  Would delete: {result["deleted"]:,} snapshots')
    else:
        result = retention.cleanup(dry_run=False)
        click.echo(f'  Deleted: {result["deleted"]:,} snapshots from '
                   f'{result["repos_affected"]} repos')

if __name__ == "__main__":
    main()
