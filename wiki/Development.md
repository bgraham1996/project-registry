# Development

## Environment

Python 3.13 managed with [`uv`](https://docs.astral.sh/uv/) (pinned via
`.python-version`). Runtime dependency: **`rich`** (for the TUI); the DB layer
uses the stdlib `sqlite3`. Dev dependency: **`pytest`**.

```bash
uv sync                       # create/refresh .venv and install deps
uv run main.py                # scan the configured roots, print watched dirs
uv run python -m app.ux.tui   # read-only rich table view of the registry
uv run pytest                 # run the test suite
uv add <pkg>                  # add a runtime dependency
uv add --dev <pkg>            # add a dev dependency
```

### What `uv run main.py` does

Prints either `Created new` or `Connected to existing registry database at
<path>`, then **scans the configured `scan_roots`** (`~/dev` by default),
`upsert`ing a `WatchlistItem` for every immediate subdirectory of each root
(idempotent — re-running just refreshes the rows), and lists all watched dirs. It
writes **real rows** to:

```
~/.config/dev-reg/registry.db
```

The directory and file are created on first run. To reset, delete that file.

### Viewing the registry

`uv run python -m app.ux.tui` renders a read-only `rich` table of everything in
the DB and exits. Add `--watch` (optionally `--interval N`) for a live-refreshing
view until Ctrl-C. The TUI only reads — populate the DB with `main.py` first.

Inspect it directly with the `sqlite3` CLI (the read views are the client-facing
contract):

```bash
sqlite3 ~/.config/dev-reg/registry.db '.schema'
sqlite3 ~/.config/dev-reg/registry.db 'SELECT project_name, path FROM v_projects;'
sqlite3 ~/.config/dev-reg/registry.db 'SELECT * FROM v_cycle_counts;'
```

### Go client

The Go half of the two-client design — a read-only CLI over the same views:

```bash
cd clients/go
go build -o registry .
./registry            # all watched dirs (v_projects)
./registry -git       # git checkouts only (v_git_projects)
./registry -json      # JSON output
./registry -db PATH   # a specific database file
```

Pure-Go driver (`modernc.org/sqlite`) — no cgo/C toolchain needed. It opens the
DB read-only and reports a missing database rather than creating one. Details in
`clients/go/README.md`.

## Testing

`pytest` is configured (`[tool.pytest.ini_options]` in `pyproject.toml` sets
`pythonpath=["."]` so tests import the `app` package absolutely, and
`testpaths=["tests"]`). Run the suite with `uv run pytest`.

```
tests/test_scanner.py   # scanner detection (git/metadata/config/track) vs. temp dir + in-memory DB
tests/test_tui.py       # render_table output (pure, no DB/terminal)
tests/test_api.py       # Registry read API over the real v_* views (in-memory DB)
```

Both suites are **hermetic** — they never touch the real filesystem tree or the
real registry at `~/.config/dev-reg/`. The scanner test builds a throwaway
directory layout in a `tmp_path` and an in-memory SQLite DB; the TUI test feeds
`WatchlistItem`s straight into `render_table`. Keep new tests to that pattern
(temp dirs + in-memory DB) so a test run never mutates real project data.

## Conventions

- **`app/` is one importable library.** Use absolute imports from the `app`
  root: `from app.cache.cache_manager import Db`. Scripts run from the repo root
  put the repo root on `sys.path`, which is what makes this resolve.
- **No hyphenated package directories** — they aren't importable as Python
  packages. Use underscores + an `__init__.py` per subpackage.
- **Writes vs. reads are split.** SQL for writes stays in `watchlist_repo.py`
  (`WatchlistRepo`); predefined read queries live in `app/api/registry.py`
  (`Registry`) over the `v_*` views. The model owns row↔attr mapping; `Db` only
  owns the connection.
- **Schema is centralised and idempotent** in `app/cache/schema.py` — add DDL
  (tables, indexes, views) there, never inline in the repo; add new columns to
  `MIGRATIONS` as well.
- **Record design decisions** as Markdown under `project/design/` (cross-project
  convention): `metadata-schema.md`, `config-schema.md`, `query-api.md`.

## Gotchas

- **Empty stub files/dirs are intentional.** `app/config_service/cngf.py` (beside
  the real `cnfg.py`), `app/data_models/projects.py`, `session_manager.py`,
  `app/main.py`, and empty dirs (`app/cache/template`, `app/ux/tui`) are
  future-direction placeholders the user has mapped out. **Do not delete or "clean
  them up."** The config file is `cnfg.py` and its accessor is `fig()` — both
  canonical.
- `.claude/settings.json` sets `worktree.bgIsolation: none`, so background
  sessions edit this checkout **in place** rather than in an isolated worktree.
- The scanner parses **both** project files: `metadata.json`
  (`name`/`version`/`branchVersion`/`cycle`) and `config.json`
  (`track` opt-out, `tags`, `notes`). A `config.json` with `"track": false`
  makes the scanner **skip and prune** that dir. Schemas + rules:
  `project/design/metadata-schema.md`, `project/design/config-schema.md`.
- **Schema changes:** add tables/indexes/views to `SCHEMA`; add *new columns* to
  existing tables via `MIGRATIONS` too (a `CREATE TABLE IF NOT EXISTS` won't alter
  a table that already exists). No migration path yet for non-additive changes.
- `uv run main.py` writes real rows to `~/.config/dev-reg/registry.db`; the
  **tests** never do — they use temp dirs + in-memory DBs (see Testing above).

## Git

Independent git repo (not part of any parent workspace). Has local commits on
`master` (**no remote** configured); `main` is the intended default branch for
PRs. Recent milestones: scanner + `metadata.json` parsing, the read query API
(`Registry` + `v_*` views), `config.json` parsing (track/tags/notes) + additive
migrations, and the Go client.
