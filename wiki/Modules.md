# Modules

File-by-file reference. Legend: **✅ working** · 🟡 skeleton · ⬜ empty stub.

## Root

| File | State | Notes |
|------|-------|-------|
| `main.py` | ✅ | Entry point. Builds `Db`, `init()`s, runs `Scanner(repo, config.scan_roots()).scan()` to index every project under the configured roots, prints all watched dirs, closes. Running it writes real rows to `~/.config/dev-reg/registry.db`. |
| `pyproject.toml` | ✅ | `project-registry` 0.1.0, `requires-python >=3.13`. Runtime dep: `rich`. Dev dep: `pytest`. `[tool.pytest.ini_options]` sets `pythonpath=["."]` and `testpaths=["tests"]`. |
| `.python-version` | ✅ | Pins Python 3.13 for `uv`. |

## `app/config_service/`

| File | State | Notes |
|------|-------|-------|
| `cnfg.py` | ✅ | `Configure`: `default()` seeds `{db_dir: ~/.config/dev-reg, db_name: registry.db, scan_roots: [~/dev]}` and returns `True`; `fig()` returns the config dict; `db_path()` returns the expanded absolute `Path`; `scan_roots()` returns the expanded root `Path`s the scanner may descend. |
| `cngf.py` | ⬜ | **Leftover empty file** — a transcription slip alongside the real `cnfg.py`. Safe to delete once confirmed. |

> Two naming quirks to be aware of: the file is `cnfg.py` (not `config.py`) and
> the accessor is `fig()` (not `config()`). Confirm with the user before treating
> either as canonical vs. renaming.

## `app/cache/`

| File | State | Notes |
|------|-------|-------|
| `cache_manager.py` | ✅ | `Db`: owns the `sqlite3` connection. `init()` mkdirs the parent, connects (create-or-open), sets `row_factory = sqlite3.Row`, applies schema via `create_tables()`, returns whether the file pre-existed. `path()`, `close()`. |
| `schema.py` | ✅ | Central `SCHEMA` list of idempotent DDL — currently `watched_dirs` + index on `project_name`. Add new tables/indexes here. |
| `watchlist_repo.py` | ✅ | `WatchlistRepo(connection)`: all SQL for `watched_dirs`. See below. |

### `WatchlistRepo` API

| Method | Behaviour |
|--------|-----------|
| `insert(item)` | Insert; returns `id`. **Raises on duplicate `path`.** |
| `upsert(item)` | Insert or update the row sharing this `path` (idempotent). On conflict refreshes every column except `id`/`path`, bumps `updated_at`, keeps the existing `id`/`created_at`. Returns the **stored** id (existing row's id on update, not the incoming item's). |
| `get(id)` | Fetch by id → `WatchlistItem` or `None`. |
| `get_by_path(path)` | Fetch by path → `WatchlistItem` or `None`. |
| `find_by_project(name)` | All rows with `project_name == name`, ordered by `path`. |
| `all()` | All rows, ordered by `path`. |

## `app/data_models/`

| File | State | Notes |
|------|-------|-------|
| `watched_dirs.py` | ✅ | `WatchlistItem` + `to_row()` / `from_row()`. See **[Data Model & Schema](Data-Model-and-Schema.md)**. |
| `projects.py` | ⬜ | Empty. Intended: a richer project model (vs. the raw watched-dir record). |
| `session_manager.py` | ⬜ | Empty. Intended: session/lifecycle management. |

## `app/scanner/`

| File | State | Notes |
|------|-------|-------|
| `scanner.py` | ✅ | `Scanner(repo, roots)`: the registry's only writer. `scan()` → for each root's immediate subdirs, `describe()` builds a `WatchlistItem` from on-disk signals and `upsert`s it (idempotent on `path`); returns the stored items. `candidates()` skips missing roots and hidden `.dotdirs`. `describe()` detects `.git` + `current_branch()` (read from `.git/HEAD`, no subprocess), records `config.json` by path, and **parses `metadata.json`** via `apply_metadata()` → `read_json()` into `projectName`/`projectVersion`/`branchVersion`/`cycle` (best-effort: bad/empty/malformed files leave fields `None`, never raise). `METADATA_FIELDS` maps JSON keys → attrs. Fenced to `scan_roots` — never the whole filesystem. See `project/design/metadata-schema.md`. |

## `app/ux/`

| File | State | Notes |
|------|-------|-------|
| `tui.py` | ✅ | Read-only `rich` view — a *client*: reads the DB via `WatchlistRepo`, never scans or writes. `render_table(items)` is pure (items in → `Table` out, testable without a DB or terminal). CLI: `uv run python -m app.ux.tui` renders once; `--watch [--interval N]` live-refreshes via `rich.live.Live` until Ctrl-C. Friendly empty-state when nothing has been scanned. |

## `tests/`

| File | State | Notes |
|------|-------|-------|
| `test_scanner.py` | ✅ | Pins scanner detection against a temp directory tree + in-memory DB — never the real filesystem or real registry. |
| `test_tui.py` | ✅ | Pins `render_table` output (pure, no DB/terminal needed). |

Run with `uv run pytest` (10 tests at last check).

## Empty placeholders

These exist as directories/files with no implementation yet:

| Path | Intended role |
|------|---------------|
| `app/main.py` | Empty — likely the eventual in-package entry point (root `main.py` is the live one today). |
| `app/api/` | The local API surface the clients call. |
| `libs/` | Reserved for general reusable tooling (not project-specific). |

## `regProject/`

A sample "registered project" — the kind of thing the registry is meant to
index, and the worked example for the metadata schema. `metadata.json` now
carries real fields (`name`/`version`/`branchVersion`/`cycle`) the scanner parses;
`config.json` carries an example registry config (recorded by path, not parsed);
`main.py` is an empty presence marker. Fixtures/targets, not runnable code.
