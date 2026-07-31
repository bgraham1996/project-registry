"""Scan configured root directories and index the projects found beneath them.

The registry is deliberately *not* handed the whole filesystem: it only looks
under the explicit roots it is constructed with (sourced from
``Configure.scan_roots``). For each root, every immediate subdirectory is treated
as a candidate project, described as a :class:`WatchlistItem` from on-disk
signals only, and ``upsert``ed into the registry (idempotent on ``path``, so a
re-scan just refreshes each row rather than duplicating it).

Detection is intentionally cheap and side-effect free — directory ``stat`` calls
and a single read of ``.git/HEAD``. No subprocesses, no writes to the scanned
trees.
"""

import json
from pathlib import Path

from app.data_models.watched_dirs import WatchlistItem


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
            if not self.is_tracked(candidate):
                self.repo.delete_by_path(str(candidate))
                continue
            item = self.describe(candidate)
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

    def describe(self, path: Path) -> WatchlistItem:
        """Build a :class:`WatchlistItem` for one project directory.

        Fills what can be read straight off disk: the ``.git`` marker (and, for a
        normal checkout, the current branch), and the presence of
        ``metadata.json`` / ``config.json``. Both files' *contents* are parsed —
        ``metadata.json`` into the descriptive fields (see :meth:`apply_metadata`)
        and ``config.json`` into the registry-config fields ``tags`` / ``notes``
        (see :meth:`apply_config`); the ``track`` flag is handled separately in
        :meth:`scan` via :meth:`is_tracked`. A missing/empty/malformed file of
        either kind is harmless — the corresponding fields simply stay ``None``.
        """
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

        metadata = path / "metadata.json"
        if metadata.is_file():
            item.metadatapath = str(metadata)
            self.apply_metadata(item, metadata)

        config = path / "config.json"
        if config.is_file():
            item.configpath = str(config)
            self.apply_config(item, config)

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

        Tracked by default: a directory is only *excluded* when its
        ``config.json`` exists, parses as an object, and sets ``track`` to the
        JSON literal ``false``. A missing/malformed config, or ``track`` absent or
        set to anything other than boolean ``false``, keeps the directory tracked
        — the registry never silently drops a project because of a bad file.
        """
        config = path / "config.json"
        if not config.is_file():
            return True
        data = self.read_json(config)
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
