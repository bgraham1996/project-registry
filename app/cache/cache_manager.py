import sqlite3
from pathlib import Path

from app.config_service.cnfg import Configure
from app.cache.schema import MIGRATIONS, SCHEMA


class Db:
    """Owns the connection to the local sqlite registry.

    ``init`` creates the database (and its parent directory) on first use, or
    connects to the existing file if it is already there, then ensures the
    schema is present. sqlite3.connect does the create-or-open; we check
    existence first so callers can tell which happened. Table creation is
    idempotent, so running against an existing database is a no-op.
    """

    def __init__(self):
        self.config = Configure()
        self.config.default()
        self.connection = None

    def path(self) -> Path:
        return self.config.db_path()

    def init(self) -> bool:
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        existed = path.exists()
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.create_tables()
        self._migrate()
        return existed  # True: opened existing, False: created new

    def create_tables(self):
        cur = self.connection.cursor()
        for ddl in SCHEMA:
            cur.execute(ddl)
        self.connection.commit()

    def _migrate(self):
        """Apply additive column migrations, tolerating ones already present.

        SQLite lacks ``ADD COLUMN IF NOT EXISTS``, so a "duplicate column name"
        error just means the column is already there (a fresh DB gets it from the
        CREATE TABLE); any other error is a real problem and re-raised.
        """
        for stmt in MIGRATIONS:
            try:
                self.connection.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        self.connection.commit()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
