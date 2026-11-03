# ADR: `doctor` — a metadata-health report

Status: accepted (2026-11-03)

## Context

Scanning the real `~/dev` showed the indexer working but the registry staying
thin: many projects had no usable `metadata.json`, and — worse — the scanner
**could not tell** a broken file from an absent one. `Scanner.read_json` catches
`json.JSONDecodeError`/`OSError` and returns `None`, so a malformed, empty, or
missing `metadata.json` all collapse to "no data": the fields are silently left
blank and nothing signals that a file needs fixing. Separately, the cycle
dashboard reads mostly `unset` because `ok` files often omit `cycle`/`tags`.

## Decision

Add a **read-only** `project-registry doctor` command that reports per-project
metadata health instead of contents. It reuses the scanner's candidate discovery
(`candidates()` + `locate()`, honouring `ignore` and the vendor/depth rules) but
does **not** touch the registry DB and does **not** apply the `track` gate — it
reports on what is on disk.

`Scanner.diagnose(candidate)` returns a `Diagnosis(name, path, status, detail,
missing_fields)` with a four-way status that makes the previously-collapsed cases
distinct:

- `missing` — no `metadata.json` found under the candidate.
- `empty` — file present but blank/whitespace (a placeholder).
- `invalid` — unreadable, bad JSON, or a non-object top level; `detail` carries
  the parse error.
- `ok` — parses as an object; `missing_fields` lists absent `HEALTH_FIELDS`
  (`cycle`, `tags`) — the enrichment fields that light up the dashboard. Absent
  fields are *reported, not errors*.

Field presence mirrors `apply_metadata`'s coercion rules (`_metadata_has_field`),
so `doctor` and the real scan agree on what counts as "set".

## Consequences

- The command is additive and low-risk: no schema change, no writes, pure
  formatters (`format_doctor_json` / `doctor_summary` / `render_doctor`).
- First run over `~/dev`: 12 ok / 11 missing / 12 empty / 0 invalid — and it
  corrected an earlier ad-hoc survey that had mislabelled empty files as invalid.
- Deliberately *not* done (possible follow-ups): a non-zero exit when `invalid`
  files exist (CI gate), and a `--fix`/scaffold that writes a starter
  `metadata.json`. `doctor` stays a read-only reporter for now.
