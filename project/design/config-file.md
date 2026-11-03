# ADR: User config file (and multiple / nested scan roots)

Status: accepted (2026-11-03)

## Context

Project *discovery* is flat: `Scanner.candidates()` only yields the immediate
children of each `scan_root`, so a project whose root isn't exactly one level
below a scan root (a monorepo subdir, a grouping folder like `archive/`,
`~/work/clientX/projectY`) isn't indexed as its own entry — see the depth
discussion that prompted this. The scanner already *iterates a list* of roots, so
the cheap fix is simply to add the nested parents as additional roots. But
`scan_roots` (and `ignore`) lived only as in-code defaults in
`Configure.default()`, so changing them meant editing Python or passing
`--scan-root` on every run.

## Decision

Add an optional **user config file** and have the runtime load it.

- **Location:** `~/.config/dev-reg/config.json` (the app's config home, next to the
  DB). Anchored to this fixed path — *not* to a `db_dir` override — so loading the
  file can never depend on the file.
- **`Configure.load(path=None)`** seeds `default()` then overlays the file. Keys a
  file may set: `db_dir`, `db_name`, `scan_roots`, `ignore`. A present key
  **replaces** the default (lists are not merged — the same override semantics as
  `--scan-root`).
- **Defensive**, like the rest of the tool: a missing / unreadable / non-JSON /
  non-object file, a wrong-typed value, or (for the list keys) non-string items
  are ignored and the defaults stand. A bad config never breaks a scan.
- The runtime (`Db.__init__`, the CLI's `_default_db_path`, `doctor`) now calls
  `load()` instead of `default()`; `default()` stays as pure in-code defaults and
  is still what tests pin against.
- **`project-registry config`** prints the effective config and the file path
  (and whether it exists), so the feature is discoverable.

This makes "multiple / nested scan roots" a config change, e.g.:

```json
{
  "scan_roots": ["~/dev", "~/dev/archive", "~/work"],
  "ignore": ["archive"]
}
```

Note the compose: listing `~/dev/archive` as its own root indexes the projects
*inside* archive, while `ignore: ["archive"]` still skips `archive` as a candidate
directly under `~/dev` — so you opt in to the contents without double-indexing the
folder itself.

## Consequences

- Deeper nesting is still manual (you name each parent). That's the point of
  choosing the cheapest option; genuine recursive/marker-based discovery remains a
  possible future ADR (it changes the core "immediate children are projects"
  model).
- A new on-disk artifact to document; `config.json` here is the *app* config,
  distinct from a project's own `config.json` (the `track` gate).

## Alternatives considered

- **TOML / YAML** — nicer to hand-edit, but JSON is already the project's idiom
  (`metadata.json` / `config.json`) and needs no dependency. Rejected for now.
- **Env-var overrides** — fine for one-offs, poor for a durable list of roots.
- **Merge (append) list semantics** — surprising next to `--scan-root`'s replace;
  rejected for consistency.
