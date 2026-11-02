# ADR: Packaging as a uv tool + a unified `project-registry` command

Status: accepted (2026-11-02)

## Context

The registry needed to be **callable from anywhere** and **usable by other projects**, not just
run from a clone with `uv run main.py` / `uv run python -m app.ux.{cli,tui}`. Until now:

- `pyproject.toml` had no `[build-system]` and no entry points, so the project was a "virtual" uv
  project — not installable, not importable outside a run-from-root `sys.path` trick.
- The package was `app/` — a collision-prone top-level import name for anything that depends on it.
- The three Python surfaces were separate invocations: a root `argparse` scanner (`main.py`), a
  `click` query CLI (`app.ux.cli`), and an `argparse` TUI (`app.ux.tui`).

## Decision

1. **Distribute as a uv tool.** Add a `[build-system]` (hatchling) and a single console script
   `project-registry = "project_registry.ux.cli:cli"`. `uv tool install .` (uv's `pipx` equivalent —
   isolated venv, executable on PATH) makes it callable from any directory.
2. **Rename the import package `app` → `project_registry`.** The distribution name stays the
   hyphenated `project-registry`; only the importable package is underscored. This gives a sane
   namespace and removes the run-from-root dependency.
3. **One command, subcommands.** Unify the three surfaces behind the existing `click` group:
   `scan` (the only writer) · `list` / `show` / `cycles` (read-only) · `tui`. The scan logic moved
   out of the root `main.py` into `project_registry/ux/scan.py` (`resolve_roots`, `run_scan`) so the
   installed command and the `uv run main.py` dev smoke test share one implementation.

## Scope (explicitly chosen)

- **"Callable anywhere" = the CLI.** Other projects are expected to consume the registry by
  **shelling out** to `project-registry … --json` / `--csv` (language-agnostic — the Go client
  already treats the DB/views as an external interface). We did **not** commit to a curated,
  importable public Python API (`from project_registry import Registry`) as a supported surface; the
  modules are importable but their API is not frozen. Revisit if an in-process Python consumer
  appears — that would promote `Registry` / `WatchlistItem` to a documented public API.

## Consequences

- `main.py` stays as the run-from-checkout smoke test but is now a thin shim over `run_scan`.
- `pyproject.toml` becomes a real package; `uv run`/`uv sync` now build-install the project itself.
  Re-run `uv tool install . --reinstall` (or `uv tool upgrade project-registry`) to pick up changes —
  the tool install is a snapshot, not editable.
- The read-only contract is unchanged: `scan` is the sole write path; every query command opens the
  SQLite file `mode=ro` and talks only to the read-only `Registry` facade.
- Known gap unchanged: schema migrations remain additive-only (no path for changing a view body or
  an existing column).

## Alternatives considered

- **Keep `app`, just declare it** — minimal churn, but `import app` is a poor namespace for any
  dependent and keeps the run-from-root smell. Rejected in favour of the rename.
- **Separate console scripts per client** (`project-registry`, `project-registry-scan`,
  `project-registry-tui`) — three names on PATH, no group to merge the scanner into. Rejected: one
  discoverable command with subcommands is simpler to remember and document.
