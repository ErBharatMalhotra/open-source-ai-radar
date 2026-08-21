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
        click.echo(f"  {'#':>3}  {'Score':>6}  {'Impact':>6}  {'Vel':>6}  {'Health':>6}  {'Repo':<40}")
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
    click.echo(f"  {'#':>3}  {'Score':>6}  {'Stars':>8}  {'Impact':>6}  {'Vel':>6}  {'Health':>6}  {'Repo':<35}")
    click.echo(f"  {'─' * 75}")
    for i, r in enumerate(top, 1):
        click.echo(
            f"  {i:>3}  {r['radar_score']:>6.1f}  "
            f"{r.get('stars', 0):>8,}  "
            f"{r['impact']:>6.1f}  {r['velocity']:>6.1f}  "
            f"{r['health']:>6.1f}  {r['repo_full_name']:<35}"
        )
    click.echo()


if __name__ == "__main__":
    main()
