"""Central DDL for the registry database.

Split into three ordered phases so a fresh DB and an older DB converge, and so
views can safely reference columns added by migrations:

- ``TABLES`` — ``CREATE TABLE/INDEX ... IF NOT EXISTS`` (idempotent).
- ``MIGRATIONS`` — additive ``ALTER TABLE ... ADD COLUMN`` for DBs created before a
  column existed (a fresh DB gets the column from ``CREATE TABLE`` instead).
- ``VIEWS`` — the read contract, each ``DROP VIEW IF EXISTS`` + ``CREATE VIEW`` so a
  view *body* change actually takes effect on an existing DB (``CREATE VIEW IF NOT
  EXISTS`` alone would silently keep the stale definition). Applied **after**
  migrations, so a view may reference a migrated-in column (e.g. ``removed_at``).

``Db.init`` runs them in that order: ``TABLES`` → ``MIGRATIONS`` → ``VIEWS``.
``SCHEMA = TABLES + VIEWS`` is exported as a convenience for consumers that build a
*fresh* database in one pass (the test fixtures), where every column already
exists from ``CREATE TABLE`` and no migration is needed.

Columns mirror ``project_registry.data_models.watched_dirs.WatchlistItem``
(camelCase attrs map to snake_case columns).

The read side of the registry — what clients *query* — is expressed as SQL
``VIEW``s here rather than as query strings buried in one client, so the Python
and Go clients read through the *same* named contract (``SELECT * FROM
v_projects``). Each ``v_*`` row-view selects the full column set and only
filters/orders rows; rollup views (``v_*_counts``) return aggregates. Every view
excludes soft-removed rows (``removed_at IS NOT NULL``) so clients see only live
projects by default; the removed rows stay in the table as history.
"""

TABLES = [
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
        tags            TEXT,
        notes           TEXT,
        removed_at      TEXT,
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # a project's path is the natural lookup key from the scanner / clients
    "CREATE INDEX IF NOT EXISTS idx_watched_dirs_project_name ON watched_dirs(project_name)",
]

# Additive migrations for databases created before a column existed. SQLite has no
# `ADD COLUMN IF NOT EXISTS`, so each is applied defensively (a "duplicate column
# name" error just means it already ran — see ``Db._migrate``). Only additive
# column changes belong here; view-body changes are handled by ``VIEWS`` recreating
# themselves on every ``init``.
MIGRATIONS = [
    "ALTER TABLE watched_dirs ADD COLUMN tags TEXT",
    "ALTER TABLE watched_dirs ADD COLUMN notes TEXT",
    "ALTER TABLE watched_dirs ADD COLUMN removed_at TEXT",
]

# --- read contract (shared by every client) --------------------------------
# Recreated from source on every init (DROP + CREATE), so editing a body here is
# enough to roll the change out to existing databases. All three exclude
# soft-removed rows: `removed_at IS NULL` means "currently present / tracked".
VIEWS = [
    "DROP VIEW IF EXISTS v_projects",
    # Canonical listing: every live watched dir, ordered for stable display.
    # project_name can be NULL, so path is the tie-break.
    """
    CREATE VIEW v_projects AS
        SELECT * FROM watched_dirs
        WHERE removed_at IS NULL
        ORDER BY project_name IS NULL, project_name, path
    """,
    "DROP VIEW IF EXISTS v_git_projects",
    # Git checkouts only — "which of my projects are real repos, and on what branch".
    """
    CREATE VIEW v_git_projects AS
        SELECT * FROM watched_dirs
        WHERE dir_type = 'git' AND removed_at IS NULL
        ORDER BY project_name IS NULL, project_name, path
    """,
    "DROP VIEW IF EXISTS v_cycle_counts",
    # Rollup: how many live watched dirs fall in each lifecycle cycle (NULL = unset).
    """
    CREATE VIEW v_cycle_counts AS
        SELECT cycle, COUNT(*) AS n
        FROM watched_dirs
        WHERE removed_at IS NULL
        GROUP BY cycle
        ORDER BY n DESC, cycle IS NULL, cycle
    """,
]

# Convenience for consumers building a fresh DB in a single pass (test fixtures):
# every column exists from CREATE TABLE, so views can be created right after tables
# with no migration step in between.
SCHEMA = TABLES + VIEWS
