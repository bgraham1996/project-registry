# Design: config.json schema, tracking opt-out, and additive migrations

**Status:** accepted · **Date:** 2026-07-31 · follows `metadata-schema.md`.

## Context

`metadata-schema.md` deliberately left `config.json` **recorded by path only**,
naming its eventual role — "per-project registry options like track / don't
track, tags, aliases" — as a follow-up. This doc lands the first config
consumer. Where `metadata.json` is the project's *self-description*,
`config.json` is **registry/tooling config**: how *this registry* should treat
the project, independent of what the project says about itself.

## Decision

### `config.json` schema

A JSON **object**. Recognised keys (all optional):

| Key      | Type            | Effect |
|----------|-----------------|--------|
| `track`  | boolean         | Gate: `false` excludes the directory from the registry. Any other value (or absent) → tracked. |
| `tags`   | list of scalars | Free-form labels. Stored as `tags` (JSON-encoded TEXT); coerced to a list of strings. |
| `notes`  | string          | Free-form note. Stored as `notes` (TEXT). |

The canonical example lives in `regProject/config.json`. Keys belonging to
`metadata.json` (`version`, `cycle`, …) are **not** read from `config.json` —
the two files stay in their own lanes, so there is no precedence question.

### `track`: skip-and-prune (opt-out, default tracked)

Tracking is **opt-out**: a directory is indexed unless its `config.json`
explicitly sets `track` to the JSON literal `false`.

An untracked directory is **not stored at all**, and if it was indexed on an
earlier run it is **pruned** on the next scan (`WatchlistRepo.delete_by_path`).
So "untracked" means "absent from the registry" as a hard invariant — even after
a project flips the flag — rather than leaving a stale row behind. `track` is a
scan-time gate only; it is intentionally **not** a column on `watched_dirs`
(every stored row is tracked by definition, so a column would be dead weight).

Trade-off accepted: because untracked dirs are never stored, they are not
queryable through the registry — they simply do not exist to it. That is the
intended meaning of the opt-out.

### Parsing rules (defensive, mirrors `apply_metadata`)

`Scanner.apply_config` / `Scanner.is_tracked` never let a bad config file break
indexing or silently hide a project:

- Missing / unreadable / empty / invalid-JSON / non-object `config.json` →
  fields stay `None` **and** the directory stays tracked. A malformed file never
  causes an opt-out.
- `tags`: only a JSON list is read; within it only scalars (`str`/`int`/`float`,
  **not** `bool`) are kept, each coerced to `str`. `tags` in memory is a Python
  list; `None` (no tags) is stored as SQL `NULL`, distinct from `[]`.
- `notes`: only a JSON string is read.
- `track`: only the boolean literal `false` opts out.

### Additive migrations

Adding `tags`/`notes` broke the "just re-run" story for **existing** databases:
`CREATE TABLE IF NOT EXISTS` does not alter a table that already exists, so a DB
created before these columns would be missing them. `schema.MIGRATIONS` now holds
additive `ALTER TABLE … ADD COLUMN` statements, applied by `Db._migrate` after
`create_tables`, each tolerant of a "duplicate column name" error (a fresh DB
already has the column from `CREATE TABLE`; an old DB gains it). Any other error
is re-raised.

This covers **additive column** changes only. Changing a view body or an
existing column still has no migration path — flagged in `query-api.md` and
still open.

## Consequences

- The registry is now **selective**: projects opt out with one line of config,
  and the opt-out is self-healing across scans.
- `tags`/`notes` make `watched_dirs` a richer queryable store; the read views
  (`v_*`) select `*`, so they surface the new columns to every client (Python
  `Registry`, and the Go client) with no view change.
- Schema evolution is safe for additive columns; non-additive changes remain a
  known gap.
