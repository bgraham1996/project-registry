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
from collections import deque
from pathlib import Path

from app.data_models.watched_dirs import WatchlistItem

# Sentinel for describe(): distinguishes "argument not passed" (locate it) from
# an explicit None ("searched, not found") passed by scan(), which must not
# trigger a second walk of the same tree.
_UNSET = object()


class Scanner:
    """Index projects under a fixed set of allowed root directories."""

    def __init__(self, repo, roots):
        self.repo = repo
        # Accept str or Path roots; expand ~ so callers can pass config values
        # or literal paths interchangeably.
        self.roots = [Path(root).expanduser() for root in roots]

    def scan(self) -> list[WatchlistItem]:
        """Describe and store every *tracked* candidate. Returns the items stored.

        A candidate whose ``config.json`` sets ``"track": false`` is skipped and,
        if it was indexed on a previous run, pruned — so opting out of tracking
        means "absent from the registry", even after a project flips the flag.
        Everything else is ``upsert``ed (idempotent on ``path``).
        """
        items = []
        for candidate in self.candidates():
            # One walk per candidate: locate here, then reuse the found paths for
            # both the track gate and describe() so the tree isn't walked twice.
            found = self.locate(candidate)
            config_path = found.get("config.json")
            if not self._is_tracked_config(config_path):
                self.repo.delete_by_path(str(candidate))
                continue
            item = self.describe(
                candidate,
                config_path=config_path,
                metadata_path=found.get("metadata.json"),
            )
            self.repo.upsert(item)
            items.append(item)
        return items

    def candidates(self):
        """Yield each root's immediate subdirectories.

        Missing roots are skipped (a configured root need not exist yet), as are
        hidden ``.dotdirs`` — they are tooling/state (``.git``, ``.obsidian``),
        not projects.
        """
        for root in self.roots:
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
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
        :meth:`locate`). Both files' *contents* are parsed — ``metadata.json``
        into the descriptive fields (see :meth:`apply_metadata`) and
        ``config.json`` into the registry-config fields ``tags`` / ``notes`` (see
        :meth:`apply_config`); the ``track`` flag is handled separately in
        :meth:`scan` via :meth:`is_tracked`. A missing/empty/malformed file of
        either kind is harmless — the corresponding fields simply stay ``None``.

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
            item.configpath = str(config_path)
            self.apply_config(item, config_path)

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

        Best-effort and defensive: a missing/unreadable/malformed file, a JSON
        top level that isn't an object, or a key whose value isn't a scalar all
        leave the corresponding field untouched (``None``) rather than raising —
        indexing must never fail because one project ships a bad metadata file.
        Scalar values are coerced to ``str`` to match the TEXT columns. A present
        ``name`` overrides the directory-name default set in :meth:`describe`.
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

    def apply_config(self, item: WatchlistItem, config_path: Path) -> None:
        """Fill registry-config fields on ``item`` from ``config.json``.

        Reads only ``tags`` (a list of scalars -> list of ``str``) and ``notes``
        (a string). The ``track`` flag is *not* applied to the item — it gates
        whether the item is stored at all, handled in :meth:`scan` /
        :meth:`is_tracked`. Same defensive stance as :meth:`apply_metadata`: a
        missing/unreadable/malformed file or a non-object top level leaves the
        fields untouched (``None``) rather than raising, and values of the wrong
        JSON type are skipped. See ``project/design/config-schema.md``.
        """
        data = self.read_json(config_path)
        if not isinstance(data, dict):
            return
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
