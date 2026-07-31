# Roadmap

Derived from the README intent and the current state of the code. Not a
commitment — a reading of where the scaffold is pointed.

## Done — the first vertical slice

- ✅ Config service resolves the DB path (`~/.config/dev-reg/registry.db`).
- ✅ `Db` create-or-open + idempotent schema application.
- ✅ `watched_dirs` table + `project_name` index.
- ✅ `WatchlistItem` model with `to_row()` / `from_row()` mapping.
- ✅ `WatchlistRepo` with `insert` / `upsert` / `get` / `get_by_path` /
  `find_by_project` / `all`.
- ✅ Working `main.py` that scans the configured roots and lists watched dirs.
- ✅ **Scanner** (`app/scanner/`): descends only the explicit `scan_roots` from
  config (never full-filesystem), treats each root's immediate subdirs as
  candidate projects, detects `.git` + current branch (read straight from
  `.git/HEAD`, no subprocess) and the presence of `metadata.json` / `config.json`,
  and `upsert`s each `WatchlistItem`. Idempotent on re-scan.
- ✅ Test runner configured (`pytest`, `pythonpath=["."]`); scanner detection is
  pinned by `tests/test_scanner.py` (temp dir + in-memory DB, never the real tree).
- ✅ **Parse `metadata.json`** in the scanner to fill the descriptive fields
  (`projectName` override, `projectVersion`, `branchVersion`, `cycle`) —
  best-effort, bad/empty/malformed files leave fields `None` without raising.
  Schema + rules recorded in `project/design/metadata-schema.md`; worked example
  in `regProject/metadata.json`; pinned by `tests/test_scanner.py`.
- ✅ **Read query API** (`app/api/registry.py`): read-only `Registry` facade over
  shared SQL **views** (`v_projects` / `v_git_projects` / `v_cycle_counts`) so
  both clients query one contract from the DB file. The TUI now reads through it.
  Decision recorded in `project/design/query-api.md`; pinned by `tests/test_api.py`.
- ✅ **Parse `config.json`** in the scanner: `track` **opt-out** (skip + prune),
  plus `tags` (JSON-encoded) and `notes` columns. Additive `MIGRATIONS` +
  `Db._migrate()` add the new columns to pre-existing DBs. Recorded in
  `project/design/config-schema.md`; pinned by `tests/test_scanner.py`.
- ✅ **Go client** (`clients/go/`): read-only CLI over the same views, pure-Go
  `modernc.org/sqlite` (no cgo). `-git` / `-json` / `-db` flags.

## Next — fill the remaining layers

- ⬜ **Surface `tags` / `notes` in the TUI** and add `Registry` filters for them
  (the data and columns now exist end-to-end; only the presentation lags).
- ⬜ **Richer models** (`app/data_models/projects.py`, `session_manager.py`):
  a project abstraction beyond the raw watched-dir row, and session/lifecycle
  handling. (Intentional empty placeholders today — keep in place.)
- 🟡 **UX layer** (`app/ux/`): TUI done — `app/ux/tui.py` is a read-only `rich`
  table over the `Registry`. `uv run python -m app.ux.tui`, or `--watch` for a
  live-refreshing view. Presentation (`render_table`) is pure and tested. Next:
  key-driven navigation / actions once there's more to interact with.
- ⬜ **Migration story for non-additive changes** (view/column bodies) — only
  additive column migrations are handled today.

## The two clients

- ✅ **Python client** — effectively the `Registry` query API + the `rich` TUI,
  both reading the SQLite DB.
- ✅ **Go client** — `clients/go/`, querying the same views over the same file.

## Housekeeping

- ✅ **Keep** the empty stub files/dirs (`cngf.py`, `projects.py`,
  `session_manager.py`, `app/main.py`, empty dirs) — the user has confirmed these
  are intentional future-direction markers. Do **not** remove them.
- ✅ `fig()` / `cnfg.py` names stay (treated as canonical).
- ✅ Add a test runner (`uv add --dev pytest`) once there's behaviour worth
  pinning.
- ✅ Create `project/design/` and record decisions (`metadata-schema.md`,
  `config-schema.md`, `query-api.md`).
- ✅ Fill in the `regProject/` fixture files (`config.json`, `metadata.json`) so
  the scanner has a realistic target to index.
- ✅ Commits landed locally on `master` (no remote yet).
