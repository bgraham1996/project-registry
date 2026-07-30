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
        """Describe and ``upsert`` every candidate project. Returns the items stored."""
        items = []
        for candidate in self.candidates():
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
        ``metadata.json`` / ``config.json``. Their *contents* are not parsed yet —
        only their paths are recorded, so an empty or malformed file is harmless.
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

        config = path / "config.json"
        if config.is_file():
            item.configpath = str(config)

        return item

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
