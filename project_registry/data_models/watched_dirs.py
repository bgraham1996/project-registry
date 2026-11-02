

import json
from uuid import uuid4


class WatchlistItem:
    def __init__(self):
        self.id = uuid4()
        self.path = None
        self.metadatapath = None
        self.configpath = None
        self.gitpath = None

        # basic metadata (from metadata.json):
        self.projectName = None
        self.projectVersion = None
        self.branchName = None
        self.branchVersion = None
        self.cycle = None
        self.dirType = None

        # registry config (from config.json): tags is a list in memory,
        # stored JSON-encoded in the TEXT column; notes is a plain string.
        self.tags = None
        self.notes = None

    def init(self):
        return True

    def to_row(self) -> dict:
        """Model attrs -> ``watched_dirs`` columns (camelCase -> snake_case).

        ``created_at`` / ``updated_at`` are omitted; the DB fills them.
        """
        return {
            "id": str(self.id),
            "path": self.path,
            "metadata_path": self.metadatapath,
            "config_path": self.configpath,
            "git_path": self.gitpath,
            "project_name": self.projectName,
            "project_version": self.projectVersion,
            "branch_name": self.branchName,
            "branch_version": self.branchVersion,
            "cycle": self.cycle,
            "dir_type": self.dirType,
            # tags is a list -> JSON text; None stays NULL (distinct from "[]")
            "tags": json.dumps(self.tags) if self.tags is not None else None,
            "notes": self.notes,
        }

    @classmethod
    def from_row(cls, row) -> "WatchlistItem":
        """Build an item from a ``sqlite3.Row`` (or any dict-like row)."""
        item = cls()
        item.id = row["id"]
        item.path = row["path"]
        item.metadatapath = row["metadata_path"]
        item.configpath = row["config_path"]
        item.gitpath = row["git_path"]
        item.projectName = row["project_name"]
        item.projectVersion = row["project_version"]
        item.branchName = row["branch_name"]
        item.branchVersion = row["branch_version"]
        item.cycle = row["cycle"]
        item.dirType = row["dir_type"]
        tags = row["tags"]
        item.tags = json.loads(tags) if tags is not None else None
        item.notes = row["notes"]
        return item
