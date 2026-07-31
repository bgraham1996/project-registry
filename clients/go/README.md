# Go client

The Go half of project-registry's "two clients, one Python and one Go". A small,
**read-only** CLI that opens the same local SQLite database the scanner writes
and reads it through the same shared SQL views the Python `Registry` uses
(`v_projects`, `v_git_projects`) — no client-specific SQL, no writes. Populating
the registry is the scanner's job (`uv run main.py` from the repo root).

## Build & run

```bash
cd clients/go
go build -o registry .

./registry            # all watched dirs (v_projects)
./registry -git       # only git checkouts (v_git_projects)
./registry -json      # JSON instead of a table
./registry -db PATH   # read a specific database file
```

By default it reads `~/.config/dev-reg/registry.db` (the same path
`app/config_service/cnfg.py` computes). A missing database is reported as
"run the scanner first" rather than silently created — the DB is opened
read-only (`mode=ro`).

## Dependencies

- **`modernc.org/sqlite`** — a pure-Go SQLite driver (no cgo), so the client
  builds and runs without a C toolchain. Pinned in `go.mod` / `go.sum`.

## Why it reads views, not tables

The read contract lives in the database as `v_*` views (see
`project/design/query-api.md`). Because the view definitions live in the file
itself, this client and the Python one query the identical SQL and cannot drift.
The views `SELECT *`, so new columns (e.g. `tags`, `notes`) appear here with no
Go change — only the `SELECT` list in `queryProjects` decides what is displayed.
