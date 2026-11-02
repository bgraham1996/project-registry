"""Read-only query API over the registry database.

This is the *read* half of the README's "local API-like service": a single,
predefined query surface that clients hit instead of writing their own SQL. It
is deliberately read-only — populating the registry is the scanner's job
(``WatchlistRepo`` owns the writes). Keeping reads and writes on separate objects
means a client (the TUI, a future HTTP layer) can hold a ``Registry`` without any
ability to mutate the store.

The queries themselves live as ``v_*`` SQL views in ``project_registry.cache.schema`` so the
planned Go client can read the exact same contract from the same database file;
each method here is a thin, typed wrapper that returns domain objects rather than
raw rows. See ``project/design/query-api.md``.

Construct with a live ``sqlite3.Connection`` whose ``row_factory`` is
``sqlite3.Row`` (``Db.init`` sets this), e.g. ``Registry(db.connection)``.
"""

from project_registry.data_models.watched_dirs import WatchlistItem


class Registry:
    """Predefined read queries over the ``watched_dirs`` registry."""

    def __init__(self, connection):
        self.connection = connection

    # --- record listings (return WatchlistItems) ----------------------------

    def projects(self) -> list[WatchlistItem]:
        """Every watched dir, in the registry's canonical display order."""
        rows = self.connection.execute("SELECT * FROM v_projects").fetchall()
        return [WatchlistItem.from_row(r) for r in rows]

    def git_projects(self) -> list[WatchlistItem]:
        """Only the watched dirs that are git checkouts."""
        rows = self.connection.execute("SELECT * FROM v_git_projects").fetchall()
        return [WatchlistItem.from_row(r) for r in rows]

    def by_cycle(self, cycle: str) -> list[WatchlistItem]:
        """Watched dirs whose lifecycle ``cycle`` matches (e.g. ``"active"``)."""
        rows = self.connection.execute(
            "SELECT * FROM v_projects WHERE cycle = ?", (cycle,)
        ).fetchall()
        return [WatchlistItem.from_row(r) for r in rows]

    def by_project(self, project_name: str) -> list[WatchlistItem]:
        """Watched dirs whose ``project_name`` matches (may share a name across paths)."""
        rows = self.connection.execute(
            "SELECT * FROM v_projects WHERE project_name = ?", (project_name,)
        ).fetchall()
        return [WatchlistItem.from_row(r) for r in rows]

    def get_by_path(self, path: str) -> WatchlistItem | None:
        """The single watched dir at ``path`` (its unique key), or ``None``."""
        row = self.connection.execute(
            "SELECT * FROM v_projects WHERE path = ?", (path,)
        ).fetchone()
        return WatchlistItem.from_row(row) if row else None

    # --- rollups (return aggregates, not records) ---------------------------

    def cycle_counts(self) -> dict[str | None, int]:
        """How many watched dirs sit in each lifecycle cycle (``None`` = unset)."""
        rows = self.connection.execute("SELECT * FROM v_cycle_counts").fetchall()
        return {row["cycle"]: row["n"] for row in rows}
