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

**Maturity: working first vertical slice, both clients real.** The full pipeline is in place —
`uv run main.py` scans the configured roots and indexes the projects found into SQLite; a read-only
query API (`app/api/registry.py`) exposes shared SQL **views**; and two clients read those views: a
Python `rich` TUI (`app/ux/tui.py`) and a Go CLI (`clients/go/`). Remaining empty modules
(`app/data_models/projects.py`, `session_manager.py`, `app/main.py`) are intentional
future-direction stubs — **keep them**. Design decisions are recorded as Markdown under
`project/design/` (three ADRs exist); keep adding there as decisions land.

## Environment and commands

Python 3.13 managed with [`uv`](https://docs.astral.sh/uv/) (pinned via `.python-version`).
`pyproject.toml` declares one runtime dep (**`rich`**, for the TUI; the DB layer itself uses the
stdlib `sqlite3`) and **`pytest`** as a dev dep. Tests live in `tests/` with `pythonpath=["."]`, so
`uv run pytest` works and is the real suite (unlike some sibling projects). The Go client is a
separate module under `clients/go/` (pure-Go `modernc.org/sqlite`, no cgo).

```bash
uv sync                       # create/refresh .venv and install deps
uv run main.py                # scan configured roots, index projects, list watched dirs
uv run python -m app.ux.tui   # read-only rich TUI over the registry (--watch to live-refresh)
uv run pytest                 # run the test suite (tests/)
uv add <pkg>                  # add a runtime dependency
cd clients/go && go build -o registry . && ./registry   # Go client (-git / -json / -db flags)
```

## Package / import layout (important)

`app/` is treated as **one local library**: it has `app/__init__.py`, and every subpackage uses an
underscore name with its own `__init__.py` (`app/cache`, `app/config_service`, `app/data_models`).
Imports are therefore **absolute from the `app` root**, e.g.
`from app.config_service.cnfg import Configure`. This resolves because scripts run from the repo
root put the repo root on `sys.path`. If the project is later installed/packaged, declare `app` in
`pyproject.toml` rather than relying on the run-from-root behavior. **Do not reintroduce
hyphenated directory names** — they are not importable as Python packages.

## Layout and current state

- `main.py` (root) — working entry point / smoke test: builds `Db`, calls `init()` (create-or-open
  + schema), then via `WatchlistRepo` idempotently `upsert`s an entry for this repo and prints
  all watched dirs. Running it writes a real row to `~/.config/dev-reg/registry.db`.
- `app/` — core library.
  - `app/config_service/cnfg.py` — `Configure`: `default()` seeds `{db_dir: ~/.config/dev-reg,
    db_name: registry.db}`, `fig()` returns the dict, `db_path()` returns the expanded `Path`.
  - `app/cache/cache_manager.py` — `Db`: `init()` ensures the parent dir exists, connects via
    `sqlite3` (creating the file if absent), applies the schema idempotently via `create_tables()`,
    and returns whether it pre-existed; `close()` tears down. Uses `sqlite3.Row` row factory.
  - `app/cache/schema.py` — central `SCHEMA` list of idempotent DDL (`CREATE ... IF NOT EXISTS`):
    the `watched_dirs` table (columns mirror `WatchlistItem`, camelCase → snake_case, including
    `tags`/`notes`), an index on `project_name`, and the read **views** `v_projects` /
    `v_git_projects` (full column set, filter/order only) and `v_cycle_counts` (rollup). Also holds
    `MIGRATIONS` — additive `ALTER TABLE ... ADD COLUMN` statements applied by `Db._migrate()` after
    `create_tables()`, each tolerant of "duplicate column" so a fresh DB and an old DB converge.
    Add new tables/indexes/views here; `init()` applies them on startup. Changing a view *body* or an
    existing column has **no** migration path yet (additive columns only) — a known gap.
  - `app/cache/watchlist_repo.py` — `WatchlistRepo(connection)`: persistence for the
    `watched_dirs` table. `insert(item)` (raises on duplicate `path`) and `upsert(item)`
    (idempotent on `path` — updates in place, keeps the existing row's `id`/`created_at`, bumps
    `updated_at`, returns the stored id), plus queries `get(id)`, `get_by_path(path)`,
    `find_by_project(name)`, `all()` — each returns `WatchlistItem`(s) or `None`. SQL lives here,
    not in the model or `Db`.
  - `app/data_models/watched_dirs.py` — `WatchlistItem` (a tracked project dir: `path`,
    `metadatapath`, `configpath`, `gitpath`, plus project/branch/cycle metadata and `tags`/`notes`).
    Owns the row mapping: `to_row()` (attrs -> columns, camelCase -> snake_case) and
    `from_row(row)` (classmethod, the inverse). `session_manager.py` and `projects.py` are still
    empty (intentional stubs).
  - `app/scanner/scanner.py` — `Scanner(repo, roots)`: the indexer. Descends **only** the explicit
    `scan_roots` from config (never the whole filesystem), treats each root's immediate subdirs as
    candidate projects, and `upsert`s a `WatchlistItem` for each. Detection is cheap and
    side-effect-free: `.git` marker + current branch read straight from `.git/HEAD` (no subprocess),
    and parses `metadata.json` (→ descriptive fields) and `config.json` (→ `tags`/`notes`, and the
    `track` opt-out gate — an untracked dir is skipped and pruned). All parsing is defensive: a
    bad/empty/malformed file never raises. See `project/design/{metadata,config}-schema.md`.
  - `app/api/registry.py` — `Registry(connection)`: **read-only** query facade over the `v_*` views.
    Methods (`projects`, `git_projects`, `by_cycle`, `by_project`, `get_by_path`, `cycle_counts`)
    are thin typed wrappers returning `WatchlistItem`s / aggregates. Reads only — writes stay on
    `WatchlistRepo`, so a client holding a `Registry` cannot mutate the store. See
    `project/design/query-api.md`.
  - `app/ux/tui.py` — read-only `rich` TUI client over `Registry`. `render_table` is pure
    (items in, `Table` out) so it's testable without a DB; `--watch` live-refreshes. `app/main.py`
    is still an empty stub.
- `clients/go/` — the Go client: a **separate Go module** (`go.mod`, `main.go`, `README.md`),
  read-only over the **same** SQLite file and the **same** `v_*` views the Python side uses. Pure-Go
  `modernc.org/sqlite` (no cgo); opens the DB `mode=ro`; `-git` / `-json` / `-db` flags.
- `tests/` — real pytest suite (`test_scanner.py`, `test_api.py`, `test_tui.py`), using temp dirs +
  in-memory DBs, never the real registry or the live tree.
- `libs/` — reserved for general reusable tooling (empty).
- `regProject/` — a sample/target "registered project" with populated `metadata.json` and
  `config.json` fixtures (the canonical examples the design docs reference) plus an empty `main.py`:
  the kind of thing the scanner indexes.

## Gotchas specific to this repo

- **The empty `cngf.py` (next to the real `cnfg.py`) and the `fig()` accessor name are canonical**,
  not slips — confirmed with the user; leave them. More broadly, the empty stub files/dirs
  (`app/main.py`, `app/data_models/{projects,session_manager}.py`, etc.) are intentional
  future-direction markers — do **not** delete them "cleaning up".
- **Design docs are ADRs (point-in-time).** A later doc may supersede an earlier one — e.g.
  `metadata-schema.md` says `config.json` is "recorded by path only / not parsed", which
  `config-schema.md` then overrides once config parsing landed. That's expected; don't "fix" the
  older doc to match the code.
- **`.claude/settings.json` sets `worktree.bgIsolation: none`** so background sessions edit this
  checkout in place (the user iterates here directly) rather than in an isolated worktree.

## Git

Independent git repo (not part of any parent workspace). `main` is the intended default branch for
PRs; the active feature branch is `feat/metadata-parsing` (there is **no** `master`). Several
commits have landed locally building out the scanner, metadata/config parsing, the query API + views,
and the Go client; there is **no remote yet**.
