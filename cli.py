import asyncio
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from app.core.models import ScanRequest, RepoSource, BugTrackerType
from app.core.pipeline import run_scan

app = typer.Typer(name="reporat", help="RepoRat -- AI-powered repo scanner.")
console = Console()


@app.command()
def scan(
    repo_url: str = typer.Argument(..., help="Repository URL to scan"),
    branch: str = typer.Option("main", "--branch", "-b"),
    source: str = typer.Option("github", "--source", "-s"),
    tracker: str = typer.Option("github_issues", "--tracker", "-t"),
    no_static: bool = typer.Option(False, "--no-static"),
    no_ai: bool = typer.Option(False, "--no-ai"),
    no_file: bool = typer.Option(False, "--no-file", help="Dry run"),
):
    console.print(Panel.fit(
        f"[bold cyan]RepoRat[/bold cyan] [dim]v0.1.0[/dim]\n"
        f"[dim]Repo:[/dim] {repo_url}\n[dim]Branch:[/dim] {branch}\n[dim]Tracker:[/dim] {tracker}",
        title="[bold]Scan Config[/bold]", border_style="cyan",
    ))
    request = ScanRequest(
        repo_url=repo_url, branch=branch, repo_source=RepoSource(source),
        bug_tracker=BugTrackerType(tracker), run_static_analysis=not no_static,
        run_ai_tests=not no_ai, file_bugs=not no_file,
    )
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Running scan...", total=None)
        result = asyncio.run(run_scan(request))
        progress.update(task, description="[green]Scan complete!")

    summary = result.summary
    if result.issues:
        table = Table(title="Issues Found", show_lines=True)
        table.add_column("Severity", width=10)
        table.add_column("Source", width=15)
        table.add_column("File", width=30)
        table.add_column("Title", width=50)
        colors = {"critical": "red", "high": "yellow", "medium": "cyan", "low": "dim", "info": "dim"}
        for issue in result.issues:
            c = colors.get(issue.severity.value, "white")
            table.add_row(f"[{c}]{issue.severity.value}[/{c}]", issue.source, issue.file_path[:30], issue.title[:50])
        console.print(table)
    else:
        console.print("[green]No issues found!")

    console.print(Panel(
        f"[bold]Issues:[/bold] {summary['total_issues']}  [bold]Tests:[/bold] {summary['tests_generated']}  "
        f"[green]Passed:[/green] {summary['tests_passed']}  [red]Failed:[/red] {summary['tests_failed']}  "
        f"[bold]Bugs Filed:[/bold] {summary['bugs_filed']}",
        title="Summary", border_style="green" if result.status.value == "completed" else "red",
    ))


@app.command()
def test_connector(tracker: str = typer.Argument(...)):
    from app.services.bug_reporter import get_tracker as gt
    connector = gt(BugTrackerType(tracker))
    with console.status(f"Testing {tracker}..."):
        connected = asyncio.run(connector.test_connection())
    if connected:
        console.print(f"[green]Connected to {tracker}!")
    else:
        console.print(f"[red]Failed to connect to {tracker}. Check .env credentials.")


if __name__ == "__main__":
    app()
