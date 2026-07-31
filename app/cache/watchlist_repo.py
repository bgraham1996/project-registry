"""Persistence for ``WatchlistItem`` against the ``watched_dirs`` table.

Keeps SQL out of the model and out of ``Db`` (which just owns the connection).
Construct with a live ``sqlite3.Connection`` that has ``row_factory`` set to
``sqlite3.Row`` (``Db.init`` does this), e.g. ``WatchlistRepo(db.connection)``.
"""

from app.data_models.watched_dirs import WatchlistItem


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

    def all(self) -> list[WatchlistItem]:
        rows = self.connection.execute(
            "SELECT * FROM watched_dirs ORDER BY path"
        ).fetchall()
        return [WatchlistItem.from_row(r) for r in rows]

    def delete_by_path(self, path: str) -> bool:
        """Remove the row at ``path`` if present; returns whether a row was deleted.

        Used by the scanner to prune a directory that has opted out of tracking
        (``config.json`` ``"track": false``) since it was last indexed, so
        "untracked" means "absent from the registry" even after a flip.
        """
        cur = self.connection.execute(
            "DELETE FROM watched_dirs WHERE path = ?", (path,)
        )
        self.connection.commit()
        return cur.rowcount > 0
