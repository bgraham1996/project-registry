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

**Early scaffold, first vertical slice working end-to-end.** `uv run main.py`
creates-or-opens the SQLite database, applies the schema, **scans the configured
roots** (`~/dev` by default), upserts a `WatchlistItem` for each project found,
and prints all watched dirs. A read-only `rich` TUI (`app/ux/tui.py`) views the
result. The scanner and TUI are pinned by a small `pytest` suite. The still-empty
layers are the API surface (`app/api/`), the richer models (`projects.py`,
`session_manager.py`), and the two planned clients.

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
| Language / tooling | Python 3.13, managed with `uv` |
| Dependencies | `rich` (runtime, for the TUI); DB layer uses stdlib `sqlite3` |
| Database | SQLite at `~/.config/dev-reg/registry.db` |
| Working entry point | `uv run main.py` (scan + list) |
| Scanner | `app/scanner/` — indexes projects under configured `scan_roots` |
| TUI (read-only view) | `uv run python -m app.ux.tui` (`--watch` to live-refresh) |
| Tables | `watched_dirs` (+ index on `project_name`) |
| Clients | Planned: Python + Go (neither built yet) |
| Tests | `pytest` configured — scanner + TUI covered (`tests/`) |
| Git | Independent repo, **no commits yet** (branch `master`; `main` intended for PRs) |
