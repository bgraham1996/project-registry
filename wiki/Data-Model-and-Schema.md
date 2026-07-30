# Data Model & Schema

## `WatchlistItem`

Defined in `app/data_models/watched_dirs.py`. An in-memory record describing one
tracked project directory. Attributes are **camelCase**; a fresh instance gets a
`uuid4` `id` and `None` for everything else.

| Attribute | Meaning |
|-----------|---------|
| `id` | Primary key (`uuid4`, stored as text). |
| `path` | Absolute path of the tracked directory. **Natural unique key.** |
| `metadatapath` | Path to the project's metadata file (e.g. `metadata.json`). |
| `configpath` | Path to the project's config file. |
| `gitpath` | Path to the `.git` directory, if any. |
| `projectName` | Project name (indexed). |
| `projectVersion` | Project version. |
| `branchName` | Current branch. |
| `branchVersion` | Branch version. |
| `cycle` | Project cycle/stage marker. |
| `dirType` | e.g. `"git"` or `"dir"`. |

### Row mapping

The model owns the translation between attributes and columns:

- **`to_row()`** → dict of `column → value`, camelCase attr → snake_case column.
  Omits `created_at` / `updated_at` (the DB fills those).
- **`from_row(row)`** *(classmethod)* → rebuilds a `WatchlistItem` from a
  `sqlite3.Row` (or any dict-like row). The inverse of `to_row()`.

This is the single place the attr↔column names diverge, which lets the repository
build INSERT/UPSERT statements generically from `to_row().keys()`.

## The `watched_dirs` table

Defined in `app/cache/schema.py`. Columns mirror `WatchlistItem` (camelCase →
snake_case):

```sql
CREATE TABLE IF NOT EXISTS watched_dirs (
    id              TEXT PRIMARY KEY,
    path            TEXT NOT NULL UNIQUE,
    metadata_path   TEXT,
    config_path     TEXT,
    git_path        TEXT,
    project_name    TEXT,
    project_version TEXT,
    branch_name     TEXT,
    branch_version  TEXT,
    cycle           TEXT,
    dir_type        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_watched_dirs_project_name
    ON watched_dirs(project_name);
```

- **`path` is `UNIQUE`** — it is the conflict key for upserts and the natural
  lookup key from the scanner and clients.
- **`project_name` is indexed** because clients look projects up by name.
- **`created_at` / `updated_at`** default to `datetime('now')`; the model never
  sets them.

Adding a new table or index? Put the DDL in the `SCHEMA` list in
`app/cache/schema.py`; `Db.init()` applies it on the next startup.

## Attr ↔ column reference

| `WatchlistItem` attr | `watched_dirs` column |
|----------------------|-----------------------|
| `id` | `id` |
| `path` | `path` |
| `metadatapath` | `metadata_path` |
| `configpath` | `config_path` |
| `gitpath` | `git_path` |
| `projectName` | `project_name` |
| `projectVersion` | `project_version` |
| `branchName` | `branch_name` |
| `branchVersion` | `branch_version` |
| `cycle` | `cycle` |
| `dirType` | `dir_type` |
| *(DB-managed)* | `created_at`, `updated_at` |
