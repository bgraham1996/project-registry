"""Tests for the placeholder TUI's pure presentation layer.

Only the pure render helpers and the empty-state branch are exercised — no DB,
no terminal. The live/watch loop is intentionally not tested here.
"""

import re

from rich.console import Console

from project_registry.data_models.watched_dirs import WatchlistItem
from project_registry.ux.tui import render_summary, render_table, render_dashboard, _renderable


def _item(name, dir_type="git", branch="main", path=None, cycle="active", tags=None):
    item = WatchlistItem()
    item.projectName = name
    item.dirType = dir_type
    item.branchName = branch
    item.path = path or f"/tmp/{name}"
    item.cycle = cycle
    item.tags = tags
    return item


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _render_to_text(renderable) -> str:
    """Render any rich renderable to plain text so we can assert on content.

    ANSI styling is stripped (rich's highlighter injects bold codes mid-phrase),
    so assertions can match on the visible text alone.
    """
    console = Console(width=200)
    with console.capture() as capture:
        console.print(renderable)
    return _ANSI.sub("", capture.get())


def test_render_table_has_a_row_per_item():
    items = [_item("alpha"), _item("beta", dir_type="dir", branch=None)]
    table = render_table(items)

    assert table.row_count == 2
    assert [col.header for col in table.columns] == [
        "Project",
        "Type",
        "Branch",
        "Cycle",
        "Tags",
        "Path",
    ]


def test_render_table_shows_tags_and_cycle():
    text = _render_to_text(render_table([_item("alpha", cycle="paused", tags=["cli", "wip"])]))
    assert "paused" in text
    assert "cli, wip" in text


def test_render_summary_shows_each_cycle_with_count():
    text = _render_to_text(render_summary({"active": 3, None: 1}))
    assert "active" in text
    assert "3" in text
    # the None bucket is labelled "unset"
    assert "unset" in text


def test_render_dashboard_includes_title_and_count():
    text = _render_to_text(render_dashboard([_item("only")], {"active": 1}))
    assert "project-registry" in text
    assert "1 watched dir(s)" in text


def test_renderable_falls_back_to_empty_state():
    result = _renderable([])
    assert isinstance(result, str)
    assert "project-registry scan" in result


def test_renderable_returns_dashboard_when_populated():
    result = _renderable([_item("alpha")], {"active": 1})
    assert result.__class__.__name__ == "Group"
