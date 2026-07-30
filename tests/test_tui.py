"""Tests for the placeholder TUI's pure presentation layer.

Only ``render_table`` and the empty-state helper are exercised — no DB, no
terminal. The live/watch loop is intentionally not tested here.
"""

from app.data_models.watched_dirs import WatchlistItem
from app.ux.tui import render_table, _renderable


def _item(name, dir_type="git", branch="main", path=None):
    item = WatchlistItem()
    item.projectName = name
    item.dirType = dir_type
    item.branchName = branch
    item.path = path or f"/tmp/{name}"
    return item


def test_render_table_has_a_row_per_item():
    items = [_item("alpha"), _item("beta", dir_type="dir", branch=None)]
    table = render_table(items)

    assert table.row_count == 2
    assert [col.header for col in table.columns] == ["Project", "Type", "Branch", "Path"]


def test_render_table_title_counts_items():
    table = render_table([_item("only")])
    assert "1 watched dir(s)" in table.title


def test_renderable_falls_back_to_empty_state():
    result = _renderable([])
    assert isinstance(result, str)
    assert "uv run main.py" in result


def test_renderable_returns_table_when_populated():
    result = _renderable([_item("alpha")])
    assert result.__class__.__name__ == "Table"
