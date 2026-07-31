"""Tests for the read-only :class:`Registry` query API.

Run against an in-memory database seeded through the real ``WatchlistRepo`` and
the real ``SCHEMA`` (views included), so the tests exercise the actual view
definitions clients depend on — not hand-written SQL that could drift from them.
"""

import sqlite3

import pytest

from app.api.registry import Registry
from app.cache.schema import SCHEMA
from app.cache.watchlist_repo import WatchlistRepo
from app.data_models.watched_dirs import WatchlistItem


def _item(name, *, path=None, dir_type="git", branch="main", cycle=None):
    item = WatchlistItem()
    item.projectName = name
    item.path = path or f"/dev/{name}"
    item.dirType = dir_type
    item.branchName = branch
    item.cycle = cycle
    return item


@pytest.fixture
def registry():
    """A Registry over an in-memory DB seeded with a handful of watched dirs."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    for ddl in SCHEMA:
        connection.execute(ddl)
    connection.commit()

    repo = WatchlistRepo(connection)
    repo.insert(_item("gamma", dir_type="dir", branch=None, cycle="idea"))
    repo.insert(_item("alpha", cycle="active"))
    repo.insert(_item("beta", cycle="active"))
    repo.insert(_item("delta", dir_type="dir", branch=None))  # cycle unset (None)
    return Registry(connection)


def test_projects_returns_all_in_canonical_order(registry):
    names = [item.projectName for item in registry.projects()]
    assert names == ["alpha", "beta", "delta", "gamma"]  # ordered by project_name


def test_projects_reconstructs_full_records(registry):
    alpha = registry.get_by_path("/dev/alpha")
    assert alpha is not None
    # from_row needs every column; the view must not drop any.
    assert alpha.projectName == "alpha"
    assert alpha.dirType == "git"
    assert alpha.branchName == "main"
    assert alpha.cycle == "active"


def test_git_projects_excludes_plain_dirs(registry):
    names = {item.projectName for item in registry.git_projects()}
    assert names == {"alpha", "beta"}  # gamma and delta are dir_type="dir"


def test_by_cycle_filters(registry):
    names = {item.projectName for item in registry.by_cycle("active")}
    assert names == {"alpha", "beta"}
    assert registry.by_cycle("nonexistent") == []


def test_by_project_matches_name(registry):
    items = registry.by_project("alpha")
    assert [i.path for i in items] == ["/dev/alpha"]
    assert registry.by_project("missing") == []


def test_get_by_path_returns_one_or_none(registry):
    assert registry.get_by_path("/dev/beta").projectName == "beta"
    assert registry.get_by_path("/dev/nope") is None


def test_cycle_counts_rolls_up_including_null(registry):
    counts = registry.cycle_counts()
    assert counts == {"active": 2, "idea": 1, None: 1}
