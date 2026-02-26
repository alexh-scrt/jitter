"""CLI entry point for Jitter."""

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
@click.version_option(package_name="jitter")
def cli():
    """Jitter - An AI agent that discovers trending ideas and ships code daily."""


@cli.command()
@click.option("--config", "config_path", default="config.yaml", help="Path to config file")
@click.option("--dry-run", is_flag=True, help="Run without pushing to GitHub")
def run(config_path: str, dry_run: bool):
    """Execute the daily pipeline."""
    from jitter.config import load_config
    from jitter.pipeline import Pipeline
    from jitter.utils.logging import setup_logging

    cfg = load_config(config_path)
    setup_logging(cfg.logging_level, cfg.logging_file)

    if dry_run:
        console.print("[yellow]Dry run mode - will not push to GitHub[/yellow]")

    pipeline = Pipeline(cfg, dry_run=dry_run)
    result = pipeline.run()

    if result.status.value == "completed":
        console.print(f"\n[bold green]Success![/bold green] {result.github_url or '(dry run)'}")
        if result.blueprint:
            console.print(f"  Project: {result.blueprint.project_name}")
        if result.selected_idea:
            console.print(f"  Idea: {result.selected_idea.title}")
    else:
        console.print(f"\n[bold red]Failed:[/bold red] {result.error}")


@cli.command()
@click.option("--config", "config_path", default="config.yaml", help="Path to config file")
@click.option("--limit", default=10, help="Number of recent runs to show")
def status(config_path: str, limit: int):
    """Show recent pipeline runs."""
    from jitter.config import load_config
    from jitter.store.history import HistoryStore

    cfg = load_config(config_path)
    store = HistoryStore(cfg.history_db_path)
    runs = store.get_recent_runs(limit)

    if not runs:
        console.print("[dim]No runs recorded yet. Run 'jitter run' to get started.[/dim]")
        return

    table = Table(title="Recent Jitter Runs")
    table.add_column("Run ID", style="cyan")
    table.add_column("Date", style="dim")
    table.add_column("Status")
    table.add_column("Project")
    table.add_column("GitHub URL", style="blue")

    for r in runs:
        status_style = {
            "completed": "[green]completed[/green]",
            "failed": "[red]failed[/red]",
            "running": "[yellow]running[/yellow]",
        }.get(r["status"], r["status"])

        table.add_row(
            r["run_id"],
            (r["started_at"] or "")[:16],
            status_style,
            r.get("project_name") or "-",
            r.get("github_url") or "-",
        )

    console.print(table)


@cli.command()
@click.option("--config", "config_path", default="config.yaml", help="Path to config file")
def history(config_path: str):
    """List all built projects."""
    from jitter.config import load_config
    from jitter.store.history import HistoryStore

    cfg = load_config(config_path)
    store = HistoryStore(cfg.history_db_path)
    projects = store.get_all_projects()

    if not projects:
        console.print("[dim]No projects built yet.[/dim]")
        return

    table = Table(title=f"Built Projects ({len(projects)} total)")
    table.add_column("Project", style="cyan")
    table.add_column("Idea", style="bold")
    table.add_column("Category")
    table.add_column("Date", style="dim")
    table.add_column("GitHub", style="blue")

    for p in projects:
        table.add_row(
            p["project_name"],
            p["idea_title"],
            p["idea_category"],
            (p["built_at"] or "")[:10],
            p.get("github_url") or "-",
        )

    console.print(table)
