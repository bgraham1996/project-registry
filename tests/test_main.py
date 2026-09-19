"""Tests for the scan entry point's argument handling (:mod:`main`).

Only the pure argument/root-resolution seam is covered here — parsing the
``--scan-root`` flag and choosing between CLI roots and configured roots — so the
tests never build a DB or walk the real ``~/dev`` tree.
"""

from pathlib import Path

from app.config_service.cnfg import Configure
from main import parse_args, resolve_roots


def _config():
    config = Configure()
    config.default()
    return config


def test_no_flag_uses_configured_roots():
    config = _config()
    args = parse_args([])
    assert args.scan_roots is None
    assert resolve_roots(config, args.scan_roots) == config.scan_roots()


def test_single_scan_root_overrides_config():
    config = _config()
    args = parse_args(["--scan-root", "/tmp/projects"])
    assert resolve_roots(config, args.scan_roots) == [Path("/tmp/projects")]


def test_scan_root_is_repeatable():
    args = parse_args(["--scan-root", "/a", "--scan-root", "/b"])
    assert resolve_roots(_config(), args.scan_roots) == [Path("/a"), Path("/b")]


def test_scan_root_expands_home():
    args = parse_args(["--scan-root", "~/work"])
    assert resolve_roots(_config(), args.scan_roots) == [Path.home() / "work"]
