# Architecture

## Design intent

The registry is a **local data service**, not a live filesystem scanner. Project
metadata is indexed into a SQLite database that serves as the single source of
truth. Everything else (a scanner that populates it, clients that read it) talks
to that one database rather than to the filesystem directly.

```
  ┌──────────────┐              ┌──────────────┐
  │ TUI (rich)   │  ✅          │ Go CLI       │  ✅
  └──────┬───────┘              └──────┬───────┘
         │ Registry (Python)          │ queries the same
         │ app/api/registry.py        │ v_* views directly
         └────────────┬───────────────┘
                      ▼   read-only, through v_* views
            ┌───────────────────┐
            │  SQLite database  │   ~/.config/dev-reg/registry.db
            │  (source of truth)│   tables + read views
            └─────────┬─────────┘
                      ▲   writes (the only writer)
             ┌────────┴────────┐
             │  scanner        │   ✅ walks scan_roots' subdirs,
             │  / indexer      │   upserts *tracked* WatchlistItems
             └─────────────────┘
```

Read/write is one-directional by design: the **scanner** is the only writer, and
every front end is a **read-only** consumer of the same SQLite file. The read
surface is defined once as SQL **views** in the database (`v_projects`,
`v_git_projects`, `v_cycle_counts`); the Python `Registry` facade and the Go CLI
both query those same views, so the two clients cannot drift apart.

## Layers as they exist today

The code is organised into a small set of responsibilities, each kept
deliberately narrow:

| Layer | Where | Responsibility |
|-------|-------|----------------|
| **Config** | `app/config_service/cnfg.py` | Supplies global vars (DB dir/name, `scan_roots`); resolves the absolute DB path and expanded scan roots. |
| **Connection** | `app/cache/cache_manager.py` (`Db`) | Owns the `sqlite3` connection; create-or-open, apply schema, then run additive `_migrate()`. |
| **Schema** | `app/cache/schema.py` | Central idempotent DDL: tables, read `v_*` views, and `MIGRATIONS` (additive `ALTER`s). |
| **Repository (write)** | `app/cache/watchlist_repo.py` (`WatchlistRepo`) | All write/CRUD SQL for `watched_dirs` (`insert`/`upsert`/`delete_by_path`/getters). |
| **Query API (read)** | `app/api/registry.py` (`Registry`) | Read-only facade over the `v_*` views — the predefined queries clients call. No writes. |
| **Model** | `app/data_models/watched_dirs.py` (`WatchlistItem`) | In-memory record + row⇄attr mapping (`tags` ⇄ JSON text). |
| **Scanner** | `app/scanner/scanner.py` (`Scanner`) | Walks each `scan_root`'s immediate subdirs, describes each from on-disk signals, upserts *tracked* ones (prunes opt-outs). The only writer. |
| **UX (view)** | `app/ux/tui.py` | Read-only `rich` table over the `Registry`. A client, not a writer. |
| **Go client** | `clients/go/` | Read-only CLI over the same `v_*` views (pure-Go `modernc.org/sqlite`). |
| **Entry point** | `main.py` (root) | Wires config → `Db` → `Scanner` → `WatchlistRepo`; scans and lists. |

### Deliberate separations

- **Reads and writes are separate objects.** `WatchlistRepo` owns writes/CRUD;
  the read-only `Registry` owns the predefined queries. A client (TUI, Go)
  holding a `Registry` has no way to mutate the store.
- **The read contract lives in the database as views**, not as query strings in
  one client — so Python and Go query identical SQL. Record-returning views
  (`v_projects`, `v_git_projects`) select the full column set (so `from_row` can
  rebuild a whole record); rollup views (`v_cycle_counts`) return aggregates.
  See `project/design/query-api.md`.
- **SQL lives only in the repository / query API.** `Db` just owns the
  connection; the model just maps rows to attributes; neither writes SQL.
- **The model owns its row mapping.** `to_row()` / `from_row()` are the single
  place camelCase attributes translate to snake_case columns, so the repo builds
  statements generically from `to_row().keys()`.
- **Schema is idempotent and centralised.** Every statement is
  `CREATE ... IF NOT EXISTS`, so `Db.init()` can run the whole `SCHEMA` list on
  every startup whether the DB is new or already populated. Column *additions*
  to an existing DB (which `CREATE TABLE IF NOT EXISTS` can't apply) go through
  `schema.MIGRATIONS` + `Db._migrate()` — additive `ALTER TABLE … ADD COLUMN`,
  tolerant of already-applied. Non-additive changes (view/column bodies) have no
  migration path yet — a known gap.

## Data flow (current slice)

`main.py` → `Db()` builds a `Configure` (seeded with defaults) → `db.init()`
ensures `~/.config/dev-reg/` exists, connects (creating the file if absent),
sets `row_factory = sqlite3.Row`, and applies the schema → returns whether the
file pre-existed → `Scanner(repo, config.scan_roots()).scan()` walks each root's
immediate subdirs, builds a `WatchlistItem` per project from on-disk signals, and
`upsert`s each *tracked* project (idempotent on `path`, so re-scans refresh
rather than duplicate; a directory that opted out via `config.json` `track:false`
is skipped and any existing row pruned) → `repo.all()` reads them back for
printing. The TUI instead reads through `Registry(db.connection).projects()`
(the `v_projects` view) → `render_table()`, read-only; the Go client queries the
same views over the same file.

## Scanner detection (what it reads off disk)

The scanner is deliberately **cheap and side-effect free** — `stat` calls plus a
single read of `.git/HEAD`, no subprocesses and no writes to the scanned trees:

- **Roots are fenced.** Only the explicit `scan_roots` from config are walked;
  the registry is never handed the whole filesystem. Missing roots are skipped
  (a root need not exist yet).
- **Candidates** are each root's immediate subdirectories; hidden `.dotdirs`
  (`.git`, `.obsidian`, …) are skipped as tooling/state, not projects.
- **Git detection** reads the branch straight from `.git/HEAD` (`ref: refs/heads/…`),
  returning `None` for a detached HEAD or a `.git` file pointing at a worktree
  (not followed yet). `dirType` is `"git"` or `"dir"`.
- **`metadata.json` is parsed** into the descriptive fields — `name` (overrides
  the directory-name default), `version` → `projectVersion`, `branchVersion`,
  and `cycle`. Parsing is best-effort: a missing/empty/malformed file, a non-object
  top level, or a non-scalar value leaves the field `None` rather than raising, so
  a bad metadata file never breaks a scan. Scalars are coerced to `str` (TEXT
  columns). Schema and rules: `project/design/metadata-schema.md`.
- **`config.json` is registry/tooling config** (its own lane, kept apart from
  the project's self-describing `metadata.json`). Parsed for: `track` — an
  **opt-out gate** (`false` excludes the dir; the scanner skips it and prunes any
  existing row, so "untracked" = "absent from the registry" even after a flip);
  `tags` (list → JSON-encoded `tags` column); and `notes` (string). Same
  defensive parsing — a bad file never breaks a scan or silently hides a project.
  Schema and rules: `project/design/config-schema.md`.

## The `app` package as one library

`app/` is a single importable library: it has `app/__init__.py`, and every
subpackage (`app/cache`, `app/config_service`, `app/data_models`) has its own
`__init__.py`. Imports are **absolute from the `app` root**, e.g.
`from app.config_service.cnfg import Configure`. This resolves because scripts
run from the repo root put the repo root on `sys.path`.

> **Do not reintroduce hyphenated directory names** — they are not importable as
> Python packages. If the project is later installed/packaged, declare `app` in
> `pyproject.toml` instead of relying on run-from-root behaviour.
