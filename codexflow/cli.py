from __future__ import annotations

from pathlib import Path
import time
from typing import Annotated

from rich.console import Console
from rich.table import Table
import typer

from .artifacts import ArtifactStore
from .config import load_config, write_default_config
from .db import RunStore
from .doctor import Doctor
from .locks import LockManager
from .pipeline import Pipeline, PipelineBlocked


app = typer.Typer(no_args_is_help=True, help="CodexFlow local Codex orchestration CLI.")
console = Console()


ConfigOption = Annotated[
    Path,
    typer.Option("--config", "-c", help="Path to .codexflow.yaml."),
]


@app.command()
def init(
    config: ConfigOption = Path(".codexflow.yaml"),
    target: Annotated[Path, typer.Option("--target", help="Target repository path.")] = Path("."),
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing config.")] = False,
) -> None:
    """Create config, storage directories, and the local run database."""

    if not target.exists():
        console.print(f"[red]Target path does not exist:[/red] {target}")
        raise typer.Exit(code=1)

    config_path = write_default_config(config, target_path=target, force=force)
    loaded = load_config(config_path)

    artifact_store = ArtifactStore(loaded.storage.runs_dir)
    artifact_store.ensure_base_dirs()
    loaded.storage.worktree_dir.mkdir(parents=True, exist_ok=True)
    loaded.storage.db_path.parent.mkdir(parents=True, exist_ok=True)
    RunStore(loaded.storage.db_path).initialize()
    (loaded.target.path / ".codexflow" / "locks").mkdir(parents=True, exist_ok=True)

    console.print(f"[green]Created[/green] {config_path}")
    console.print(f"[green]Initialized[/green] {loaded.target.path / '.codexflow'}")


@app.command()
def doctor(
    config: ConfigOption = Path(".codexflow.yaml"),
    target: Annotated[Path | None, typer.Option("--target", help="Override target repository path.")] = None,
) -> None:
    """Check whether the local environment can run CodexFlow."""

    loaded = load_config(config, target_override=target)
    checks = Doctor().run(loaded)

    table = Table(title="CodexFlow Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Details")
    for check in checks:
        status = "[green]ok[/green]" if check.ok else ("[red]fail[/red]" if check.required else "[yellow]warn[/yellow]")
        table.add_row(check.name, status, check.details)
    console.print(table)

    if Doctor.has_failures(checks):
        raise typer.Exit(code=1)


@app.command()
def status(
    config: ConfigOption = Path(".codexflow.yaml"),
    limit: Annotated[int, typer.Option("--limit", min=1, help="Maximum runs to show.")] = 20,
) -> None:
    """Show recent run records from the local database."""

    loaded = load_config(config)
    store = RunStore(loaded.storage.db_path)
    if not loaded.storage.db_path.exists():
        console.print("[yellow]No CodexFlow database found.[/yellow]")
        return

    runs = store.list_runs(limit=limit)
    if not runs:
        console.print("[yellow]No runs recorded.[/yellow]")
        return

    table = Table(title="CodexFlow Runs")
    table.add_column("Run ID")
    table.add_column("Issue")
    table.add_column("Status")
    table.add_column("Phase")
    table.add_column("Updated")
    for run in runs:
        issue = f"#{run['issue_number']}" if run["issue_number"] is not None else "-"
        table.add_row(
            run["id"],
            issue,
            run["status"],
            run["current_phase"] or "-",
            run["updated_at"],
        )
    console.print(table)


@app.command("show-run")
def show_run(
    run_id: str,
    config: ConfigOption = Path(".codexflow.yaml"),
) -> None:
    """Show one run record from the local database."""

    loaded = load_config(config)
    store = RunStore(loaded.storage.db_path)
    run = store.get_run(run_id) if loaded.storage.db_path.exists() else None
    if run is None:
        console.print(f"[red]Run not found:[/red] {run_id}")
        raise typer.Exit(code=1)
    for key, value in run.items():
        console.print(f"[bold]{key}[/bold]: {value}")


@app.command("run-issue")
def run_issue(
    issue_number: int,
    config: ConfigOption = Path(".codexflow.yaml"),
    target: Annotated[Path | None, typer.Option("--target", help="Override target repository path.")] = None,
) -> None:
    """Run one issue through the pipeline."""

    loaded = load_config(config, target_override=target)
    console.print(f"[bold]Issue #{issue_number}[/bold]: starting")
    try:
        result = Pipeline(config=loaded).run_issue(issue_number)
    except PipelineBlocked as exc:
        console.print(f"[yellow]Blocked:[/yellow] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]Failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Done[/green] {result.run_id}")
    if result.commit_sha:
        console.print(f"Commit: {result.commit_sha}")
    console.print(f"Run log: {result.run_dir}")


@app.command("run-next")
def run_next(
    config: ConfigOption = Path(".codexflow.yaml"),
    target: Annotated[Path | None, typer.Option("--target", help="Override target repository path.")] = None,
) -> None:
    """Claim and run the next ready issue."""

    loaded = load_config(config, target_override=target)
    try:
        result = Pipeline(config=loaded).run_next()
    except PipelineBlocked as exc:
        console.print(f"[yellow]Blocked:[/yellow] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]Failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if result is None:
        console.print("[yellow]No ready issue found.[/yellow]")
        return
    console.print(f"[green]Done[/green] {result.run_id}")
    if result.commit_sha:
        console.print(f"Commit: {result.commit_sha}")
    console.print(f"Run log: {result.run_dir}")


@app.command("run-all")
def run_all(
    limit: Annotated[int, typer.Option("--limit", min=1)] = 5,
    config: ConfigOption = Path(".codexflow.yaml"),
    target: Annotated[Path | None, typer.Option("--target", help="Override target repository path.")] = None,
) -> None:
    """Claim and run multiple ready issues."""

    loaded = load_config(config, target_override=target)
    try:
        results = Pipeline(config=loaded).run_all(limit=limit)
    except PipelineBlocked as exc:
        console.print(f"[yellow]Blocked:[/yellow] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]Failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if not results:
        console.print("[yellow]No ready issue found.[/yellow]")
        return
    for result in results:
        line = f"{result.run_id} {result.status}"
        if result.commit_sha:
            line += f" {result.commit_sha}"
        console.print(line)


@app.command()
def watch(
    interval: Annotated[int, typer.Option("--interval", min=1)] = 60,
    limit: Annotated[int | None, typer.Option("--limit", min=1, help="Stop after this many processed issues.")] = None,
    config: ConfigOption = Path(".codexflow.yaml"),
    target: Annotated[Path | None, typer.Option("--target", help="Override target repository path.")] = None,
) -> None:
    """Continuously poll GitHub issues and process ready work."""

    loaded = load_config(config, target_override=target)
    pipeline = Pipeline(config=loaded)
    processed = 0
    console.print(f"[bold]Watching[/bold] interval={interval}s")
    try:
        while True:
            try:
                result = pipeline.run_next()
            except PipelineBlocked as exc:
                processed += 1
                console.print(f"[yellow]Blocked:[/yellow] {exc}")
                if limit is not None and processed >= limit:
                    return
                _sleep(interval)
                continue
            except Exception as exc:
                processed += 1
                console.print(f"[red]Failed:[/red] {exc}")
                if limit is not None and processed >= limit:
                    return
                _sleep(interval)
                continue

            if result is None:
                console.print("[yellow]No ready issue found.[/yellow]")
                if limit is not None:
                    return
                _sleep(interval)
                continue

            processed += 1
            console.print(f"[green]Done[/green] {result.run_id}")
            if limit is not None and processed >= limit:
                return
    except KeyboardInterrupt:
        console.print("[yellow]Stopped.[/yellow]")


@app.command()
def unlock(
    config: ConfigOption = Path(".codexflow.yaml"),
    target: Annotated[Path | None, typer.Option("--target", help="Override target repository path.")] = None,
    stale: Annotated[bool, typer.Option("--stale", help="Remove stale lock files.")] = False,
) -> None:
    """Inspect or clear CodexFlow lock files."""

    loaded = load_config(config, target_override=target)
    manager = LockManager(loaded.target.path / ".codexflow" / "locks")
    if stale:
        removed = manager.clear_stale()
        console.print(f"Removed stale locks: {len(removed)}")
        for path in removed:
            console.print(str(path))
        return
    stale_locks = manager.stale_locks()
    if not stale_locks:
        console.print("No stale locks found.")
        return
    for path in stale_locks:
        console.print(str(path))


@app.command()
def resume(
    run_id: str,
    config: ConfigOption = Path(".codexflow.yaml"),
    target: Annotated[Path | None, typer.Option("--target", help="Override target repository path.")] = None,
) -> None:
    """Resume an interrupted run."""

    loaded = load_config(config, target_override=target)
    try:
        result = Pipeline(config=loaded).resume(run_id)
    except PipelineBlocked as exc:
        console.print(f"[yellow]Blocked:[/yellow] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]Failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Resumed[/green] {result.run_id} {result.status}")
    if result.commit_sha:
        console.print(f"Commit: {result.commit_sha}")
    console.print(f"Run log: {result.run_dir}")


def main() -> None:
    app()


def _sleep(seconds: int) -> None:
    time.sleep(seconds)
