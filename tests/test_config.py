"""Tests for ``Configure`` defaults and user-config-file loading.

All file-loading tests pass an explicit ``path`` to :meth:`Configure.load` so they
never read the real ``~/.config/dev-reg/config.json``.
"""

import json
from pathlib import Path

from project_registry.config_service.cnfg import Configure


def _write(path, data):
    path.write_text(json.dumps(data))
    return path


def test_load_without_a_file_equals_defaults(tmp_path):
    cfg = Configure()
    cfg.load(path=tmp_path / "nope.json")  # does not exist
    default = Configure()
    default.default()
    assert cfg.fig() == default.fig()


def test_load_overrides_scan_roots_and_ignore(tmp_path):
    f = _write(tmp_path / "config.json", {"scan_roots": ["~/dev", "~/work"], "ignore": ["archive", "scratch"]})
    cfg = Configure()
    cfg.load(path=f)
    assert cfg.scan_roots() == [Path.home() / "dev", Path.home() / "work"]  # ~ expanded
    assert cfg.ignore() == ["archive", "scratch"]


def test_load_replaces_lists_rather_than_merging(tmp_path):
    # a file scan_roots replaces the default entirely (same semantics as --scan-root)
    f = _write(tmp_path / "config.json", {"scan_roots": ["~/only"]})
    cfg = Configure()
    cfg.load(path=f)
    assert cfg.scan_roots() == [Path.home() / "only"]


def test_load_partial_file_keeps_other_defaults(tmp_path):
    f = _write(tmp_path / "config.json", {"scan_roots": ["~/x"]})
    cfg = Configure()
    cfg.load(path=f)
    assert cfg.ignore() == ["archive"]  # untouched default
    assert cfg.fig()["db_name"] == "registry.db"


def test_load_honors_db_dir_and_name(tmp_path):
    f = _write(tmp_path / "config.json", {"db_dir": "~/somewhere", "db_name": "reg.sqlite"})
    cfg = Configure()
    cfg.load(path=f)
    assert cfg.db_path() == Path.home() / "somewhere" / "reg.sqlite"


def test_malformed_file_falls_back_to_defaults(tmp_path):
    bad = tmp_path / "config.json"
    bad.write_text("{ not json ]")
    cfg = Configure()
    cfg.load(path=bad)
    assert cfg.scan_roots() == [Path.home() / "dev"]
    assert cfg.ignore() == ["archive"]


def test_non_object_top_level_is_ignored(tmp_path):
    f = _write(tmp_path / "config.json", ["not", "an", "object"])
    cfg = Configure()
    cfg.load(path=f)
    assert cfg.ignore() == ["archive"]


def test_wrong_typed_values_are_ignored(tmp_path):
    # scan_roots as a string (not a list) is rejected; mixed ignore keeps only strs
    f = _write(tmp_path / "config.json", {"scan_roots": "~/dev", "ignore": ["ok", 7, None, "fine"]})
    cfg = Configure()
    cfg.load(path=f)
    assert cfg.scan_roots() == [Path.home() / "dev"]  # default kept
    assert cfg.ignore() == ["ok", "fine"]  # non-strings dropped


def test_config_file_path_is_under_the_config_home():
    path = Configure().config_file_path()
    assert path.name == "config.json"
    assert path.parent == Path("~/.config/dev-reg").expanduser()
