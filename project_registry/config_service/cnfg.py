
"""
    this service should simply give a way for other
    components of the tool to get global vars
"""

import json
from pathlib import Path

# The app's config home. The SQLite DB and the optional user config file both
# live here by default; the config-file location is anchored to this fixed path
# (not to a `db_dir` override) so loading the file can never depend on the file.
DEFAULT_DB_DIR = "~/.config/dev-reg"
CONFIG_FILENAME = "config.json"

# Keys a user config file may override, and the type each must be to be accepted
# (a value of the wrong type is ignored rather than allowed to break a scan).
_OVERRIDABLE = {
    "db_dir": str,
    "db_name": str,
    "scan_roots": list,
    "ignore": list,
}


class Configure:
    def __init__(self):
        self._config = {}

    def default(self):
        self._config = {
            "db_dir": DEFAULT_DB_DIR,
            "db_name": "registry.db",
            # The scanner only ever looks under these roots — it is never given
            # free rein over the filesystem. Each root is a directory whose
            # immediate children are candidate projects. Add nested parents here
            # (e.g. "~/dev/archive", "~/work") to index projects that don't sit
            # exactly one level below an existing root.
            "scan_roots": ["~/dev"],
            # Candidate directory names the scanner skips entirely (matched
            # case-insensitively against each root's immediate children). "archive"
            # is where dormant projects are parked — kept on disk but not actively
            # tracked; an ignored dir already in the registry is soft-removed.
            "ignore": ["archive"],
        }
        return True

    def load(self, path=None):
        """Seed defaults, then overlay a user config file if one is present.

        The file (JSON, at :meth:`config_file_path` unless ``path`` is given) may
        set any of the keys in :data:`_OVERRIDABLE`; a present key **replaces** the
        default (lists are not merged — the same override semantics as
        ``--scan-root``). Defensive like the rest of the tool: a missing,
        unreadable, non-JSON, non-object, or wrong-typed file/value is ignored and
        the defaults stand, so a bad config never breaks a scan. For ``scan_roots``
        / ``ignore`` only string items are kept.
        """
        self.default()
        target = Path(path).expanduser() if path else self.config_file_path()
        data = self._read_file(target)
        if not isinstance(data, dict):
            return True
        for key, expected_type in _OVERRIDABLE.items():
            if key not in data or not isinstance(data[key], expected_type):
                continue
            value = data[key]
            if expected_type is list:
                value = [item for item in value if isinstance(item, str)]
            self._config[key] = value
        return True

    def config_file_path(self) -> Path:
        """Where the optional user config file lives (``~`` expanded)."""
        return Path(DEFAULT_DB_DIR).expanduser() / CONFIG_FILENAME

    @staticmethod
    def _read_file(path: Path):
        """Parse the config file, or ``None`` if it can't be read or parsed."""
        try:
            text = Path(path).read_text()
        except OSError:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None

    def fig(self):
        return self._config

    def db_path(self) -> Path:
        """Absolute path to the sqlite file, with ~ expanded."""
        cfg = self._config
        return Path(cfg["db_dir"]).expanduser() / cfg["db_name"]

    def scan_roots(self) -> list[Path]:
        """The directories the scanner is allowed to descend into, ~ expanded."""
        return [Path(root).expanduser() for root in self._config.get("scan_roots", [])]

    def ignore(self) -> list[str]:
        """Candidate directory names the scanner skips (e.g. ``["archive"]``)."""
        return list(self._config.get("ignore", []))
