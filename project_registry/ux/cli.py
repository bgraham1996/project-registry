"""The ``project-registry`` command — one click app over the whole registry.

This is the single installed entry point (``project-registry``, declared in
``pyproject.toml`` and installable anywhere via ``uv tool install .``). It groups
the one *write* path and every *read* path as subcommands:

    project-registry scan [--scan-root DIR ...]   # index projects (the only writer)
    project-registry list                          # every watched dir, as a table
    project-registry list --git                    # only git checkouts
    project-registry list --cycle active           # filter by lifecycle cycle
    project-registry list --json                   # machine-readable output
    project-registry list --csv > out.csv          # spreadsheet-friendly export
    project-registry show ~/dev/rosmerta           # detail for one watched dir
    project-registry cycles                        # cycle × count rollup
    project-registry tui [--watch]                 # live rich dashboard

``scan`` is the only subcommand that mutates the store (it delegates to
:func:`project_registry.ux.scan.run_scan`). Every query subcommand opens the
SQLite file ``mode=ro`` (the same read-only contract the Go client uses) and talks
to the read-only :class:`Registry` query API, so a query can never write.

The presentation is kept pure: the ``format_*`` / ``render_detail`` helpers take
data and return a string or a ``rich`` renderable, so the whole surface is testable
without a terminal, and the table/summary/dashboard views are reused from
:mod:`project_registry.ux.tui` so every client renders identically.
"""

import csv
import io
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import click
from rich.console import Console

from project_registry.api.registry import Registry
from project_registry.config_service.cnfg import Configure
from project_registry.data_models.watched_dirs import WatchlistItem
from project_registry.ux.scan import run_scan
from project_registry.ux.tui import (
    _cycle_label,
    _cycle_style,
    render_summary,
    render_table,
    run as tui_run,
    watch as tui_watch,
)


# --- opening the store (read-only) ------------------------------------------

def _default_db_path() -> Path:
    """The registry path from config — same file the scanner and TUI use."""
    config = Configure()
    config.default()
    return config.db_path()


@contextmanager
def open_registry(db_path=None):
    """Yield a :class:`Registry` over a read-only connection, then close it.

    Opens the SQLite file ``mode=ro`` so this client physically cannot write to
    it. A missing file means nothing has been scanned yet, which we turn into a
    friendly ``ClickException`` rather than a raw sqlite error.
    """
    path = Path(db_path).expanduser() if db_path else _default_db_path()
    if not path.exists():
        raise click.ClickException(
            f"No registry database at {path} — run `project-registry scan` to scan first."
        )
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        yield Registry(connection)
    finally:
        connection.close()


# --- pure formatting --------------------------------------------------------

def _item_dict(item) -> dict:
    """A JSON-friendly view of a ``WatchlistItem`` (tags stay a list; id a str)."""
    return {
        "id": str(item.id),
        "path": item.path,
        "projectName": item.projectName,
        "projectVersion": item.projectVersion,
        "branchName": item.branchName,
        "branchVersion": item.branchVersion,
        "cycle": item.cycle,
        "dirType": item.dirType,
        "tags": item.tags,
        "notes": item.notes,
        "metadataPath": item.metadatapath,
        "configPath": item.configpath,
        "gitPath": item.gitpath,
    }


def format_items_json(items) -> str:
    """A list of watched dirs as a pretty JSON array. Pure."""
    return json.dumps([_item_dict(i) for i in items], indent=2)


def format_item_json(item) -> str:
    """A single watched dir as a pretty JSON object. Pure."""
    return json.dumps(_item_dict(item), indent=2)


def format_items_csv(items) -> str:
    """A list of watched dirs as CSV text. Pure.

    Columns are the keys of :func:`_item_dict`, so CSV and ``--json`` expose the
    same fields in the same order and can never drift. ``tags`` (a list) is
    flattened to a ``;``-joined string for spreadsheet-friendliness; every other
    ``None`` becomes an empty cell. The stdlib ``csv`` writer quotes cells that
    contain commas/newlines (e.g. ``notes``), so the output round-trips cleanly.
    A header row is always emitted, even for an empty list.
    """
    fieldnames = list(_item_dict(WatchlistItem()).keys())
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        row = _item_dict(item)
        row["tags"] = ";".join(row["tags"]) if row["tags"] else ""
        writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    # csv writes \r\n line terminators; StringIO keeps them. Return as-is so the
    # output is RFC-4180-clean; click.echo won't add an extra trailing newline.
    return buffer.getvalue()


def format_cycle_counts_json(counts: dict) -> str:
    """The cycle rollup as JSON, with the ``None`` bucket labelled ``unset``. Pure."""
    return json.dumps(
        {(_cycle_label(cycle)): n for cycle, n in counts.items()}, indent=2
    )


def render_detail(item):
    """A key/value detail view of one watched dir. Pure: data in, renderable out."""
    from rich.table import Table

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold", justify="right", no_wrap=True)
    grid.add_column(overflow="fold")

    def row(label, value):
        grid.add_row(label, value if value not in (None, "") else "[dim]-[/]")

    row("Project", item.projectName)
    row("Type", item.dirType)
    row("Branch", item.branchName)
    row("Cycle", f"[{_cycle_style(item.cycle)}]{_cycle_label(item.cycle)}[/]")
    row("Tags", ", ".join(item.tags) if item.tags else None)
    row("Notes", item.notes)
    row("Path", item.path)
    row("Metadata", item.metadatapath)
    row("Config", item.configpath)
    row("Git", item.gitpath)
    return grid


# --- commands ---------------------------------------------------------------

@click.group(help="Scan and query your local dev-project registry (scan writes; all other commands are read-only).")
@click.option(
    "--db",
    "db_path",
    default=None,
    help="path to the registry SQLite database (default: the configured path).",
)
@click.pass_context
def cli(ctx, db_path):
    ctx.obj = {"db_path": db_path}


@cli.command(help="Scan the configured roots and index the projects found (the only writer).")
@click.option(
    "--scan-root",
    "scan_roots",
    multiple=True,
    metavar="DIR",
    help=(
        "Directory whose immediate subdirectories are candidate projects. "
        "Repeatable. Overrides the configured scan roots when given. ~ is expanded."
    ),
)
def scan(scan_roots):
    # multiple=() when unset -> None so run_scan falls back to the configured roots.
    run_scan(list(scan_roots) or None, echo=click.echo)


@cli.command(name="list", help="List watched dirs (optionally filtered).")
@click.option("--git", "-g", is_flag=True, help="only git checkouts.")
@click.option("--cycle", "-c", default=None, help="filter by lifecycle cycle (e.g. active).")
@click.option("--project", "-p", default=None, help="filter by project name.")
@click.option("--json", "-j", "as_json", is_flag=True, help="emit JSON instead of a table.")
@click.option("--csv", "as_csv", is_flag=True, help="emit CSV instead of a table (to stdout).")
@click.pass_context
def list_cmd(ctx, git, cycle, project, as_json, as_csv):
    if as_json and as_csv:
        raise click.UsageError("--json and --csv are mutually exclusive.")

    with open_registry(ctx.obj["db_path"]) as registry:
        items = registry.git_projects() if git else registry.projects()
    # --cycle / --project narrow the (possibly git-only) set in memory, so the
    # filters compose rather than each being a separate exclusive query.
    if cycle is not None:
        items = [i for i in items if i.cycle == cycle]
    if project is not None:
        items = [i for i in items if i.projectName == project]

    if as_json:
        click.echo(format_items_json(items))
    elif as_csv:
        # nl=False: the CSV text already ends in its own line terminator, so
        # click shouldn't append an extra blank line.
        click.echo(format_items_csv(items), nl=False)
    elif items:
        Console().print(render_table(items))
    else:
        Console().print("[yellow]No matching watched dirs.[/]")


@cli.command(help="Show detail for the watched dir at PATH.")
@click.argument("path")
@click.option("--json", "-j", "as_json", is_flag=True, help="emit JSON instead of a detail view.")
@click.pass_context
def show(ctx, path, as_json):
    target = str(Path(path).expanduser())
    with open_registry(ctx.obj["db_path"]) as registry:
        item = registry.get_by_path(target)
    if item is None:
        raise click.ClickException(f"No watched dir at {target}.")

    if as_json:
        click.echo(format_item_json(item))
    else:
        Console().print(render_detail(item))


@cli.command(help="Show how many watched dirs sit in each lifecycle cycle.")
@click.option("--json", "-j", "as_json", is_flag=True, help="emit JSON instead of a summary bar.")
@click.pass_context
def cycles(ctx, as_json):
    with open_registry(ctx.obj["db_path"]) as registry:
        counts = registry.cycle_counts()
    if as_json:
        click.echo(format_cycle_counts_json(counts))
    else:
        Console().print(render_summary(counts))


@cli.command(help="Live rich dashboard view of the registry.")
@click.option("--watch", "-w", is_flag=True, help="live-refresh until Ctrl-C (default: render once).")
@click.option("--interval", default=2.0, type=float, help="seconds between refreshes in --watch mode.")
def tui(watch, interval):
    if watch:
        tui_watch(interval=interval)
    else:
        tui_run()


if __name__ == "__main__":
    cli()
