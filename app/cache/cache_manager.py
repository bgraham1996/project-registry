import sqlite3
from pathlib import Path

from app.config_service.cnfg import Configure
from app.cache.schema import SCHEMA


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
        return existed  # True: opened existing, False: created new

    def create_tables(self):
        cur = self.connection.cursor()
        for ddl in SCHEMA:
            cur.execute(ddl)
        self.connection.commit()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
