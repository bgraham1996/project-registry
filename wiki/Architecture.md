# Architecture

## Design intent

The registry is a **local data service**, not a live filesystem scanner. Project
metadata is indexed into a SQLite database that serves as the single source of
truth. Everything else (a scanner that populates it, clients that read it) talks
to that one database rather than to the filesystem directly.

```
  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
  │ TUI view    │   │ Python      │   │ Go          │
  │ (built ✅)  │   │ client (⬜) │   │ client (⬜) │
  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
         │                 │                 │
         └────────┬────────┴─────────────────┘
                  ▼   (read-only)
        ┌───────────────────┐
        │  SQLite database  │   ~/.config/dev-reg/registry.db
        │  (source of truth)│
        └─────────┬─────────┘
                  ▲   (writes)
         ┌────────┴────────┐
         │  scanner        │   ✅ walks scan_roots' subdirs,
         │  / indexer      │   upserts WatchlistItems
         └─────────────────┘
```

Read/write is one-directional by design: the **scanner** is the only writer, and
every front end (the built-in TUI, the planned clients) is a **read-only** consumer
of the same SQLite file.

## Layers as they exist today

The code is organised into a small set of responsibilities, each kept
deliberately narrow:

| Layer | Where | Responsibility |
|-------|-------|----------------|
| **Config** | `app/config_service/cnfg.py` | Supplies global vars (DB dir/name, `scan_roots`); resolves the absolute DB path and expanded scan roots. |
| **Connection** | `app/cache/cache_manager.py` (`Db`) | Owns the `sqlite3` connection; create-or-open + apply schema. |
| **Schema** | `app/cache/schema.py` | Central list of idempotent DDL. |
| **Repository** | `app/cache/watchlist_repo.py` (`WatchlistRepo`) | All SQL for the `watched_dirs` table. |
| **Model** | `app/data_models/watched_dirs.py` (`WatchlistItem`) | In-memory record + row⇄attr mapping. |
| **Scanner** | `app/scanner/scanner.py` (`Scanner`) | Walks each `scan_root`'s immediate subdirs, describes each from on-disk signals, upserts. The only writer. |
| **UX (view)** | `app/ux/tui.py` | Read-only `rich` table over `WatchlistRepo`. A client, not a writer. |
| **Entry point** | `main.py` (root) | Wires config → `Db` → `Scanner` → `WatchlistRepo`; scans and lists. |

### Deliberate separations

- **SQL lives only in the repository.** `Db` just owns the connection; the model
  just maps rows to attributes; neither writes SQL.
- **The model owns its row mapping.** `to_row()` / `from_row()` are the single
  place camelCase attributes translate to snake_case columns, so the repo builds
  statements generically from `to_row().keys()`.
- **Schema is idempotent and centralised.** Every statement is
  `CREATE ... IF NOT EXISTS`, so `Db.init()` can run the whole `SCHEMA` list on
  every startup whether the DB is new or already populated.

## Data flow (current slice)

`main.py` → `Db()` builds a `Configure` (seeded with defaults) → `db.init()`
ensures `~/.config/dev-reg/` exists, connects (creating the file if absent),
sets `row_factory = sqlite3.Row`, and applies the schema → returns whether the
file pre-existed → `Scanner(repo, config.scan_roots()).scan()` walks each root's
immediate subdirs, builds a `WatchlistItem` per project from on-disk signals, and
`upsert`s each (idempotent on `path`, so re-scans refresh rather than duplicate)
→ `repo.all()` reads them back for printing. The TUI takes the same
`repo.all()` → `render_table()` path, read-only.

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
- **Metadata/config** presence is recorded as *paths only* — `metadata.json` /
  `config.json` are noted if present but **not yet parsed**, so an empty or
  malformed file is harmless (this is the next roadmap item).

## The `app` package as one library

`app/` is a single importable library: it has `app/__init__.py`, and every
subpackage (`app/cache`, `app/config_service`, `app/data_models`) has its own
`__init__.py`. Imports are **absolute from the `app` root**, e.g.
`from app.config_service.cnfg import Configure`. This resolves because scripts
run from the repo root put the repo root on `sys.path`.

> **Do not reintroduce hyphenated directory names** — they are not importable as
> Python packages. If the project is later installed/packaged, declare `app` in
> `pyproject.toml` instead of relying on run-from-root behaviour.
