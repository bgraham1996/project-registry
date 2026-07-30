"""Tests for the scanner's on-disk detection and its wiring to the repo.

These run entirely against a temp directory and an in-memory sqlite database, so
they never read the real ``~/dev`` tree or write the real registry at
``~/.config/dev-reg/registry.db``.
"""

import json
import sqlite3

import pytest

from app.cache.schema import SCHEMA
from app.cache.watchlist_repo import WatchlistRepo
from app.scanner.scanner import Scanner


@pytest.fixture
def repo():
    """A WatchlistRepo backed by a throwaway in-memory database."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    for ddl in SCHEMA:
        connection.execute(ddl)
    connection.commit()
    return WatchlistRepo(connection)


def make_git_project(root, name, branch="main"):
    """A directory that looks like a git checkout on ``branch``."""
    project = root / name
    (project / ".git").mkdir(parents=True)
    (project / ".git" / "HEAD").write_text(f"ref: refs/heads/{branch}\n")
    return project


def test_describe_git_project_reads_branch_and_markers(tmp_path):
    project = make_git_project(tmp_path, "alpha", branch="feature/x")
    (project / "metadata.json").write_text("")  # empty is fine; only presence matters
    (project / "config.json").write_text("")

    item = Scanner(repo=None, roots=[]).describe(project)

    assert item.projectName == "alpha"
    assert item.dirType == "git"
    assert item.gitpath == str(project / ".git")
    assert item.branchName == "feature/x"
    assert item.metadatapath == str(project / "metadata.json")
    assert item.configpath == str(project / "config.json")


def test_describe_parses_metadata_fields(tmp_path):
    project = make_git_project(tmp_path, "alpha", branch="main")
    (project / "metadata.json").write_text(
        json.dumps({"version": "1.2.3", "branchVersion": "1.2.3-dev", "cycle": "active"})
    )

    item = Scanner(repo=None, roots=[]).describe(project)

    assert item.projectVersion == "1.2.3"
    assert item.branchVersion == "1.2.3-dev"
    assert item.cycle == "active"


def test_metadata_name_overrides_directory_name(tmp_path):
    project = tmp_path / "on-disk-name"
    project.mkdir()
    (project / "metadata.json").write_text(json.dumps({"name": "Canonical Name"}))

    item = Scanner(repo=None, roots=[]).describe(project)

    assert item.projectName == "Canonical Name"


def test_metadata_absent_name_keeps_directory_name(tmp_path):
    project = tmp_path / "delta"
    project.mkdir()
    (project / "metadata.json").write_text(json.dumps({"version": "0.1.0"}))

    item = Scanner(repo=None, roots=[]).describe(project)

    assert item.projectName == "delta"  # dir name preserved when metadata omits it
    assert item.projectVersion == "0.1.0"


def test_scalar_metadata_values_are_coerced_to_str(tmp_path):
    project = tmp_path / "epsilon"
    project.mkdir()
    (project / "metadata.json").write_text(json.dumps({"version": 2, "cycle": 3}))

    item = Scanner(repo=None, roots=[]).describe(project)

    assert item.projectVersion == "2"
    assert item.cycle == "3"


def test_malformed_metadata_is_ignored(tmp_path):
    project = tmp_path / "zeta"
    project.mkdir()
    (project / "metadata.json").write_text("{ not valid json ]")

    item = Scanner(repo=None, roots=[]).describe(project)

    # Path still recorded; descriptive fields left untouched, no exception raised.
    assert item.metadatapath == str(project / "metadata.json")
    assert item.projectVersion is None
    assert item.cycle is None


def test_non_object_and_nonscalar_metadata_are_ignored(tmp_path):
    project = tmp_path / "eta"
    project.mkdir()
    # Top level is a list (not an object); and a nested-object value for a field.
    (project / "metadata.json").write_text(json.dumps(["not", "an", "object"]))

    item = Scanner(repo=None, roots=[]).describe(project)

    assert item.projectVersion is None
    assert item.cycle is None

    (project / "metadata.json").write_text(json.dumps({"version": {"nested": "obj"}}))
    item = Scanner(repo=None, roots=[]).describe(project)
    assert item.projectVersion is None  # non-scalar value skipped


def test_config_json_recorded_but_not_parsed(tmp_path):
    project = tmp_path / "theta"
    project.mkdir()
    # config.json carries fields that look descriptive; they must NOT be applied.
    (project / "config.json").write_text(json.dumps({"version": "9.9.9", "cycle": "prod"}))

    item = Scanner(repo=None, roots=[]).describe(project)

    assert item.configpath == str(project / "config.json")
    assert item.projectVersion is None  # config.json is reserved, not parsed
    assert item.cycle is None


def test_describe_plain_dir_has_no_git_fields(tmp_path):
    project = tmp_path / "beta"
    project.mkdir()

    item = Scanner(repo=None, roots=[]).describe(project)

    assert item.dirType == "dir"
    assert item.gitpath is None
    assert item.branchName is None
    assert item.metadatapath is None


def test_detached_head_yields_no_branch(tmp_path):
    project = tmp_path / "gamma"
    (project / ".git").mkdir(parents=True)
    (project / ".git" / "HEAD").write_text("a1b2c3d4" * 5 + "\n")  # raw sha, detached

    item = Scanner(repo=None, roots=[]).describe(project)

    assert item.dirType == "git"
    assert item.branchName is None


def test_candidates_skips_dotdirs_and_files(tmp_path):
    make_git_project(tmp_path, "one")
    (tmp_path / "two").mkdir()
    (tmp_path / ".hidden").mkdir()  # tooling/state, not a project
    (tmp_path / "loose.txt").write_text("not a project")

    names = {p.name for p in Scanner(repo=None, roots=[tmp_path]).candidates()}

    assert names == {"one", "two"}


def test_missing_root_is_skipped(tmp_path):
    scanner = Scanner(repo=None, roots=[tmp_path / "does-not-exist"])
    assert list(scanner.candidates()) == []


def test_scan_upserts_all_candidates_and_is_idempotent(repo, tmp_path):
    make_git_project(tmp_path, "one")
    (tmp_path / "two").mkdir()

    scanner = Scanner(repo=repo, roots=[tmp_path])

    first = scanner.scan()
    assert {item.projectName for item in first} == {"one", "two"}
    assert len(repo.all()) == 2

    scanner.scan()  # re-scan must refresh in place, not duplicate
    assert len(repo.all()) == 2
