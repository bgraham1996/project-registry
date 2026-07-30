"""Placeholder TUI: a read-only ``rich`` view of the registry.

This is a *client* in the README's sense — it only ever reads the SQLite DB
(through :class:`WatchlistRepo`); it never scans or writes. Populating the
registry is the scanner's job (``uv run main.py``). Run the view with:

    uv run python -m app.ux.tui            # render once and exit
    uv run python -m app.ux.tui --watch    # live-refresh from the DB until Ctrl-C

``render_table`` is kept pure (items in, ``Table`` out) so the presentation can
be tested without a database or a terminal.
"""

import argparse
import time

from rich.console import Console
from rich.live import Live
from rich.table import Table

from app.cache.cache_manager import Db
from app.cache.watchlist_repo import WatchlistRepo


def render_table(items) -> Table:
    """Build a ``rich`` table from ``WatchlistItem``s. Pure: no I/O."""
    table = Table(
        title=f"project-registry — {len(items)} watched dir(s)",
        title_style="bold",
        header_style="bold",
        expand=True,
    )
    table.add_column("Project", style="bold", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Branch", style="cyan", no_wrap=True)
    table.add_column("Path", style="dim", overflow="fold")

    for item in items:
        dir_type = item.dirType or "?"
        type_cell = f"[green]{dir_type}[/]" if dir_type == "git" else f"[dim]{dir_type}[/]"
        table.add_row(
            item.projectName or "?",
            type_cell,
            item.branchName or "-",
            item.path or "",
        )
    return table


def _load_items():
    """Open the registry, read every watched dir, close. Returns the items."""
    db = Db()
    db.init()
    try:
        return WatchlistRepo(db.connection).all()
    finally:
        db.close()


def _renderable(items):
    """The table, or a friendly empty-state when nothing has been scanned yet."""
    if items:
        return render_table(items)
    return "[yellow]No watched dirs yet — run [bold]uv run main.py[/bold] to scan.[/]"


def run(console: Console | None = None) -> None:
    """Render the registry once."""
    console = console or Console()
    console.print(_renderable(_load_items()))


def watch(interval: float = 2.0, console: Console | None = None) -> None:
    """Live-refresh the table from the DB every ``interval`` seconds until Ctrl-C."""
    console = console or Console()
    with Live(_renderable(_load_items()), console=console, screen=True) as live:
        try:
            while True:
                time.sleep(interval)
                live.update(_renderable(_load_items()))
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
