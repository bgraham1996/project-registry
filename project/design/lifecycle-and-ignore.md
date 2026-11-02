# ADR: Metadata/config split, soft-delete lifecycle, and an ignore list

Status: accepted (2026-11-02). Supersedes the tags/notes placement in
`config-schema.md` (point-in-time; that doc is left as-is per the ADR convention).

## Context

Running the scanner against the real `~/dev` surfaced three problems (see the
survey that prompted this): the registry accumulated **ghost rows** for
deleted/renamed projects (≈1/3 of rows pointed at dirs that no longer existed,
including a macOS case-duplicate `Aaja`/`aaja`); `tags` lived in `config.json`
while the rest of the descriptive data lived in `metadata.json`, so a project's
tags were split across two files; and there was no way to exclude a holding-pen
directory (`archive/`) of dormant projects.

## Decision

1. **All descriptive data lives in `metadata.json`.** `tags` and `notes` move
   there alongside `name` / `version` / `branchVersion` / `cycle`. `config.json`
   is reserved for project-specific **configuration**; the only key the registry
   reads from it is the `track` opt-out gate. Its path is still recorded for
   reference, but its contents never populate item fields.
   - `notes` was moved together with `tags` (the user asked for `tags` + `cycle`
     in metadata; `notes` is descriptive, so keeping it in `config.json` would
     violate "config is for configuration"). Flagged as a judgment call.

2. **Removal is a soft-delete, for history.** A new nullable `removed_at` column
   marks when a row left the live set; it is never hard-deleted. `scan` upserts
   every present, tracked candidate (an upsert **clears** `removed_at`, so a dir
   that reappears is reactivated — same row, same id), then a **reconcile** pass
   soft-removes any previously-live row under a scanned root it didn't see this
   pass: a dir that was deleted/renamed/moved, is now ignored, or opted out via
   `track: false`. Reconcile is scoped to the roots actually scanned, so scanning
   one root never touches rows from another. All client-facing views filter
   `removed_at IS NULL`, so clients see only live projects; history stays queryable
   in the table (`repo.all(include_removed=True)`).

3. **A global ignore list.** `Configure` gains `ignore` (default `["archive"]`):
   candidate directory names the scanner skips entirely, matched case-insensitively
   against each root's immediate children. An ignored dir already in the registry
   is soft-removed by the reconcile pass. This is *global* app config (how the
   registry scans), distinct from per-project `config.json`.

## Consequences

- **View-migration gap closed (for views).** Views moved out of the one-shot
  `SCHEMA`/`CREATE ... IF NOT EXISTS` pass into their own `VIEWS` phase that runs
  **after** migrations and **drops + recreates** each view every `init`. So a view
  body can now reference a migrated-in column (`removed_at`) and a future view
  change actually takes effect on existing DBs. Table/column changes are still
  additive-only via `MIGRATIONS`.
- `Db.init` order is now: `TABLES` → `MIGRATIONS` → `VIEWS`.
- `WatchlistRepo`: `all(include_removed=False)` (live-only by default),
  `mark_removed_by_path`, `active_paths`; the hard `delete_by_path` was removed
  (nothing hard-deletes anymore).
- Verified against the real `~/dev`: 53 pre-existing rows migrated in place, 19
  soft-removed (17 ghosts + the case-dup + `archive`), 0 deleted; views report 35
  live projects.

## Alternatives considered

- **Hard delete / prune** (the prior behaviour) — simplest, but loses the history
  of what used to be tracked. Rejected: the user explicitly wants history.
- **Per-project opt-out only** (no global ignore) — `archive/` would need a
  `config.json` with `track:false` dropped into it (and into each dormant project).
  Rejected: a single global ignore for the holding-pen dir is far less fuss.
