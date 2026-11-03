"""Scan configured root directories and index the projects found beneath them.

The registry is deliberately *not* handed the whole filesystem: it only looks
under the explicit roots it is constructed with (sourced from
``Configure.scan_roots``). For each root, every immediate subdirectory is treated
as a candidate project, described as a :class:`WatchlistItem` from on-disk
signals only, and ``upsert``ed into the registry (idempotent on ``path``, so a
re-scan just refreshes each row rather than duplicating it).

Detection is intentionally cheap and side-effect free — a bounded breadth-first
walk of each candidate (skipping hidden and vendored/build dirs) to find the
highest-level ``metadata.json`` / ``config.json``, plus a single read of
``.git/HEAD``. No subprocesses, no writes to the scanned trees.
"""

import json
from collections import deque, namedtuple
from pathlib import Path

from project_registry.data_models.watched_dirs import WatchlistItem

# Sentinel for describe(): distinguishes "argument not passed" (locate it) from
# an explicit None ("searched, not found") passed by scan(), which must not
# trigger a second walk of the same tree.
_UNSET = object()

# One project's metadata-file health, as reported by `doctor`. ``status`` is one
# of "ok" / "missing" / "empty" / "invalid"; ``detail`` carries the parse error
# (invalid only); ``missing_fields`` lists enrichment fields absent from an
# otherwise-ok file (see Scanner.HEALTH_FIELDS).
Diagnosis = namedtuple("Diagnosis", ["name", "path", "status", "detail", "missing_fields"])


class Scanner:
    """Index projects under a fixed set of allowed root directories."""

    def __init__(self, repo, roots, ignore=None):
        self.repo = repo
        # Accept str or Path roots; expand ~ so callers can pass config values
        # or literal paths interchangeably.
        self.roots = [Path(root).expanduser() for root in roots]
        # Candidate directory names to skip entirely (e.g. "archive" — a holding
        # pen for dormant projects). Matched case-insensitively against each
        # immediate subdir's name. Sourced from Configure.ignore(); an ignored dir
        # that was indexed before is soft-removed by the reconcile pass in scan().
        self.ignore = {name.lower() for name in (ignore or [])}

    def scan(self) -> list[WatchlistItem]:
        """Describe and store every *tracked, present* candidate. Returns those items.

        Each tracked candidate is ``upsert``ed (idempotent on ``path``); an upsert
        also clears ``removed_at``, so a dir that had been soft-removed and then
        reappears is reactivated. Afterwards a reconcile pass **soft-removes** (does
        not delete) any previously-live row under a scanned root that this pass did
        not see — a dir that was deleted/renamed/moved, is now ignored, or opted out
        via ``config.json`` ``"track": false``. Removed rows stay in the table as
        history and are hidden from the client-facing views.
        """
        items = []
        seen: set[str] = set()
        for candidate in self.candidates():
            # One walk per candidate: locate here, then reuse the found paths for
            # both the track gate and describe() so the tree isn't walked twice.
            found = self.locate(candidate)
            config_path = found.get("config.json")
            if not self._is_tracked_config(config_path):
                # Opted out: leave it out of `seen` so the reconcile pass below
                # soft-removes any existing row for it.
                continue
            item = self.describe(
                candidate,
                config_path=config_path,
                metadata_path=found.get("metadata.json"),
            )
            self.repo.upsert(item)
            items.append(item)
            seen.add(str(candidate))
        self._reconcile(seen)
        return items

    def _reconcile(self, seen: set[str]) -> None:
        """Soft-remove live rows under the scanned roots that weren't seen this pass.

        Scoped to the roots actually scanned (a row is only a candidate for removal
        when its parent directory is one of :attr:`roots`), so scanning one root
        never touches rows indexed under a different root.
        """
        roots = {str(root) for root in self.roots}
        for path in self.repo.active_paths():
            if path in seen:
                continue
            if str(Path(path).parent) in roots:
                self.repo.mark_removed_by_path(path)

    def candidates(self):
        """Yield each root's immediate subdirectories.

        Missing roots are skipped (a configured root need not exist yet), as are
        hidden ``.dotdirs`` — they are tooling/state (``.git``, ``.obsidian``),
        not projects — and any directory whose name is in :attr:`ignore`.
        """
        for root in self.roots:
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                if (
                    child.is_dir()
                    and not child.name.startswith(".")
                    and child.name.lower() not in self.ignore
                ):
                    yield child

    # Files the scanner hunts for inside each candidate, and how far it descends.
    # See project/design/file-discovery.md.
    TARGET_FILES = ("config.json", "metadata.json")
    MAX_SCAN_DEPTH = 4  # candidate root is depth 0
    # Never descended when hunting for a project's *top-level* files: hidden dirs
    # are tooling/state, the rest are vendored/build output a project's own
    # config/metadata would never live inside. (Dot-prefixed dirs are also caught
    # by the startswith('.') check below; .venv is listed here for explicitness.)
    SKIP_DIRS = frozenset({
        "node_modules", "__pycache__", "dist", "build",
        "target", "site-packages", "venv", ".venv",
    })

    def locate(self, root: Path) -> dict[str, Path]:
        """Find the shallowest ``config.json`` / ``metadata.json`` under ``root``.

        Breadth-first from the project root, so the *highest-level* occurrence of
        each target file wins; ties at the same depth break on sorted directory
        order (deterministic). The two files are searched **independently** — they
        may live at different depths. Hidden dirs and vendored/build dirs
        (:data:`SKIP_DIRS`) are never descended, and the walk is bounded to
        :data:`MAX_SCAN_DEPTH`, so a project that lacks the files costs a small
        bounded traversal rather than a full walk into ``node_modules`` /
        ``site-packages``. Returns a dict mapping each found filename to its
        ``Path``; a file that is never found is simply absent from the dict.
        """
        remaining = set(self.TARGET_FILES)
        found: dict[str, Path] = {}
        queue = deque([(root, 0)])
        while queue and remaining:
            current, depth = queue.popleft()
            for name in list(remaining):  # snapshot: we mutate `remaining` below
                target = current / name
                if target.is_file():
                    found[name] = target
                    remaining.discard(name)
            if not remaining or depth >= self.MAX_SCAN_DEPTH:
                continue
            try:
                children = sorted(current.iterdir())
            except OSError:
                continue  # unreadable dir: skip it rather than fail the scan
            for child in children:
                if (
                    child.is_dir()
                    and not child.name.startswith(".")
                    and child.name not in self.SKIP_DIRS
                ):
                    queue.append((child, depth + 1))
        return found

    def describe(
        self, path: Path, config_path=_UNSET, metadata_path=_UNSET
    ) -> WatchlistItem:
        """Build a :class:`WatchlistItem` for one project directory.

        Fills what can be read straight off disk: the ``.git`` marker (and, for a
        normal checkout, the current branch), plus the *highest-level*
        ``metadata.json`` / ``config.json`` found beneath ``path`` (see
        :meth:`locate`). All descriptive fields — including ``tags`` / ``notes`` —
        come from ``metadata.json`` (see :meth:`apply_metadata`). ``config.json`` is
        reserved for project-specific *configuration*: its path is recorded, but the
        only key the registry reads from it is the ``track`` opt-out gate, handled
        separately in :meth:`scan` via :meth:`is_tracked` — its contents never
        populate item fields. A missing/empty/malformed file of either kind is
        harmless — the corresponding fields simply stay ``None``.

        ``config_path`` / ``metadata_path`` may be supplied by a caller that has
        already run :meth:`locate` (as :meth:`scan` does, to avoid walking the
        tree twice); each is a :class:`~pathlib.Path`, or ``None`` for "searched,
        not found". Left unset, they are resolved here via :meth:`locate`.
        """
        if config_path is _UNSET or metadata_path is _UNSET:
            found = self.locate(path)
            if config_path is _UNSET:
                config_path = found.get("config.json")
            if metadata_path is _UNSET:
                metadata_path = found.get("metadata.json")

        item = WatchlistItem()
        item.path = str(path)
        item.projectName = path.name

        git_dir = path / ".git"
        if git_dir.exists():
            item.dirType = "git"
            item.gitpath = str(git_dir)
            item.branchName = self.current_branch(git_dir)
        else:
            item.dirType = "dir"

        if metadata_path is not None:
            item.metadatapath = str(metadata_path)
            self.apply_metadata(item, metadata_path)

        if config_path is not None:
            # Recorded for reference only; the track gate is read in scan().
            item.configpath = str(config_path)

        return item

    # metadata.json keys -> WatchlistItem attributes. Only these keys are read;
    # anything else in the file is ignored. See project/design/metadata-schema.md.
    METADATA_FIELDS = {
        "name": "projectName",
        "version": "projectVersion",
        "branchVersion": "branchVersion",
        "cycle": "cycle",
    }

    def apply_metadata(self, item: WatchlistItem, metadata_path: Path) -> None:
        """Fill descriptive fields on ``item`` from ``metadata.json``.

        Reads the scalar fields in :data:`METADATA_FIELDS` plus ``tags`` (a list of
        scalars -> list of ``str``) and ``notes`` (a string). Best-effort and
        defensive: a missing/unreadable/malformed file, a JSON top level that isn't
        an object, or a value of the wrong type all leave the corresponding field
        untouched (``None``) rather than raising — indexing must never fail because
        one project ships a bad metadata file. Scalar values are coerced to ``str``
        to match the TEXT columns. A present ``name`` overrides the directory-name
        default set in :meth:`describe`. See ``project/design/metadata-schema.md``.
        """
        data = self.read_json(metadata_path)
        if not isinstance(data, dict):
            return
        for key, attr in self.METADATA_FIELDS.items():
            value = data.get(key)
            # bool is an int subclass, but a boolean version/cycle is meaningless.
            if isinstance(value, bool):
                continue
            if isinstance(value, (str, int, float)):
                setattr(item, attr, str(value))
        tags = data.get("tags")
        if isinstance(tags, list):
            # keep only scalar tags, coerced to str; bool is an int subclass but
            # a boolean tag is meaningless, so drop it.
            item.tags = [
                str(t)
                for t in tags
                if isinstance(t, (str, int, float)) and not isinstance(t, bool)
            ]
        notes = data.get("notes")
        if isinstance(notes, str):
            item.notes = notes

    def is_tracked(self, path: Path) -> bool:
        """Whether ``path`` should be indexed, per its ``config.json`` ``track`` flag.

        Convenience wrapper: locates the highest-level ``config.json`` under
        ``path`` (see :meth:`locate`) and applies the track gate to it.
        :meth:`scan` instead reuses the config path from its own :meth:`locate`
        call — via :meth:`_is_tracked_config` — to avoid walking the tree twice.
        """
        return self._is_tracked_config(self.locate(path).get("config.json"))

    def _is_tracked_config(self, config_path) -> bool:
        """Apply the track gate to an already-located ``config.json`` path.

        Tracked by default: a directory is only *excluded* when its
        ``config.json`` exists, parses as an object, and sets ``track`` to the
        JSON literal ``false``. No config at all (``config_path is None``), a
        malformed config, or ``track`` absent / set to anything other than boolean
        ``false`` keeps the directory tracked — the registry never silently drops
        a project because of a bad or missing file.
        """
        if config_path is None:
            return True
        data = self.read_json(config_path)
        if not isinstance(data, dict):
            return True
        return data.get("track") is not False

    # Enrichment fields `doctor` nudges you to add: present in metadata.json, they
    # light up the dashboard (cycle grouping, tag display). Absent ones are
    # reported for an otherwise-ok file — they are not errors.
    HEALTH_FIELDS = ("cycle", "tags")

    def diagnose_all(self) -> list[Diagnosis]:
        """Report metadata-file health for every candidate under the roots.

        Read-only: inspects the on-disk ``metadata.json`` of each candidate (same
        discovery + ignore rules as :meth:`scan`) without touching the registry.
        Does not apply the ``track`` gate — it reports on what is on disk.
        """
        return [self.diagnose(candidate) for candidate in self.candidates()]

    def diagnose(self, candidate: Path) -> Diagnosis:
        """Classify one candidate's highest-level ``metadata.json``.

        ``missing`` (no file found), ``empty`` (file present but blank),
        ``invalid`` (unreadable, bad JSON, or a non-object top level — ``detail``
        holds the reason), or ``ok`` (parses as an object; ``missing_fields`` lists
        any :data:`HEALTH_FIELDS` it lacks). This is where "file failed to parse"
        is kept distinct from "no metadata", which :meth:`read_json` collapses.
        """
        name, path = candidate.name, str(candidate)
        metadata_path = self.locate(candidate).get("metadata.json")
        if metadata_path is None:
            return Diagnosis(name, path, "missing", "", [])
        try:
            text = metadata_path.read_text()
        except OSError as exc:
            return Diagnosis(name, path, "invalid", f"unreadable: {exc}", [])
        if not text.strip():
            return Diagnosis(name, path, "empty", "", [])
        try:
            data = json.loads(text)
        except ValueError as exc:
            return Diagnosis(name, path, "invalid", str(exc), [])
        if not isinstance(data, dict):
            return Diagnosis(name, path, "invalid", "top-level JSON is not an object", [])
        missing = [f for f in self.HEALTH_FIELDS if not self._metadata_has_field(data, f)]
        return Diagnosis(name, path, "ok", "", missing)

    @staticmethod
    def _metadata_has_field(data: dict, field: str) -> bool:
        """Whether ``field`` holds a value :meth:`apply_metadata` would actually store.

        Mirrors that method's coercion rules so `doctor` and the real scan agree on
        what counts as "set": a scalar (``bool`` excluded) for most fields, and a
        list with at least one scalar for ``tags``.
        """
        value = data.get(field)
        if field == "tags":
            return isinstance(value, list) and any(
                isinstance(t, (str, int, float)) and not isinstance(t, bool) for t in value
            )
        return isinstance(value, (str, int, float)) and not isinstance(value, bool)

    @staticmethod
    def read_json(path: Path):
        """Parse a JSON file, or return ``None`` if it can't be read or parsed.

        Empty files and invalid JSON both yield ``None`` (never an exception), so
        callers can treat "no usable data" uniformly.
        """
        try:
            text = path.read_text()
        except OSError:
            return None
        try:
            return json.loads(text)
        except ValueError:  # json.JSONDecodeError is a subclass
            return None

    @staticmethod
    def current_branch(git_dir: Path) -> str | None:
        """The checked-out branch, read directly from ``.git/HEAD`` (no subprocess).

        Returns the branch name for a normal checkout, or ``None`` for a detached
        HEAD, or when HEAD is absent/unreadable (e.g. a ``.git`` file pointing at
        a worktree, which we do not follow yet).
        """
        head = git_dir / "HEAD"
        if not head.is_file():
            return None
        try:
            content = head.read_text().strip()
        except OSError:
            return None
        prefix = "ref: refs/heads/"
        if content.startswith(prefix):
            return content[len(prefix):]
        return None  # detached HEAD holds a raw sha, not a branch
