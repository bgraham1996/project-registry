# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

`project-registry` is a **local, API-like service for keeping track of the user's dev projects**
across different filesystem paths and Obsidian vaults. The design intent (from `README.md`):

- A local **SQLite database** is the single source of truth. Rather than scanning project
  directories live on every request, project data is indexed into SQLite so there is one
  access/control point and queries can be predefined and changed later without rework.
- Two clients are planned against that DB: **one in Python and one in Go**, both querying the
  same local SQLite database.

**Maturity: working first vertical slice, both clients real, packaged as a uv tool.** The full
pipeline is in place — `project-registry scan` (installed console command; also `uv run main.py`)
scans the configured roots and indexes the projects found into SQLite; a read-only query API
(`project_registry/api/registry.py`) exposes shared SQL **views**; and three clients read those
views: a Python `rich` TUI (`project_registry/ux/tui.py`), a Python query CLI
(`project_registry/ux/cli.py`), and a Go CLI (`clients/go/`). The Python scan + query + TUI are now
unified behind one installable `project-registry` command (subcommands `scan`/`list`/`show`/`cycles`/`tui`). Remaining empty modules
(`project_registry/data_models/projects.py`, `session_manager.py`, `project_registry/main.py`) are intentional
future-direction stubs — **keep them**. Design decisions are recorded as Markdown under
`project/design/` (eight ADRs exist); keep adding there as decisions land.

## Environment and commands

Python 3.13 managed with [`uv`](https://docs.astral.sh/uv/) (pinned via `.python-version`).
`pyproject.toml` declares two runtime deps (**`rich`** for the TUI, **`click`** for the query CLI;
the DB layer itself uses the stdlib `sqlite3`) and **`pytest`** as a dev dep. Tests live in `tests/`
with `pythonpath=["."]`, so
`uv run pytest` works and is the real suite (unlike some sibling projects). The Go client is a
separate module under `clients/go/` (pure-Go `modernc.org/sqlite`, no cgo).

```bash
uv sync                       # create/refresh .venv and install deps
uv tool install .             # install `project-registry` on PATH (callable anywhere); --reinstall after changes
project-registry scan         # index projects (the only writer); --scan-root DIR repeatable, overrides config
project-registry list         # read-only query (list/show/cycles; --git/--cycle/--project; --json/--csv)
project-registry doctor       # read-only metadata-file health report (missing/empty/invalid/ok + absent fields)
project-registry tui          # read-only rich dashboard (--watch to live-refresh)
uv run main.py                # dev smoke test: same scan as `project-registry scan`, run from the checkout
uv run pytest                 # run the test suite (tests/)
uv add <pkg>                  # add a runtime dependency
cd clients/go && go build -o registry . && ./registry   # Go client (-git / -json / -db flags)
```

`pyproject.toml` declares a `[build-system]` (hatchling) and a single console script
(`project-registry = "project_registry.ux.cli:cli"`), so the project is a real installable
package. `uv tool install .` is the "callable from anywhere" path (uv's `pipx` equivalent: isolated
venv, executable on PATH); re-run with `--reinstall` to pick up code changes. The subcommands also
run in-repo via `uv run project-registry …` without installing.

## Package / import layout (important)

`project_registry/` is treated as **one local library**: it has `project_registry/__init__.py`, and every subpackage uses an
underscore name with its own `__init__.py` (`project_registry/cache`, `project_registry/config_service`, `project_registry/data_models`).
Imports are therefore **absolute from the `project_registry` root**, e.g.
`from project_registry.config_service.cnfg import Configure`. The project is now a real package —
`pyproject.toml` has a `[build-system]` (hatchling) that ships `project_registry`, so these imports
resolve both from an install and when run from the repo root (which also puts the root on
`sys.path`, letting the root `main.py` and `tests/` import `project_registry` directly). **Do not
reintroduce hyphenated directory names** — they are not importable as Python packages. (The
distribution name on PyPI-style metadata is still the hyphenated `project-registry`; only the
*import* package is underscored.)

## Layout and current state

- `main.py` (root) — dev smoke test / run-from-checkout scan entry point: a thin `argparse` shim
  (repeatable `--scan-root DIR`, `~` expanded, **overrides** configured `scan_roots` when given) that
  delegates to `project_registry.ux.scan.run_scan`. The real scan logic no longer lives here — it
  moved into the package so the installed `project-registry scan` command and `uv run main.py` share
  one implementation. Running either writes real rows to `~/.config/dev-reg/registry.db`. `parse_args`
  is still unit-tested in `tests/test_main.py` (which imports `resolve_roots` re-exported from `main`).
- `project_registry/` — core library.
  - `project_registry/config_service/cnfg.py` — `Configure`: `default()` seeds `{db_dir: ~/.config/dev-reg,
    db_name: registry.db, scan_roots: [~/dev], ignore: [archive]}`, `fig()` returns the dict,
    `db_path()`/`scan_roots()`/`ignore()` return the expanded values. `ignore` = candidate dir names
    the scanner skips (see scanner below).
  - `project_registry/cache/cache_manager.py` — `Db`: `init()` ensures the parent dir exists, connects via
    `sqlite3` (creating the file if absent), then runs **`create_tables()` → `_migrate()` →
    `_create_views()`** (order matters: views may reference a migrated-in column like `removed_at`),
    and returns whether it pre-existed; `close()` tears down. Uses `sqlite3.Row` row factory.
  - `project_registry/cache/schema.py` — DDL in three ordered phases: `TABLES` (idempotent
    `CREATE TABLE/INDEX IF NOT EXISTS` — the `watched_dirs` table, columns mirror `WatchlistItem`
    camelCase → snake_case, incl. `tags`/`notes`/`removed_at`); `MIGRATIONS` (additive `ALTER TABLE ...
    ADD COLUMN`, each tolerant of "duplicate column" so a fresh and an old DB converge); and `VIEWS`
    (the read contract — `v_projects` / `v_git_projects` / `v_cycle_counts`, each **`DROP VIEW` +
    `CREATE VIEW`** so a changed body actually rolls out to existing DBs, and each filtering
    `removed_at IS NULL` so clients see only live rows). `SCHEMA = TABLES + VIEWS` is a convenience for
    fresh-DB consumers (test fixtures). Known gap remaining: **table/column** changes are still
    additive-only (view-body changes now propagate). See `project/design/lifecycle-and-ignore.md`.
  - `project_registry/cache/watchlist_repo.py` — `WatchlistRepo(connection)`: persistence for the
    `watched_dirs` table. `insert(item)` (raises on duplicate `path`) and `upsert(item)`
    (idempotent on `path` — updates in place, keeps the existing row's `id`/`created_at`, bumps
    `updated_at`, **clears `removed_at`** so a reappearing dir reactivates, returns the stored id),
    plus queries `get(id)`, `get_by_path(path)`, `find_by_project(name)`, `all(include_removed=False)`
    (live-only by default). Soft-delete lives here too: `mark_removed_by_path(path)` (sets
    `removed_at` on a live row) and `active_paths()` (the scanner's reconcile input). There is **no**
    hard delete. SQL lives here, not in the model or `Db`.
  - `project_registry/data_models/watched_dirs.py` — `WatchlistItem` (a tracked project dir: `path`,
    `metadatapath`, `configpath`, `gitpath`, project/branch/cycle metadata, `tags`/`notes`, and
    `removedAt` — NULL while present/tracked). Owns the row mapping: `to_row()` (attrs -> columns,
    camelCase -> snake_case; emits `removed_at=None` for a fresh item so an upsert clears it) and
    `from_row(row)` (the inverse). `session_manager.py` and `projects.py` are still empty (intentional
    stubs).
  - `project_registry/scanner/scanner.py` — `Scanner(repo, roots, ignore=None)`: the indexer. Descends
    **only** the explicit `scan_roots` (never the whole filesystem), treats each root's immediate
    subdirs as candidate projects (skipping hidden dirs and any name in `ignore`, matched
    case-insensitively — e.g. `archive`), and `upsert`s a `WatchlistItem` for each present, tracked
    one. Detection is cheap and side-effect-free: `.git` marker + branch from `.git/HEAD` (no
    subprocess); **all descriptive fields incl. `tags`/`notes` come from `metadata.json`**, while
    `config.json` is reserved for project-specific config — only its `track` opt-out gate is read, its
    contents never populate item fields (its path is still recorded). For both files it finds the
    **highest-level** (shallowest) occurrence *anywhere beneath* the candidate via a bounded BFS
    (`Scanner.locate`: skips hidden + vendor/build dirs like `node_modules`, capped at
    `MAX_SCAN_DEPTH`; searched independently, may sit at different depths); `scan` runs `locate`
    **once** per candidate. Removal is a **soft-delete for history**: after upserting, a reconcile pass
    `mark_removed_by_path`s any previously-live row under a scanned root it didn't see this pass (dir
    gone/renamed/moved, now ignored, or `track:false`) — scoped to the scanned roots, never
    hard-deleted, hidden from the views. All parsing is defensive: a bad/empty/malformed file never
    raises. See `project/design/{metadata,config}-schema.md`, `file-discovery.md`, and
    `lifecycle-and-ignore.md` (the current source of truth for the metadata/config split + lifecycle).
    Also exposes a read-only **health check** for `doctor`: `diagnose(candidate)` → a `Diagnosis`
    namedtuple classifying the candidate's `metadata.json` as `missing` / `empty` / `invalid` (with the
    parse error, kept distinct from "missing" — which `read_json` collapses) / `ok` (listing absent
    `HEALTH_FIELDS` = `cycle`/`tags`), and `diagnose_all()` over all candidates. See
    `project/design/doctor-metadata-health.md`.
  - `project_registry/ux/scan.py` — the indexer as an importable routine: `resolve_roots(config,
    cli_roots)` (pure; CLI roots override config, `~` expanded) and `run_scan(cli_roots, echo)` (builds
    `Db`, resolves roots, runs `Scanner`, reports via the injected `echo`). This is the **one write
    path** and the shared implementation behind both `project-registry scan` and `uv run main.py`.
  - `project_registry/api/registry.py` — `Registry(connection)`: **read-only** query facade over the `v_*` views.
    Methods (`projects`, `git_projects`, `by_cycle`, `by_project`, `get_by_path`, `cycle_counts`)
    are thin typed wrappers returning `WatchlistItem`s / aggregates. Reads only — writes stay on
    `WatchlistRepo`, so a client holding a `Registry` cannot mutate the store. See
    `project/design/query-api.md`.
  - `project_registry/ux/tui.py` — read-only `rich` TUI client over `Registry`, rendered as a single-screen
    dashboard: a title `Rule`, a `cycle × count` summary bar (from `Registry.cycle_counts`), and a
    rounded table (Project / Type / Branch / Cycle / Tags / Path, with git-vs-dir glyphs and
    cycle colouring from the shared `CYCLE_STYLES` map). The render helpers (`render_summary`,
    `render_table`, `render_dashboard`) are all **pure** — data in, `rich` renderable out — so the
    whole view is tested without a DB or terminal; `--watch` live-refreshes. `project_registry/main.py` is still
    an empty stub.
  - `project_registry/ux/cli.py` — the **`project-registry` command** (`click` group; the single
    console-script entry point in `pyproject.toml`). One command groups every Python surface:
    `scan` (the write path — delegates to `scan.run_scan`), the read commands `list` / `show` /
    `cycles`, `doctor` (metadata-file health report), and `tui` (delegates to `tui.run`/`tui.watch`).
    The `list`/`show`/`cycles` read commands open the DB `mode=ro` (same read-only contract as the Go
    client) and talk only to `Registry`, so a query can never write; `doctor` reads the project files
    on disk (via `Scanner.diagnose_all`), not the DB. `list` takes `--git` / `--cycle` / `--project`
    (filters compose) plus output `--json` **or** `--csv` (mutually exclusive); `show <path>` /
    `cycles` / `doctor` take `--json` (`doctor` also takes `--scan-root`); global `--db`
    overrides the DB path for the DB-backed read commands. `--csv` emits RFC-4180 CSV to stdout with columns
    driven off the same `_item_dict` as `--json` so the two never drift; `tags` (a list) is flattened
    to a `;`-joined cell. The `format_*` / `render_detail` helpers are **pure**, and it reuses the
    TUI's `render_table` / `render_summary` so every client renders identically. Run installed as
    `project-registry …`, or in-repo via `uv run project-registry …`.
- `clients/go/` — the Go client: a **separate Go module** (`go.mod`, `main.go`, `README.md`),
  read-only over the **same** SQLite file and the **same** `v_*` views the Python side uses. Pure-Go
  `modernc.org/sqlite` (no cgo); opens the DB `mode=ro`; `-git` / `-json` / `-db` flags.
- `tests/` — real pytest suite (`test_scanner.py`, `test_api.py`, `test_tui.py`, `test_cli.py`),
  using temp dirs +
  in-memory DBs, never the real registry or the live tree.
- `libs/` — reserved for general reusable tooling (empty).
- `regProject/` — a sample/target "registered project" with populated `metadata.json` and
  `config.json` fixtures (the canonical examples the design docs reference) plus an empty `main.py`:
  the kind of thing the scanner indexes.

## Gotchas specific to this repo

- **The empty `cngf.py` (next to the real `cnfg.py`) and the `fig()` accessor name are canonical**,
  not slips — confirmed with the user; leave them. More broadly, the empty stub files/dirs
  (`project_registry/main.py`, `project_registry/data_models/{projects,session_manager}.py`, etc.) are intentional
  future-direction markers — do **not** delete them "cleaning up".
- **Design docs are ADRs (point-in-time); read them newest-first.** A later doc supersedes an earlier
  one and the older doc is deliberately **not** rewritten to match the code. The chain for the
  metadata/config split: `metadata-schema.md` ("config recorded by path only") → `config-schema.md`
  (config parses `tags`/`notes`/`track`) → **`lifecycle-and-ignore.md`** (current: `tags`/`notes` moved
  back to `metadata.json`; `config.json` is config-only, just the `track` gate). When in doubt, the
  newest ADR + the code win.
- **`.claude/settings.json` sets `worktree.bgIsolation: none`** so background sessions edit this
  checkout in place (the user iterates here directly) rather than in an isolated worktree.

## Git

Independent git repo (not part of any parent workspace). `main` is the intended default branch for
PRs; the active feature branch is `feat/metadata-parsing` (there is **no** `master`). Several
commits have landed locally building out the scanner, metadata/config parsing, the query API + views,
and the Go client; there is **no remote yet**.
