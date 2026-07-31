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
| `tags` | Free-form labels — a **list of strings** in memory. From `config.json`. |
| `notes` | Free-form note (string). From `config.json`. |

Populated by the scanner from two files in their own lanes:
`projectName`/`projectVersion`/`branchVersion`/`cycle` from the project's
**`metadata.json`**; `tags`/`notes` from its **`config.json`**
(`branchName`/`dirType`/`gitpath` come from git; `path`/`*path` from the
filesystem). See `project/design/metadata-schema.md` and
`project/design/config-schema.md` for the schemas and parsing rules.

### Row mapping

The model owns the translation between attributes and columns:

- **`to_row()`** → dict of `column → value`, camelCase attr → snake_case column.
  Omits `created_at` / `updated_at` (the DB fills those). `tags` (a list) is
  `json.dumps`'d to text; `None` stays SQL `NULL` (distinct from `"[]"`).
- **`from_row(row)`** *(classmethod)* → rebuilds a `WatchlistItem` from a
  `sqlite3.Row` (or any dict-like row). The inverse of `to_row()`; `tags` is
  `json.loads`'d back into a list.

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
    tags            TEXT,   -- JSON-encoded list of strings
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_watched_dirs_project_name
    ON watched_dirs(project_name);
```

- **`path` is `UNIQUE`** — it is the conflict key for upserts and the natural
  lookup key from the scanner and clients.
- **`project_name` is indexed** because clients look projects up by name.
- **`tags` holds a JSON array** (e.g. `["example","fixture"]`); the model
  serialises/parses it. `NULL` means "no tags", distinct from an empty list.
- **`created_at` / `updated_at`** default to `datetime('now')`; the model never
  sets them.

Adding a new table or index? Put the DDL in the `SCHEMA` list in
`app/cache/schema.py`; `Db.init()` applies it on the next startup.

## Read views (the query contract)

The read side is defined as SQL **views** in the same `SCHEMA` list, so both
clients (Python `Registry`, Go CLI) read the identical contract from the database
file rather than each re-deriving SQL. See `project/design/query-api.md`.

| View | Kind | Definition |
|------|------|------------|
| `v_projects` | records | every `watched_dirs` row, ordered `project_name` (NULLs last) then `path`. |
| `v_git_projects` | records | as above, filtered to `dir_type = 'git'`. |
| `v_cycle_counts` | rollup | `(cycle, n)` — count of watched dirs per lifecycle `cycle` (NULL = unset). |

Record views select the **full** column set (never drop columns) so a client can
rebuild a whole `WatchlistItem` via `from_row`; rollup views return aggregates.
Parameterised lookups (by cycle, by project, by path) are `WHERE` clauses any
client layers over these views — see `Registry` in **[Modules](Modules.md)**.

## Migrations (additive columns)

`CREATE TABLE IF NOT EXISTS` cannot add a column to a table that already exists,
so columns added after a database was first created (e.g. `tags`, `notes`) are
applied through `schema.MIGRATIONS` — additive `ALTER TABLE … ADD COLUMN`
statements run by `Db._migrate()` after `create_tables()`, each tolerant of a
"duplicate column name" error (a fresh DB already has the column from the
`CREATE TABLE`; an old DB gains it). Only **additive** changes belong here;
changing a view/column body still has no migration path.

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
| `tags` | `tags` *(list ⇄ JSON text)* |
| `notes` | `notes` |
| *(DB-managed)* | `created_at`, `updated_at` |
