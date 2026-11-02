"""The indexer, as an importable routine.

Scanning is the one *write* path in the registry: it walks the configured (or
``--scan-root``-overridden) roots and upserts a row per project found. This lives
inside the package — rather than only in the repo-root ``main.py`` smoke test — so
the installed ``project-registry scan`` console command and the ``uv run main.py``
dev entry point can share one implementation. Everything read-only stays on the
:class:`~project_registry.api.registry.Registry` query API.
"""

from pathlib import Path

from project_registry.cache.cache_manager import Db
from project_registry.cache.watchlist_repo import WatchlistRepo
from project_registry.scanner.scanner import Scanner


def resolve_roots(config, cli_roots) -> list[Path]:
    """The roots to scan: explicit ``--scan-root`` values if any, else config.

    ``cli_roots`` is the (possibly empty/None) list of ``--scan-root`` strings from
    the command line. When one or more is given it *overrides* the configured
    ``scan_roots`` entirely (it does not append); otherwise the configured roots
    are used. Either way ``~`` is expanded so the two sources are interchangeable.
    """
    if cli_roots:
        return [Path(root).expanduser() for root in cli_roots]
    return config.scan_roots()


def run_scan(cli_roots=None, echo=print):
    """Scan the resolved roots, upsert a row per project, and report.

    ``echo`` is the line sink (``print`` for the dev entry point, ``click.echo``
    for the console command) so the routine is UI-agnostic. Returns the stored
    :class:`WatchlistItem`\\ s. Upserts are idempotent, so re-running just refreshes
    the existing rows.
    """
    db = Db()
    existed = db.init()
    verb = "Connected to existing" if existed else "Created new"
    echo(f"{verb} registry database at {db.path()}")

    repo = WatchlistRepo(db.connection)

    roots = resolve_roots(db.config, cli_roots)
    echo(f"Scanning {len(roots)} root(s): {', '.join(str(r) for r in roots)}")
    Scanner(repo, roots).scan()

    items = repo.all()
    echo(f"{len(items)} watched dir(s):")
    for item in items:
        branch = f" @{item.branchName}" if item.branchName else ""
        echo(f"  - {item.projectName or '?'} [{item.dirType or '?'}]{branch}  {item.path}")

    db.close()
    return items
