# Read/query API: SQL views as the shared contract

## Context

The README frames project-registry as a "local API-like service" whose value is
"an easy access/control point" where queries can be "predefined … without too
much hassle." Two clients are planned against the same local SQLite database —
**one in Python and one in Go**.

The write path (config → `Db`/schema → `WatchlistRepo` → `Scanner`) already
existed. What was missing was the *read* surface: the TUI reached straight
through `WatchlistRepo.all()`, and the repo is CRUD-by-path, not a query API.
There was nothing a second client could target, and nothing "predefined."

## Decision

**Predefined read queries live as SQL `VIEW`s in the database, not as query
strings inside one client.** They are declared in `app/cache/schema.py`
alongside the table DDL and applied idempotently by `Db.init` on every startup.

- Record-returning views (`v_projects`, `v_git_projects`) select the **full**
  `watched_dirs` column set and only filter/order rows — never drop columns — so
  any client can reconstruct a whole record from them.
- Rollup views (`v_cycle_counts`) return aggregates.

Python gets a thin typed facade, `app.api.registry.Registry(connection)`, whose
methods are one-liners over those views returning `WatchlistItem`s / plain
dicts. It is **read-only by construction**: writes stay on `WatchlistRepo`, so a
client holding a `Registry` cannot mutate the store.

## Why views instead of a Python-only query module

The contract has to be reachable from Go too. A view definition lives *in the
database file*, so the Go client runs the identical `SELECT * FROM v_projects`
without re-deriving or drifting from Python's SQL. That is what makes "one
access/control point" literally true rather than "Python owns the real logic and
Go reimplements it." Parameterised lookups (by cycle, by project) are trivial
`WHERE` clauses any client adds over the same views; only the stable projections
and rollups are worth freezing as named views.

## Consequences / follow-ups

- New predefined queries are added as `v_*` views in `schema.py` (+ a wrapper
  method), keeping SQL out of clients.
- Views are recreated with `CREATE VIEW IF NOT EXISTS`; **changing** a view's
  body will need a migration story (drop/recreate) once the DB is long-lived —
  not yet handled, flagged here for when it matters.
- The Go client, when built, reads these same views — it is now unblocked.
