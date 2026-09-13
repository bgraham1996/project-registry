# Design: highest-level discovery of metadata.json / config.json

**Status:** accepted · **Date:** 2026-08-23 · extends `metadata-schema.md` and `config-schema.md`.

## Context

Both earlier schema docs assumed `metadata.json` and `config.json` live **at the
project root** — the scanner only ever checked `<candidate>/metadata.json` and
`<candidate>/config.json` (depth 1, no recursion). In practice a project's
descriptive/registry files may sit one or more levels down (e.g. a conventional
`project/config.json`), so a root-only check missed them entirely, leaving the
descriptive fields, `tags`/`notes`, and — importantly — the `track` opt-out
gate blind to any non-root config.

## Decision

The scanner now finds the **highest-level** (shallowest) occurrence of each
target file *anywhere beneath* the candidate directory, via a bounded
breadth-first walk (`Scanner.locate`).

- **Shallowest wins.** BFS from the candidate root means a root-level file is
  found first; a file is only taken from a deeper level if none exists above it.
- **The two files are searched independently.** `config.json` and
  `metadata.json` may resolve to different depths / different subtrees. `locate`
  returns a `{filename: Path}` dict; a file never found is simply absent.
- **Deterministic ties.** Within one depth, directories are visited in sorted
  order, so two same-depth candidates resolve predictably (sorted-first wins).
- **Bounded and pruned, to stay cheap.** Hidden dirs (`.git`, `.venv`,
  `.obsidian`, …) and vendored/build dirs (`SKIP_DIRS`: `node_modules`,
  `__pycache__`, `dist`, `build`, `target`, `site-packages`, `venv`) are never
  descended, and the walk is capped at `MAX_SCAN_DEPTH` (4; root = depth 0). A
  project's *own* top-level config/metadata never lives inside a vendored tree,
  so skipping those is safe for the intent and keeps a project that lacks the
  files from triggering a full-tree walk. Measured cost over the real `~/dev`
  (37 projects): ~0.15s total.

### Implication for the `track` gate

Because the opt-out gate reads whatever `config.json` `locate` finds, a
**nested** `config.json` with `"track": false` now opts a project out (and
prunes it), exactly as a root-level one does. This extends — and supersedes —
`config-schema.md`'s implicit "config at the project root" assumption. The
gate's semantics are otherwise unchanged: tracked by default; only the JSON
literal `false` opts out; missing/malformed config keeps the project tracked.

### Single walk per candidate

`scan` calls `locate` **once** per candidate and feeds the resulting paths to
both the track gate (`_is_tracked_config`) and `describe`, so a scan never walks
the same tree twice. `describe(path)` and `is_tracked(path)` still work
standalone (they run `locate` themselves) for tests and ad-hoc use.

## Consequences

- Projects that keep their metadata/config below the root are now indexed
  correctly, including their `track` opt-out.
- The scanner is still subprocess-free and side-effect-free; the added cost is a
  small bounded directory walk, mitigated by hidden/vendor pruning and the depth
  cap.
- New knobs (`TARGET_FILES`, `MAX_SCAN_DEPTH`, `SKIP_DIRS`) are class attributes
  on `Scanner`, so the depth/skip policy is tunable in one place.
- Open trade-off: a project that *legitimately* keeps config deeper than
  `MAX_SCAN_DEPTH`, or inside a `SKIP_DIRS` name, is not found. Raise the cap or
  trim the skip set here if that ever bites.
