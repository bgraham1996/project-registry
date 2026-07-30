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

## Next — fill the empty layers

- ⬜ **Parse `config.json`** in the scanner — reserved for registry/tooling config
  and recorded by *path only* today. Define its schema (a follow-up design doc)
  and a consumer before parsing it.
- ⬜ **API surface** (`app/api/`): the local, predefined queries the clients
  call — the "access/control point" the README describes.
- ⬜ **Richer models** (`app/data_models/projects.py`,
  `session_manager.py`): a project abstraction beyond the raw watched-dir row,
  and session/lifecycle handling.
- 🟡 **UX layer** (`app/ux/`): placeholder TUI done — `app/ux/tui.py` is a
  read-only `rich` table view of the registry (a *client*: reads the DB via
  `WatchlistRepo`, never scans/writes). `uv run python -m app.ux.tui`, or
  `--watch` for a live-refreshing view. Presentation (`render_table`) is pure and
  tested. Next: key-driven navigation / actions once there's more to interact with.

## Later — the two clients

- ⬜ **Python client** querying the SQLite DB.
- ⬜ **Go client** querying the same DB.

## Housekeeping

- ⬜ Remove the leftover empty `app/config_service/cngf.py` (confirm first).
- ⬜ Decide whether `fig()` / `cnfg.py` names stay or get normalised.
- ✅ Add a test runner (`uv add --dev pytest`) once there's behaviour worth
  pinning.
- ✅ Create `project/design/` and record architecture decisions as they're made
  (first: `metadata-schema.md`).
- ✅ Fill in the `regProject/` fixture files (`config.json`, `metadata.json`) so
  the scanner has a realistic target to index.
- ✅ First commit — initial commit landed on `main` (local only, no remote yet).
