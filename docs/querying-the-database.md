# Querying the registry database

The registry is a single local SQLite file — the one source of truth that
`scan` writes and every client reads. You can read it with any SQLite tooling;
nothing is proprietary.

```
~/.config/dev-reg/registry.db      # default (see `project-registry config`)
```

> **Read-only, please.** Treat the database as read-only unless you are the
> scanner. Every built-in client opens it with `mode=ro`. `project-registry scan`
> is the only writer — let it own all mutations so the registry stays consistent.

## Read through the views, not the table

Clients never `SELECT * FROM watched_dirs` directly — they read **views**, so the
default filtering/ordering lives in one place and every client (Python, Go, your
scripts) sees the same thing. There are three:

| View | Rows | Use |
|---|---|---|
| `v_projects` | every live project, ordered by name then path | the canonical listing |
| `v_git_projects` | live projects that are git checkouts | "which are real repos, on what branch" |
| `v_cycle_counts` | `(cycle, n)` aggregate | the cycle rollup |

All three exclude **soft-removed** rows (see below). The row views select the full
column set, so you can reconstruct a whole record from them.

```bash
sqlite3 -readonly ~/.config/dev-reg/registry.db \
  "SELECT project_name, dir_type, branch_name, cycle FROM v_projects;"
```

## Columns (`watched_dirs`)

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT | UUID primary key |
| `path` | TEXT | absolute project path (unique) |
| `metadata_path` / `config_path` / `git_path` | TEXT | located files (nullable) |
| `project_name` | TEXT | from `metadata.json` `name`, else the directory name |
| `project_version` / `branch_version` | TEXT | from `metadata.json` |
| `branch_name` | TEXT | current branch (git checkouts) |
| `cycle` | TEXT | lifecycle stage from `metadata.json` (nullable) |
| `dir_type` | TEXT | `git` or `dir` |
| `tags` | TEXT | **JSON-encoded list** (e.g. `["cli","wip"]`), or NULL |
| `notes` | TEXT | free text from `metadata.json` |
| `removed_at` | TEXT | NULL = live; a timestamp = soft-removed (history) |
| `created_at` / `updated_at` | TEXT | timestamps (`datetime('now')`) |

`tags` is stored as a JSON string — decode it when you read it (`json.loads` in
Python, `json_each`/`json_extract` in SQLite).

## Soft-removal and history

Projects that disappear, get ignored, or opt out (`config.json` `"track": false`)
are **not deleted** — their row's `removed_at` is set. The views hide them, so
clients only ever see live projects. To inspect history, query the table directly:

```bash
# what left the registry, and when
sqlite3 -readonly ~/.config/dev-reg/registry.db \
  "SELECT project_name, path, removed_at FROM watched_dirs
   WHERE removed_at IS NOT NULL ORDER BY removed_at DESC;"
```

## Reading from Python (stdlib only)

```python
import json, sqlite3
from pathlib import Path

db = Path("~/.config/dev-reg/registry.db").expanduser()
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)   # read-only
con.row_factory = sqlite3.Row

for row in con.execute("SELECT * FROM v_git_projects"):
    tags = json.loads(row["tags"]) if row["tags"] else []
    print(row["project_name"], row["branch_name"], tags)
con.close()
```

If you have the package installed (`uv tool install .` / `uv add`), you can skip
the raw SQL and use the read-only façade instead — see
[scripting.md](scripting.md).
