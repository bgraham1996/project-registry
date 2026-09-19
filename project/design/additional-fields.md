# Design: additional metadata / config fields to parse

**Status:** proposed — open · **Date:** 2026-09-18 · pending a survey of the user's
other projects.

## Context

The scanner currently parses a fixed, small set of fields:

- from `metadata.json` → `projectName`, `projectVersion`, `branchVersion`, `cycle`
  (see [`metadata-schema.md`](metadata-schema.md), via `Scanner.METADATA_FIELDS`);
- from `config.json` → `tags`, `notes`, and the `track` gate
  (see [`config-schema.md`](config-schema.md), via `Scanner.apply_config`).

We want to **add more tags/metadata fields** to index, but the exact set isn't
decided yet: the user needs to **look through their other projects first** to see
what fields actually exist in the wild and would be worth surfacing. This note
just captures the intent and the extension points so the work is ready to pick up
once that survey is done.

## Open question (to resolve after the survey)

- Which new keys should `metadata.json` and/or `config.json` carry? (e.g.
  description, language/stack, owner, links/URLs, status beyond `cycle`,
  last-touched, priority, aliases — **placeholder list, confirm against real
  projects**.)
- For each: does it belong in `metadata.json` (project self-description) or
  `config.json` (registry/tooling config)? Same split as the existing docs.
- Is it a scalar (new TEXT column) or a list/structured value (JSON-encoded TEXT,
  like `tags`)?

## Where each new field touches the code (checklist per field)

Adding a tracked field today is a hardcoded, ~5-place change — capture this so the
survey's output maps straight onto edits:

1. **`app/data_models/watched_dirs.py`** — add the attr to `WatchlistItem.__init__`,
   and the mapping in `to_row()` / `from_row()`.
2. **`app/cache/schema.py`** — add the column to the `watched_dirs` CREATE TABLE
   **and** an additive `ALTER TABLE ... ADD COLUMN` in `MIGRATIONS` (so existing
   DBs converge). The `v_*` views are `SELECT *`, so they pick it up for free.
3. **`app/scanner/scanner.py`** — the value source: a new entry in
   `METADATA_FIELDS` (for a `metadata.json` scalar) or a new read in
   `apply_config()` (for a `config.json` value). Keep the defensive stance
   (missing/malformed never raises).
4. **`app/ux/cli.py`** — add the field to `_item_dict` (this alone flows it into
   both `--json` and `--csv`, which derive their columns from it) and, if it
   should be visible in the terminal, to `render_detail` / the table.
5. **`app/ux/tui.py`** — add a column to `render_table` if it belongs in the
   dashboard view.
6. **Tests + the schema docs** — extend `tests/` and update
   `metadata-schema.md` / `config-schema.md` with the new keys.

## Possible follow-up (not now)

The fact that a field is listed in ~6 places is the friction here. If the survey
turns up many new fields, consider a **single ordered field descriptor** (name,
column, source file + JSON key, scalar-vs-list, whether it's displayed) that the
model mapping, schema, scanner, and serializers all derive from — collapsing the
parallel lists. Out of scope for the first batch; revisit if the count grows.
