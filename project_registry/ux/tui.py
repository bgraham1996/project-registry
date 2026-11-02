"""Placeholder TUI: a read-only ``rich`` view of the registry.

This is a *client* in the README's sense — it only ever reads the SQLite DB
(through the read-only :class:`Registry` query API); it never scans or writes.
Populating the registry is the scanner's job (``uv run main.py``). Run the view
with:

    uv run python -m project_registry.ux.tui            # render once and exit
    uv run python -m project_registry.ux.tui --watch    # live-refresh from the DB until Ctrl-C

The presentation helpers (:func:`render_table`, :func:`render_summary`,
:func:`render_dashboard`) are kept pure — data in, ``rich`` renderable out — so
the whole view can be tested without a database or a terminal.
"""

import argparse
import time

from rich.console import Console, Group
from rich.live import Live
from rich.rule import Rule
from rich.table import Table
from rich import box

from project_registry.api.registry import Registry
from project_registry.cache.cache_manager import Db

# How each lifecycle cycle is coloured, in both the summary bar and the table's
# Cycle column, so a project's stage reads the same everywhere. ``None`` is the
# "cycle not set" bucket the rollup reports.
CYCLE_STYLES = {
    "active": "bold green",
    "paused": "yellow",
    "archived": "dim",
    None: "dim italic",
}


def _cycle_style(cycle) -> str:
    return CYCLE_STYLES.get(cycle, "cyan")


def _cycle_label(cycle) -> str:
    return cycle if cycle else "unset"


def render_summary(cycle_counts: dict) -> Table:
    """A compact one-line rollup of how many dirs sit in each cycle. Pure.

    Rendered as a borderless, single-row table of coloured ``cycle × n`` chips
    (a grid, so it lays out cleanly whatever the terminal width). Given an empty
    mapping it still returns a table — just an empty one.
    """
    grid = Table.grid(padding=(0, 2))
    chips = []
    for cycle, n in cycle_counts.items():
        style = _cycle_style(cycle)
        chips.append(f"[{style}]{_cycle_label(cycle)}[/] [bold]{n}[/]")
    if chips:
        for _ in chips:
            grid.add_column(no_wrap=True)
        grid.add_row(*chips)
    return grid


def render_table(items) -> Table:
    """Build a ``rich`` table from ``WatchlistItem``s. Pure: no I/O."""
    table = Table(
        box=box.ROUNDED,
        header_style="bold",
        expand=True,
        border_style="dim",
        row_styles=["", "on grey11"],
    )
    table.add_column("Project", style="bold", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Branch", style="cyan", no_wrap=True)
    table.add_column("Cycle", no_wrap=True)
    table.add_column("Tags", style="magenta")
    table.add_column("Path", style="dim", overflow="fold")

    for item in items:
        dir_type = item.dirType or "?"
        type_cell = (
            f"[green]● {dir_type}[/]" if dir_type == "git" else f"[dim]○ {dir_type}[/]"
        )
        cycle_cell = f"[{_cycle_style(item.cycle)}]{_cycle_label(item.cycle)}[/]"
        tags_cell = ", ".join(item.tags) if item.tags else "[dim]-[/]"
        table.add_row(
            item.projectName or "?",
            type_cell,
            item.branchName or "-",
            cycle_cell,
            tags_cell,
            item.path or "",
        )
    return table


def render_dashboard(items, cycle_counts: dict) -> Group:
    """The full single-screen view: title rule, cycle summary, and the table."""
    return Group(
        Rule(
            f"[bold]project-registry[/] · {len(items)} watched dir(s)",
            style="cyan",
        ),
        render_summary(cycle_counts),
        "",
        render_table(items),
    )


def _load():
    """Open the registry, read items + the cycle rollup, close. Returns both."""
    db = Db()
    db.init()
    try:
        registry = Registry(db.connection)
        return registry.projects(), registry.cycle_counts()
    finally:
        db.close()


def _renderable(items, cycle_counts=None):
    """The dashboard, or a friendly empty-state when nothing has been scanned yet."""
    if items:
        return render_dashboard(items, cycle_counts or {})
    return "[yellow]No watched dirs yet — run [bold]project-registry scan[/bold] to scan.[/]"


def run(console: Console | None = None) -> None:
    """Render the registry once."""
    console = console or Console()
    items, cycle_counts = _load()
    console.print(_renderable(items, cycle_counts))


def watch(interval: float = 2.0, console: Console | None = None) -> None:
    """Live-refresh the view from the DB every ``interval`` seconds until Ctrl-C."""
    console = console or Console()
    with Live(_renderable(*_load()), console=console, screen=True) as live:
        try:
            while True:
                time.sleep(interval)
                live.update(_renderable(*_load()))
        except KeyboardInterrupt:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only TUI view of the project registry.")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="live-refresh from the DB until Ctrl-C (default: render once and exit)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="seconds between refreshes in --watch mode (default: 2.0)",
    )
    args = parser.parse_args()
    if args.watch:
        watch(interval=args.interval)
    else:
        run()


if __name__ == "__main__":
    main()
