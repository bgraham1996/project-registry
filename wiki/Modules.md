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
| `cngf.py` | ⬜ | Empty placeholder beside the real `cnfg.py`. **Intentional** — the user has mapped the empty stubs as future-direction markers; leave it in place (do not delete). |

> Two naming quirks to be aware of: the file is `cnfg.py` (not `config.py`) and
> the accessor is `fig()` (not `config()`). Both are treated as canonical.

## `app/cache/`

| File | State | Notes |
|------|-------|-------|
| `cache_manager.py` | ✅ | `Db`: owns the `sqlite3` connection. `init()` mkdirs the parent, connects (create-or-open), sets `row_factory = sqlite3.Row`, applies schema via `create_tables()`, runs additive `_migrate()`, returns whether the file pre-existed. `path()`, `close()`. |
| `schema.py` | ✅ | Central `SCHEMA` list of idempotent DDL — `watched_dirs` + index, plus read views `v_projects` / `v_git_projects` / `v_cycle_counts`. Also `MIGRATIONS`: additive `ALTER … ADD COLUMN` for DBs predating a column. Add new tables/indexes/views here. |
| `watchlist_repo.py` | ✅ | `WatchlistRepo(connection)`: write/CRUD SQL for `watched_dirs`. See below. |

### `WatchlistRepo` API (writes)

| Method | Behaviour |
|--------|-----------|
| `insert(item)` | Insert; returns `id`. **Raises on duplicate `path`.** |
| `upsert(item)` | Insert or update the row sharing this `path` (idempotent). On conflict refreshes every column except `id`/`path`, bumps `updated_at`, keeps the existing `id`/`created_at`. Returns the **stored** id (existing row's id on update, not the incoming item's). |
| `delete_by_path(path)` | Delete the row at `path` if present; returns whether one was removed. Used by the scanner to prune projects that opt out of tracking. |
| `get(id)` | Fetch by id → `WatchlistItem` or `None`. |
| `get_by_path(path)` | Fetch by path → `WatchlistItem` or `None`. |
| `find_by_project(name)` | All rows with `project_name == name`, ordered by `path`. |
| `all()` | All rows, ordered by `path`. |

## `app/api/`

| File | State | Notes |
|------|-------|-------|
| `registry.py` | ✅ | `Registry(connection)`: **read-only** query API over the `v_*` views — the predefined queries clients call. No writes (those stay on `WatchlistRepo`). See below. |

### `Registry` API (reads)

| Method | Behaviour |
|--------|-----------|
| `projects()` | Every watched dir (via `v_projects`), canonical order → `list[WatchlistItem]`. |
| `git_projects()` | Git checkouts only (via `v_git_projects`). |
| `by_cycle(cycle)` | Watched dirs with matching lifecycle `cycle`. |
| `by_project(name)` | Watched dirs with matching `project_name`. |
| `get_by_path(path)` | Single watched dir at `path`, or `None`. |
| `cycle_counts()` | `{cycle: n}` rollup (via `v_cycle_counts`); `None` key = unset cycle. |

## `app/data_models/`

| File | State | Notes |
|------|-------|-------|
| `watched_dirs.py` | ✅ | `WatchlistItem` (now incl. `tags`/`notes`) + `to_row()` / `from_row()` (`tags` ⇄ JSON text). See **[Data Model & Schema](Data-Model-and-Schema.md)**. |
| `projects.py` | ⬜ | Empty **intentional** placeholder — a richer project model (vs. the raw watched-dir record). Keep in place. |
| `session_manager.py` | ⬜ | Empty **intentional** placeholder — session/lifecycle management. Keep in place. |

## `app/scanner/`

| File | State | Notes |
|------|-------|-------|
| `scanner.py` | ✅ | `Scanner(repo, roots)`: the registry's only writer. `scan()` → for each root's immediate subdir, if `is_tracked()` it `describe()`s a `WatchlistItem` and `upsert`s it (idempotent on `path`), else it prunes any existing row (`delete_by_path`); returns the stored items. `candidates()` skips missing roots and hidden `.dotdirs`. `describe()` detects `.git` + `current_branch()` (from `.git/HEAD`, no subprocess), **parses `metadata.json`** (`apply_metadata` → `projectName`/`projectVersion`/`branchVersion`/`cycle`) and **`config.json`** (`apply_config` → `tags`/`notes`). `is_tracked()` reads `config.json`'s `track` flag (opt-out; only `false` excludes). All parsing best-effort — bad/empty/malformed files leave fields `None` (and keep a dir tracked), never raise. Fenced to `scan_roots`. See `project/design/{metadata,config}-schema.md`. |

## `app/ux/`

| File | State | Notes |
|------|-------|-------|
| `tui.py` | ✅ | Read-only `rich` view — a *client*: reads the DB via the `Registry` query API (`projects()`), never scans or writes. `render_table(items)` is pure (items in → `Table` out, testable without a DB or terminal). CLI: `uv run python -m app.ux.tui` renders once; `--watch [--interval N]` live-refreshes via `rich.live.Live` until Ctrl-C. Friendly empty-state when nothing has been scanned. |

## `tests/`

| File | State | Notes |
|------|-------|-------|
| `test_scanner.py` | ✅ | Pins scanner detection (incl. `config.json` tags/notes + `track` skip/prune) against a temp directory tree + in-memory DB — never the real filesystem or real registry. |
| `test_tui.py` | ✅ | Pins `render_table` output (pure, no DB/terminal needed). |
| `test_api.py` | ✅ | Pins the `Registry` read API against an in-memory DB seeded through the real schema + repo, exercising the actual `v_*` view definitions. |

Run with `uv run pytest` (29 tests at last check).

## `clients/go/`

| File | State | Notes |
|------|-------|-------|
| `main.go` | ✅ | Read-only Go CLI over the same `v_*` views. Flags `-git` (uses `v_git_projects`), `-json`, `-db PATH`; default path mirrors `cnfg.py` (`~/.config/dev-reg/registry.db`); opens `mode=ro` and reports a missing DB rather than creating one; decodes the JSON `tags` column for display. |
| `go.mod` / `go.sum` | ✅ | Module `project-registry/goclient`; single dep `modernc.org/sqlite` (pure-Go driver, no cgo). |
| `README.md` | ✅ | Build/run instructions and the views-as-shared-contract rationale. |
| `.gitignore` | ✅ | Ignores the built `./registry` binary. |

## Empty placeholders (intentional)

These exist as directories/files with **no implementation yet, on purpose** — the
user has mapped them as future-direction markers. **Leave them in place.**

| Path | Intended role |
|------|---------------|
| `app/main.py` | The eventual in-package entry point (root `main.py` is the live one today). |
| `app/cache/template`, `app/ux/tui` (dir) | Empty dirs reserved for planned structure. |
| `libs/` | Reserved for general reusable tooling (not project-specific). |

## `regProject/`

A sample "registered project" — the kind of thing the registry is meant to
index, and the worked example for both schemas. `metadata.json` carries the
descriptive fields (`name`/`version`/`branchVersion`/`cycle`); `config.json`
carries registry config the scanner now parses — `track` (true here), `tags`,
`notes`; `main.py` is an empty presence marker. Fixtures/targets, not runnable
code.
