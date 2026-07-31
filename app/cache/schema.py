"""Central DDL for the registry database.

Statements are idempotent (``CREATE ... IF NOT EXISTS``) so ``Db.init`` can run
them on every startup, whether the database is brand new or already populated.
Columns mirror ``app.data_models.watched_dirs.WatchlistItem`` (camelCase attrs
map to snake_case columns).

The read side of the registry — what clients *query* — is expressed as SQL
``VIEW``s here rather than as query strings buried in one client. A view lives in
the database file itself, so the planned Python and Go clients read the registry
through the *same* named contract (``SELECT * FROM v_projects``) instead of each
re-deriving ad-hoc SQL. Python's read facade is ``app.api.registry.Registry``;
see ``project/design/query-api.md`` for the rationale.

Each ``v_*`` row-view selects the full ``watched_dirs`` column set (so any client
can reconstruct a whole record) and only *filters/orders* rows — it never drops
columns. Rollup views (``v_*_counts``) return aggregates, not records.
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

    # --- read contract (shared by every client) -----------------------------

    # Canonical listing: every watched dir, ordered for stable display. Clients
    # read this instead of `SELECT * FROM watched_dirs` so the default ordering
    # is defined in one place. project_name can be NULL, so path is the tie-break.
    """
    CREATE VIEW IF NOT EXISTS v_projects AS
        SELECT * FROM watched_dirs
        ORDER BY project_name IS NULL, project_name, path
    """,
    # Git checkouts only — the common "which of my projects are real repos, and
    # on what branch" question, without each client re-encoding the filter.
    """
    CREATE VIEW IF NOT EXISTS v_git_projects AS
        SELECT * FROM watched_dirs
        WHERE dir_type = 'git'
        ORDER BY project_name IS NULL, project_name, path
    """,
    # Rollup: how many watched dirs fall in each lifecycle cycle (NULL = unset).
    # Aggregate view — returns (cycle, n), not full records.
    """
    CREATE VIEW IF NOT EXISTS v_cycle_counts AS
        SELECT cycle, COUNT(*) AS n
        FROM watched_dirs
        GROUP BY cycle
        ORDER BY n DESC, cycle IS NULL, cycle
    """,
]
