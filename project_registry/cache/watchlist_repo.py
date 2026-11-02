"""Persistence for ``WatchlistItem`` against the ``watched_dirs`` table.

Keeps SQL out of the model and out of ``Db`` (which just owns the connection).
Construct with a live ``sqlite3.Connection`` that has ``row_factory`` set to
``sqlite3.Row`` (``Db.init`` does this), e.g. ``WatchlistRepo(db.connection)``.
"""

from project_registry.data_models.watched_dirs import WatchlistItem


class WatchlistRepo:
    def __init__(self, connection):
        self.connection = connection

    def insert(self, item: WatchlistItem) -> str:
        """Insert one item; returns its id. Raises on duplicate ``path``."""
        row = item.to_row()
        columns = ", ".join(row.keys())
        placeholders = ", ".join(f":{key}" for key in row)
        self.connection.execute(
            f"INSERT INTO watched_dirs ({columns}) VALUES ({placeholders})", row
        )
        self.connection.commit()
        return row["id"]

    def upsert(self, item: WatchlistItem) -> str:
        """Insert, or update the existing row that shares this ``path``.

        ``path`` is the conflict key, so re-registering the same directory is
        idempotent. On conflict every column except ``id``/``path`` is refreshed
        from the incoming item and ``updated_at`` is bumped; the existing row
        keeps its original ``id`` (and ``created_at``). Returns the stored id,
        which is the *existing* row's id on update — not the incoming item's.
        """
        row = item.to_row()
        columns = ", ".join(row.keys())
        placeholders = ", ".join(f":{key}" for key in row)
        updates = ", ".join(
            f"{col} = excluded.{col}" for col in row if col not in ("id", "path")
        )
        stored = self.connection.execute(
            f"INSERT INTO watched_dirs ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT(path) DO UPDATE SET {updates}, updated_at = datetime('now') "
            f"RETURNING id",
            row,
        ).fetchone()
        self.connection.commit()
        return stored["id"]

    def get(self, item_id) -> WatchlistItem | None:
        row = self.connection.execute(
            "SELECT * FROM watched_dirs WHERE id = ?", (str(item_id),)
        ).fetchone()
        return WatchlistItem.from_row(row) if row else None

    def get_by_path(self, path: str) -> WatchlistItem | None:
        row = self.connection.execute(
            "SELECT * FROM watched_dirs WHERE path = ?", (path,)
        ).fetchone()
        return WatchlistItem.from_row(row) if row else None

    def find_by_project(self, project_name: str) -> list[WatchlistItem]:
        rows = self.connection.execute(
            "SELECT * FROM watched_dirs WHERE project_name = ? ORDER BY path",
            (project_name,),
        ).fetchall()
        return [WatchlistItem.from_row(r) for r in rows]

    def all(self, include_removed: bool = False) -> list[WatchlistItem]:
        """Every watched dir, live ones only by default.

        ``include_removed=True`` also returns soft-removed rows (``removed_at`` set),
        which is how history is inspected; the default matches the client-facing
        views, which never show removed rows.
        """
        where = "" if include_removed else " WHERE removed_at IS NULL"
        rows = self.connection.execute(
            f"SELECT * FROM watched_dirs{where} ORDER BY path"
        ).fetchall()
        return [WatchlistItem.from_row(r) for r in rows]

    def active_paths(self) -> set[str]:
        """The ``path`` of every row not currently soft-removed.

        The scanner uses this to reconcile: any live row whose path it did not see
        on this pass (dir gone, now ignored, or opted out) gets soft-removed.
        """
        rows = self.connection.execute(
            "SELECT path FROM watched_dirs WHERE removed_at IS NULL"
        ).fetchall()
        return {r["path"] for r in rows}

    def mark_removed_by_path(self, path: str) -> bool:
        """Soft-remove the row at ``path``; returns whether a live row was marked.

        Sets ``removed_at`` (and bumps ``updated_at``) only on a currently-live row,
        so re-marking an already-removed row is a no-op and its original
        ``removed_at`` timestamp is preserved. The row is kept as history — the
        client-facing views filter it out.
        """
        cur = self.connection.execute(
            "UPDATE watched_dirs "
            "SET removed_at = datetime('now'), updated_at = datetime('now') "
            "WHERE path = ? AND removed_at IS NULL",
            (path,),
        )
        self.connection.commit()
        return cur.rowcount > 0
