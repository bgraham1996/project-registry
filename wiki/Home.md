# project-registry — Wiki

A local, API-like service for keeping track of the user's dev projects across
different filesystem paths and Obsidian vaults.

## The idea

Rather than scanning project directories live on every request, project data is
**indexed into a local SQLite database** that acts as the single source of truth.
This gives one access/control point, lets queries be predefined and revised later
without rework, and decouples the front end from the filesystem.

Two clients are planned against that same database — **one in Python and one in
Go** — both reading the local SQLite file.

## Maturity

**Working end-to-end, both clients live.** `uv run main.py` creates-or-opens the
SQLite database, applies the schema (tables **+ read views**), **scans the
configured roots** (`~/dev` by default), upserts a `WatchlistItem` for each
*tracked* project found, and prints all watched dirs. Reads go through a
predefined **query API** (`app/api/registry.py`) over shared SQL views; two
clients consume it — a read-only `rich` TUI (`app/ux/tui.py`) and a **Go CLI**
(`clients/go/`). Scanner, TUI, and query API are pinned by a `pytest` suite. The
still-empty layers (`app/data_models/projects.py`, `session_manager.py`,
`app/main.py`, `libs/`) are **intentional roadmap placeholders**, not oversights
— leave them in place.

## Wiki pages

- **[Architecture](Architecture.md)** — layers, data flow, design intent.
- **[Data Model & Schema](Data-Model-and-Schema.md)** — `WatchlistItem`, the
  `watched_dirs` table, and the attr↔column mapping.
- **[Modules](Modules.md)** — file-by-file reference of what exists and what's a stub.
- **[Development](Development.md)** — how to run it, conventions, gotchas.
- **[Roadmap](Roadmap.md)** — what's done and what's next.

## At a glance

| Aspect | State |
|--------|-------|
| Language / tooling | Python 3.13, managed with `uv`; Go 1.25 for the Go client |
| Dependencies | `rich` (runtime, for the TUI); DB layer uses stdlib `sqlite3`. Go client: `modernc.org/sqlite` (pure-Go, no cgo) |
| Database | SQLite at `~/.config/dev-reg/registry.db` |
| Working entry point | `uv run main.py` (scan + list) |
| Scanner | `app/scanner/` — indexes *tracked* projects under configured `scan_roots` |
| Read API | `app/api/registry.py` — read-only `Registry` over shared `v_*` views |
| TUI (read-only view) | `uv run python -m app.ux.tui` (`--watch` to live-refresh) |
| Go client | `clients/go/` — read-only CLI over the same views (`-git` / `-json` / `-db`) |
| Tables / views | `watched_dirs` (+ index) and read views `v_projects` / `v_git_projects` / `v_cycle_counts` |
| Clients | Python (`Registry` + TUI) ✅ and Go CLI ✅ |
| Tests | `pytest` — scanner + TUI + query API covered (`tests/`) |
| Git | Independent repo; commits on `master` (local only, no remote). `main` intended for PRs |
