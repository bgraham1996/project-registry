# Configuration

`project-registry` works out of the box with sensible defaults. To change what it
scans or where it stores data, drop a JSON file at:

```
~/.config/dev-reg/config.json
```

Run `project-registry config` at any time to see the effective configuration and
whether that file exists yet:

```bash
project-registry config          # human-readable, shows the file path
project-registry config --json   # just the effective config as JSON
```

## Keys

A config file may set any of these keys. Anything you omit keeps its default, and
a key you **do** set **replaces** the default entirely (lists are *not* merged —
the same "override, don't append" rule `--scan-root` already uses).

| Key | Type | Default | Meaning |
|---|---|---|---|
| `scan_roots` | list of strings | `["~/dev"]` | Directories whose **immediate** subdirectories are candidate projects. |
| `ignore` | list of strings | `["archive"]` | Candidate directory **names** to skip (matched case-insensitively). |
| `db_dir` | string | `"~/.config/dev-reg"` | Directory holding the SQLite database. |
| `db_name` | string | `"registry.db"` | SQLite database filename. |

`~` is expanded in every path. Example:

```json
{
  "scan_roots": ["~/dev", "~/dev/archive", "~/work"],
  "ignore": ["archive", "scratch"]
}
```

## Scanning projects nested deeper than one level

Project **discovery is flat**: only the immediate children of each `scan_root` are
treated as projects. A project at `~/dev/work/clientX/projectY` is therefore *not*
found on its own — `~/dev/work` would be treated as a single project instead.

The simplest fix is to **add the nested parent as its own scan root**:

```json
{ "scan_roots": ["~/dev", "~/dev/work"] }
```

Now the projects directly under `~/dev/work` are indexed too.

### Compose `scan_roots` with `ignore`

These two combine usefully. Say `~/dev/archive` is where you park dormant projects
you want kept out of the registry — but occasionally you want to index what's
*inside* it:

```json
{
  "scan_roots": ["~/dev", "~/dev/archive"],
  "ignore": ["archive"]
}
```

- `ignore: ["archive"]` skips `archive` as a candidate directly under `~/dev`
  (so you don't get one bogus "archive" project).
- Listing `~/dev/archive` as its own root indexes the projects **inside** it.

Leave `~/dev/archive` out of `scan_roots` to keep archived projects out entirely —
they'll be soft-removed from the registry on the next scan (see
[querying-the-database.md](querying-the-database.md) on soft-removal).

## The relationship to `--scan-root`

`project-registry scan --scan-root DIR` (repeatable) **overrides** the configured
`scan_roots` for that one run. The config file is the durable default; the flag is
for one-offs. `doctor` honours the same config (and also accepts `--scan-root`).

## Robustness

Loading never fails a scan: a missing file uses the defaults, and a file that is
unreadable, isn't valid JSON, isn't a JSON object, or carries a wrong-typed value
is ignored (the default stands). For `scan_roots`/`ignore`, only string items are
kept. If a change isn't taking effect, run `project-registry config` to confirm
what was actually parsed.
