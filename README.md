# project-registry

A small, local, API-like service for keeping track of your dev projects across
different filesystem paths and Obsidian vaults.

Rather than reading project directories live on every request, `project-registry`
**indexes** them into a local **SQLite database** — one source of truth with a
single access/control point, so queries are predefined and can change later
without rework. One command (`scan`) writes; everything else is read-only. Clients
in **Python** (a `rich` TUI and a query CLI) and **Go** read the same database
through the same shared SQL views.

## Install

Python 3.13, managed with [`uv`](https://docs.astral.sh/uv/).

```bash
uv tool install .      # puts `project-registry` on your PATH (re-run with --reinstall to update)
```

Or run it from a clone without installing: `uv run project-registry ...`.

## Quickstart

```bash
project-registry scan            # index projects under the configured roots (the only writer)
project-registry list            # list live projects (a table)
project-registry list --git      # only git checkouts
project-registry doctor          # check which projects have good/missing/broken metadata.json
project-registry tui             # live rich dashboard (--watch to auto-refresh)
project-registry config          # show the effective config and where to customise it
```

## Commands

| Command | Writes? | What it does |
|---|---|---|
| `scan [--scan-root DIR]...` | **yes** | Index projects under the scan roots. Repeatable `--scan-root` overrides the config for one run. |
| `list [--git] [--cycle C] [--project P] [--json\|--csv]` | no | List live projects; filters compose. |
| `show PATH [--json]` | no | Detail for one project. |
| `cycles [--json]` | no | Count of projects per lifecycle cycle. |
| `doctor [--scan-root DIR]... [--json]` | no | Per-project `metadata.json` health report. |
| `config [--json]` | no | Show effective configuration + config-file path. |
| `tui [--watch] [--interval S]` | no | Rich dashboard view. |

Global `--db PATH` points the DB-backed read commands at a specific database file.

## How it works

- **`scan`** walks the configured roots, treats each root's immediate subdirs as
  candidate projects, and records each into SQLite. Detection is cheap and
  side-effect-free: a `.git` marker + branch from `.git/HEAD`, and the
  highest-level `metadata.json` found beneath the project (descriptive data:
  `name`, `version`, `cycle`, `tags`, `notes`). A project's `config.json` is for
  per-project configuration — only its `track` opt-out flag is read.
- Removal is a **soft-delete**: a project that disappears, is ignored, or opts out
  is marked removed (kept as history), not deleted. The read views show only live
  projects.
- The read side is a set of **SQL views** (`v_projects`, `v_git_projects`,
  `v_cycle_counts`) that every client — Python, Go, and your own scripts — reads
  through identically.

## Documentation

- **[docs/configuration.md](docs/configuration.md)** — the config file: scan
  roots, ignore list, db path; and how to index projects nested deeper than one
  level.
- **[docs/querying-the-database.md](docs/querying-the-database.md)** — the DB
  location, schema, views, soft-removal, and reading it with `sqlite3`/Python.
- **[docs/scripting.md](docs/scripting.md)** — using the registry from other
  scripts: the CLI (`--json`/`--csv`), the SQL views, or the Python package.

## Development

```bash
uv sync                 # install deps into .venv
uv run pytest           # run the test suite (tests/)
uv run main.py          # dev smoke test: same scan as `project-registry scan`
```

Design decisions are recorded as ADRs under `project/design/`. The Go client is a
separate module under `clients/go/`. See `CLAUDE.md` for the full internal map.
