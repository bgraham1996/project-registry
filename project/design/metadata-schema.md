# Design: project metadata schema and scanner parsing

**Status:** accepted · **Date:** 2026-07-30 · first design doc for this repo.

## Context

The scanner already detected the *presence* of a project's `metadata.json` and
`config.json` and recorded their paths, but it never read their contents — so
`WatchlistItem.projectVersion`, `branchVersion`, and `cycle` stayed `None` for
every indexed project. This doc defines what those files mean and how the scanner
turns them into a `WatchlistItem`.

## Decision

### Two files, two roles

- **`metadata.json` — the project's self-description.** Author-maintained, lives
  in the project it describes. The scanner **parses** it to fill the descriptive
  fields of `WatchlistItem`. This is the file the roadmap's "parse metadata" item
  refers to.
- **`config.json` — reserved for registry/tooling config.** Recorded by **path
  only** for now; the scanner does **not** parse it into descriptive fields.
  It is parsed later, when a consumer exists (e.g. per-project registry options
  like "track / don't track", tags, aliases). Keeping it out of the descriptive
  mapping avoids an ambiguous precedence question (which file wins?) before we
  have a real need for config.

### `metadata.json` schema

A JSON **object**. Recognised keys (all optional):

| Key            | → `WatchlistItem` attr | → `watched_dirs` column | Meaning |
|----------------|------------------------|-------------------------|---------|
| `name`         | `projectName`          | `project_name`          | Canonical project name. **Overrides** the directory-name default. |
| `version`      | `projectVersion`       | `project_version`       | Project version (e.g. `"0.2.0"`). |
| `branchVersion`| `branchVersion`        | `branch_version`        | Version marker for the current branch. |
| `cycle`        | `cycle`                | `cycle`                 | Project cycle/stage marker (e.g. `"active"`). |

Unrecognised keys are ignored. The canonical example lives in
`regProject/metadata.json`:

```json
{
  "name": "regProject",
  "version": "0.2.0",
  "branchVersion": "0.2.0-dev",
  "cycle": "active"
}
```

### Parsing rules (defensive by design)

Indexing must never fail because one project ships a bad metadata file. So
`Scanner.apply_metadata` (via `Scanner.read_json`):

- **Missing / unreadable / empty / invalid-JSON file** → no fields set (all stay
  `None`); the path is still recorded. No exception propagates.
- **Top level is not a JSON object** (e.g. a list) → ignored entirely.
- **Per-key value must be a scalar** (`str` / `int` / `float`); non-scalar values
  (objects, arrays) are skipped. `bool` is explicitly rejected — it is an `int`
  subclass but a boolean version/cycle is meaningless.
- **Scalars are coerced to `str`** to match the TEXT columns, so `"version": 2`
  stores `"2"`.
- **`name` override:** applied only when present, so a metadata file that omits
  `name` leaves the directory-name default from `describe()` intact.

## Consequences

- All four descriptive fields can now be populated purely from on-disk signals,
  keeping the scanner subprocess-free and side-effect-free.
- `config.json`'s eventual schema is left open — a follow-up design doc will
  define it when the first config consumer lands.
- Precedence between `metadata.json` and `config.json` is a non-issue today
  because only one of them is parsed. Revisit here if that changes.
