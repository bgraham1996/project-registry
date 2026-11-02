
"""
    this service should simply give a way for other
    components of the tool to get global vars
"""

from pathlib import Path


class Configure:
    def __init__(self):
        self._config = {}

    def default(self):
        self._config = {
            "db_dir": "~/.config/dev-reg",
            "db_name": "registry.db",
            # The scanner only ever looks under these roots — it is never given
            # free rein over the filesystem. Each root is a directory whose
            # immediate children are candidate projects.
            "scan_roots": ["~/dev"],
        }
        return True

    def fig(self):
        return self._config

    def db_path(self) -> Path:
        """Absolute path to the sqlite file, with ~ expanded."""
        cfg = self._config
        return Path(cfg["db_dir"]).expanduser() / cfg["db_name"]

    def scan_roots(self) -> list[Path]:
        """The directories the scanner is allowed to descend into, ~ expanded."""
        return [Path(root).expanduser() for root in self._config.get("scan_roots", [])]
