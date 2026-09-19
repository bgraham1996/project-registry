import argparse
from pathlib import Path

from app.cache.cache_manager import Db
from app.cache.watchlist_repo import WatchlistRepo
from app.scanner.scanner import Scanner


def resolve_roots(config, cli_roots) -> list[Path]:
    """The roots to scan: explicit ``--scan-root`` values if any, else config.

    ``cli_roots`` is the (possibly empty) list of ``--scan-root`` strings from the
    command line. When one or more is given it *overrides* the configured
    ``scan_roots`` entirely (it does not append); otherwise the configured roots
    are used. Either way ``~`` is expanded so the two sources are interchangeable.
    """
    if cli_roots:
        return [Path(root).expanduser() for root in cli_roots]
    return config.scan_roots()


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan configured roots and index the projects found into the registry.",
    )
    parser.add_argument(
        "--scan-root",
        dest="scan_roots",
        action="append",
        metavar="DIR",
        help=(
            "Directory whose immediate subdirectories are candidate projects. "
            "Repeatable. Overrides the configured scan roots when given. "
            "~ is expanded."
        ),
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    db = Db()
    existed = db.init()
    verb = "Connected to existing" if existed else "Created new"
    print(f"{verb} registry database at {db.path()}")

    repo = WatchlistRepo(db.connection)

    roots = resolve_roots(db.config, args.scan_roots)
    print(f"Scanning {len(roots)} root(s): {', '.join(str(r) for r in roots)}")
    Scanner(repo, roots).scan()  # idempotent upserts; re-running just refreshes rows

    items = repo.all()
    print(f"{len(items)} watched dir(s):")
    for item in items:
        branch = f" @{item.branchName}" if item.branchName else ""
        print(f"  - {item.projectName or '?'} [{item.dirType or '?'}]{branch}  {item.path}")

    db.close()


if __name__ == "__main__":
    main()
