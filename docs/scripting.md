# Using the registry from other scripts

Three ways to consume the registry from your own tooling, from most decoupled to
most coupled. For most cases, **shelling out to the CLI** is the right choice.

## 1. Shell out to the CLI (recommended, language-agnostic)

Every read command emits machine-readable output, so any language can drive it.
Data goes to **stdout**; a nonzero exit means failure (e.g. the registry hasn't
been scanned yet).

```bash
# JSON — list, with filters that compose
project-registry list --json
project-registry list --git --cycle active --json

# one project
project-registry show ~/dev/rosmerta --json

# the cycle rollup, and metadata health
project-registry cycles --json
project-registry doctor --json

# CSV for spreadsheets / data tools (tags flattened to a ;-joined cell)
project-registry list --csv > projects.csv
```

Parse it however you like:

```bash
# names of every active git project, via jq
project-registry list --git --cycle active --json | jq -r '.[].projectName'

# fail a CI check if any metadata.json is invalid
test "$(project-registry doctor --json | jq '[.[]|select(.status=="invalid")]|length')" -eq 0
```

```python
import json, subprocess

out = subprocess.run(
    ["project-registry", "list", "--git", "--json"],
    capture_output=True, text=True, check=True,
).stdout
for p in json.loads(out):
    print(p["projectName"], p["branchName"], p["tags"])
```

`list`/`show`/`cycles` read the DB and exit nonzero if it doesn't exist yet;
`doctor`/`config` inspect on-disk files / config and don't need a scanned DB.
Scanning (the only write) is a separate command: `project-registry scan`.

### JSON field names

`list`/`show` objects use: `id`, `path`, `projectName`, `projectVersion`,
`branchName`, `branchVersion`, `cycle`, `dirType`, `tags` (list), `notes`,
`metadataPath`, `configPath`, `gitPath`. `cycles` is a `{cycle: count}` map (the
unset bucket is labelled `"unset"`). `doctor` objects use `project`, `path`,
`status`, `detail`, `missingFields`.

## 2. Read the SQLite views directly

If you'd rather not spawn a process, open the database read-only and read the
shared views (`v_projects`, `v_git_projects`, `v_cycle_counts`). This is exactly
what the bundled Go client (`clients/go/`) does. Open with `mode=ro` and never
write — `scan` owns all mutations. Full schema, columns, and examples (shell,
Python) are in [querying-the-database.md](querying-the-database.md).

## 3. Import the Python package

Install it as a dependency and use the read-only query façade:

```bash
uv add project-registry        # or: uv tool install . for the CLI only
```

```python
import sqlite3
from pathlib import Path
from project_registry.api.registry import Registry

db = Path("~/.config/dev-reg/registry.db").expanduser()
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
con.row_factory = sqlite3.Row

reg = Registry(con)                 # read-only: it cannot write the store
for item in reg.git_projects():     # -> WatchlistItem objects
    print(item.projectName, item.branchName, item.tags)

reg.by_cycle("active")              # list[WatchlistItem]
reg.by_project("rosmerta")          # list[WatchlistItem]
reg.get_by_path("/Users/me/dev/rosmerta")   # WatchlistItem | None
reg.cycle_counts()                  # {cycle_or_None: count}
con.close()
```

`Registry` reads only — writes stay on the scanner — so a script holding one can't
corrupt the registry. Note: the Python API surface isn't a frozen public contract
(see `project/design/packaging-and-cli.md`); if you want the most stable
integration, prefer the CLI (option 1) or the SQL views (option 2).
