"""Central DDL for the registry database.

Statements are idempotent (``CREATE ... IF NOT EXISTS``) so ``Db.init`` can run
them on every startup, whether the database is brand new or already populated.
Columns mirror ``app.data_models.watched_dirs.WatchlistItem`` (camelCase attrs
map to snake_case columns).
"""

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS watched_dirs (
        id              TEXT PRIMARY KEY,
        path            TEXT NOT NULL UNIQUE,
        metadata_path   TEXT,
        config_path     TEXT,
        git_path        TEXT,
        project_name    TEXT,
        project_version TEXT,
        branch_name     TEXT,
        branch_version  TEXT,
        cycle           TEXT,
        dir_type        TEXT,
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # a project's path is the natural lookup key from the scanner / clients
    "CREATE INDEX IF NOT EXISTS idx_watched_dirs_project_name ON watched_dirs(project_name)",
]
