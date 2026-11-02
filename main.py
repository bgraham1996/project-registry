"""Dev entry point / smoke test for the indexer.

The real scan implementation lives in :mod:`project_registry.ux.scan` (shared with
the installed ``project-registry scan`` command). This root module stays as the
run-from-checkout smoke test — ``uv run main.py [--scan-root DIR ...]`` — and keeps
its own tiny ``argparse`` seam so ``resolve_roots`` wiring is exercised here too.
"""

import argparse

from project_registry.ux.scan import resolve_roots, run_scan  # noqa: F401 (re-exported for tests)


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
    run_scan(args.scan_roots, echo=print)


if __name__ == "__main__":
    main()
