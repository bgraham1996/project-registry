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

**Maturity: early scaffold, first slice working.** `uv run main.py` now creates-or-opens the
sqlite database (see below); most other modules are still empty stubs or skeletons. Treat most
work here as building to the intent above. When you add real structure, record design decisions as
Markdown under `project/design/` (the cross-project convention) — none exist yet.

## Environment and commands

Python 3.13 managed with [`uv`](https://docs.astral.sh/uv/) (pinned via `.python-version`).
`pyproject.toml` declares **no dependencies** (the DB layer uses the stdlib `sqlite3`) and **no
test/lint/format runner** — don't assume `uv run pytest` works until a runner is configured.

```bash
uv sync             # create/refresh .venv
uv run main.py      # create or connect to the sqlite registry, print which happened
uv add <pkg>        # add a runtime dependency
uv add --dev pytest # add a dev dependency (none configured yet)
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
  - `app/cache/schema.py` — central `SCHEMA` list of idempotent DDL (`CREATE ... IF NOT EXISTS`).
    Currently the `watched_dirs` table (columns mirror `WatchlistItem`, camelCase → snake_case)
    plus an index on `project_name`. Add new tables/indexes here; `init()` applies them on startup.
  - `app/cache/watchlist_repo.py` — `WatchlistRepo(connection)`: persistence for the
    `watched_dirs` table. `insert(item)` (raises on duplicate `path`) and `upsert(item)`
    (idempotent on `path` — updates in place, keeps the existing row's `id`/`created_at`, bumps
    `updated_at`, returns the stored id), plus queries `get(id)`, `get_by_path(path)`,
    `find_by_project(name)`, `all()` — each returns `WatchlistItem`(s) or `None`. SQL lives here,
    not in the model or `Db`.
  - `app/data_models/watched_dirs.py` — `WatchlistItem` (a tracked project dir: `path`,
    `metadatapath`, `configpath`, `gitpath`, plus project/branch/cycle metadata). Owns the
    row mapping: `to_row()` (attrs -> columns, camelCase -> snake_case) and
    `from_row(row)` (classmethod, the inverse). `session_manager.py` and `projects.py` are empty.
  - `app/api`, `app/scanner`, `app/ux`, `app/main.py` — empty placeholders.
- `libs/` — reserved for general reusable tooling (empty).
- `regProject/env/` — a sample/target "registered project" (`metadata.json`, `main.py`, both
  empty): the kind of thing the registry is meant to index.

## Gotchas specific to this repo

- **`app/config_service/` still has a leftover empty `cngf.py`** alongside the real `cnfg.py`, and
  the config accessor is named `fig()`. These look like transcription slips; confirm intent with
  the user before treating either as canonical.
- **`.claude/settings.json` sets `worktree.bgIsolation: none`** so background sessions edit this
  checkout in place (the user iterates here directly) rather than in an isolated worktree.

## Git

Independent git repo (not part of any parent workspace), currently **no commits yet** — everything
is untracked. `main` is the intended default branch for PRs even though the working branch is
`master`.
