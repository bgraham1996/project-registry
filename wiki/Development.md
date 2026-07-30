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

Inspect it directly with the `sqlite3` CLI:

```bash
sqlite3 ~/.config/dev-reg/registry.db '.schema'
sqlite3 ~/.config/dev-reg/registry.db 'SELECT project_name, path FROM watched_dirs;'
```

## Testing

`pytest` is configured (`[tool.pytest.ini_options]` in `pyproject.toml` sets
`pythonpath=["."]` so tests import the `app` package absolutely, and
`testpaths=["tests"]`). Run the suite with `uv run pytest`.

```
tests/test_scanner.py   # scanner detection vs. a temp dir tree + in-memory DB
tests/test_tui.py       # render_table output (pure, no DB/terminal)
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
- **SQL stays in the repository layer** (`watchlist_repo.py`); the model owns
  row↔attr mapping; `Db` only owns the connection.
- **Schema is centralised and idempotent** in `app/cache/schema.py` — add DDL
  there, never inline in the repo.
- **Record design decisions** as Markdown under `project/design/` (cross-project
  convention). First one landed: `project/design/metadata-schema.md`.

## Gotchas

- `app/config_service/` has a leftover empty `cngf.py` beside the real
  `cnfg.py`, and the config accessor is `fig()`. These look like transcription
  slips — confirm intent before treating either as canonical.
- `.claude/settings.json` sets `worktree.bgIsolation: none`, so background
  sessions edit this checkout **in place** rather than in an isolated worktree.
- The scanner **parses `metadata.json`** (`name`/`version`/`branchVersion`/`cycle`)
  but records `config.json` by **path only** — `config.json` is reserved for
  registry config and isn't parsed yet. Schema + rules:
  `project/design/metadata-schema.md`.
- `uv run main.py` writes real rows to `~/.config/dev-reg/registry.db`; the
  **tests** never do — they use temp dirs + in-memory DBs (see Testing above).

## Git

Independent git repo (not part of any parent workspace). Currently **no commits
yet** — everything is untracked. The working branch is `master`, but `main` is
the intended default branch for PRs.
