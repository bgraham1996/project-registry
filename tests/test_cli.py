"""Tests for the read-only query CLI (:mod:`project_registry.ux.cli`).

The pure formatters are exercised directly, and the commands are driven through
click's ``CliRunner`` against a real on-disk SQLite file (the CLI opens the DB by
path, ``mode=ro``, so an in-memory DB won't do). The file is seeded through the
real ``SCHEMA`` + ``WatchlistRepo`` so the tests hit the actual views the CLI
depends on. Never touches the real registry.
"""

import csv
import io
import json

import pytest
from click.testing import CliRunner

from project_registry.cache.schema import SCHEMA
from project_registry.cache.watchlist_repo import WatchlistRepo
from project_registry.data_models.watched_dirs import WatchlistItem
from project_registry.scanner.scanner import Diagnosis
from project_registry.ux.cli import (
    cli,
    doctor_summary,
    format_cycle_counts_json,
    format_doctor_json,
    format_items_csv,
    format_items_json,
    render_detail,
)


def _item(name, *, path=None, dir_type="git", branch="main", cycle=None, tags=None, notes=None):
    item = WatchlistItem()
    item.projectName = name
    item.path = path or f"/dev/{name}"
    item.dirType = dir_type
    item.branchName = branch
    item.cycle = cycle
    item.tags = tags
    item.notes = notes
    return item


@pytest.fixture
def db_file(tmp_path):
    """A seeded registry DB on disk; returns its path for the CLI's --db flag."""
    import sqlite3

    path = tmp_path / "registry.db"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    for ddl in SCHEMA:
        connection.execute(ddl)
    connection.commit()

    repo = WatchlistRepo(connection)
    repo.insert(_item("alpha", cycle="active", tags=["cli"], notes="the query client"))
    repo.insert(_item("beta", cycle="active"))
    repo.insert(_item("delta", dir_type="dir", branch=None))  # cycle unset (None)
    repo.insert(_item("gamma", dir_type="dir", branch=None, cycle="idea"))
    connection.commit()
    connection.close()
    return path


def _run(db_file, *args):
    return CliRunner().invoke(cli, ["--db", str(db_file), *args])


# --- pure formatters --------------------------------------------------------

def test_format_items_json_round_trips_tags_as_list():
    payload = json.loads(format_items_json([_item("alpha", tags=["cli", "wip"])]))
    assert payload[0]["projectName"] == "alpha"
    assert payload[0]["tags"] == ["cli", "wip"]


def test_format_items_csv_flattens_tags_and_quotes_notes():
    rows = list(csv.DictReader(io.StringIO(
        format_items_csv([_item("alpha", tags=["cli", "wip"], notes="a, b\nc")])
    )))
    assert len(rows) == 1
    assert rows[0]["projectName"] == "alpha"
    assert rows[0]["tags"] == "cli;wip"          # list -> ;-joined cell
    assert rows[0]["notes"] == "a, b\nc"          # comma/newline survive quoting


def test_format_items_csv_columns_match_json_view():
    # CSV header is driven off the same _item_dict as --json, so the two agree.
    header = next(csv.reader(io.StringIO(format_items_csv([]))))
    payload_keys = list(json.loads(format_items_json([_item("alpha")]))[0].keys())
    assert header == payload_keys


def test_format_items_csv_empty_still_has_header():
    header = next(csv.reader(io.StringIO(format_items_csv([]))))
    assert "projectName" in header


def test_format_cycle_counts_json_labels_none_bucket():
    payload = json.loads(format_cycle_counts_json({"active": 2, None: 1}))
    assert payload == {"active": 2, "unset": 1}


def test_render_detail_shows_fields():
    from rich.console import Console

    console = Console(width=200)
    with console.capture() as cap:
        console.print(render_detail(_item("alpha", cycle="paused", notes="hi")))
    text = cap.get()
    assert "alpha" in text
    assert "paused" in text
    assert "hi" in text


# --- list -------------------------------------------------------------------

def test_list_shows_all(db_file):
    result = _run(db_file, "list")
    assert result.exit_code == 0
    for name in ("alpha", "beta", "delta", "gamma"):
        assert name in result.output


def test_list_git_only(db_file):
    result = _run(db_file, "list", "--git")
    assert result.exit_code == 0
    assert "alpha" in result.output and "beta" in result.output
    assert "delta" not in result.output and "gamma" not in result.output


def test_list_cycle_filter(db_file):
    result = _run(db_file, "list", "--cycle", "active")
    assert "alpha" in result.output and "beta" in result.output
    assert "delta" not in result.output


def test_list_git_and_cycle_compose(db_file):
    # gamma is cycle=idea but a plain dir; --git should exclude it even though
    # --cycle would not be applied to it either — the two filters compose.
    result = _run(db_file, "list", "--git", "--cycle", "active")
    assert "alpha" in result.output and "beta" in result.output


def test_list_json_is_valid_and_filtered(db_file):
    result = _run(db_file, "list", "--git", "--json")
    payload = json.loads(result.output)
    assert {p["projectName"] for p in payload} == {"alpha", "beta"}


def test_list_csv_is_valid_and_filtered(db_file):
    result = _run(db_file, "list", "--git", "--csv")
    assert result.exit_code == 0
    rows = list(csv.DictReader(io.StringIO(result.output)))
    assert {r["projectName"] for r in rows} == {"alpha", "beta"}
    # tags flattened for the row that has them
    alpha = next(r for r in rows if r["projectName"] == "alpha")
    assert alpha["tags"] == "cli"


def test_list_json_and_csv_are_mutually_exclusive(db_file):
    result = _run(db_file, "list", "--json", "--csv")
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_list_no_match_is_friendly(db_file):
    result = _run(db_file, "list", "--project", "nope")
    assert result.exit_code == 0
    assert "No matching" in result.output


# --- show -------------------------------------------------------------------

def test_show_found(db_file):
    result = _run(db_file, "show", "/dev/alpha")
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "the query client" in result.output  # notes surfaced


def test_show_json(db_file):
    result = _run(db_file, "show", "/dev/alpha", "--json")
    payload = json.loads(result.output)
    assert payload["projectName"] == "alpha"
    assert payload["cycle"] == "active"


def test_show_missing_errors(db_file):
    result = _run(db_file, "show", "/dev/nope")
    assert result.exit_code != 0
    assert "No watched dir" in result.output


# --- cycles -----------------------------------------------------------------

def test_cycles_json_rolls_up(db_file):
    result = _run(db_file, "cycles", "--json")
    payload = json.loads(result.output)
    assert payload == {"active": 2, "idea": 1, "unset": 1}


# --- missing DB -------------------------------------------------------------

def test_missing_db_is_friendly(tmp_path):
    result = _run(tmp_path / "does-not-exist.db", "list")
    assert result.exit_code != 0
    assert "run `project-registry scan`" in result.output


# --- doctor (pure formatters) -----------------------------------------------

def _diag(name, status, detail="", missing=()):
    return Diagnosis(name, f"/dev/{name}", status, detail, list(missing))


def test_doctor_summary_counts_and_omits_zero_buckets():
    diagnoses = [
        _diag("a", "ok"),
        _diag("b", "ok"),
        _diag("c", "invalid", detail="boom"),
        _diag("d", "missing"),
    ]
    summary = doctor_summary(diagnoses)
    assert "2 ok" in summary
    assert "1 invalid" in summary
    assert "1 missing" in summary
    assert "empty" not in summary  # zero bucket omitted


def test_format_doctor_json_shape():
    diagnoses = [
        _diag("ok1", "ok", missing=["cycle"]),
        _diag("bad", "invalid", detail="Expecting value"),
    ]
    payload = json.loads(format_doctor_json(diagnoses))
    assert payload[0] == {
        "project": "ok1",
        "path": "/dev/ok1",
        "status": "ok",
        "detail": "",
        "missingFields": ["cycle"],
    }
    assert payload[1]["status"] == "invalid"
    assert payload[1]["detail"] == "Expecting value"


# --- doctor (command, against a real on-disk tree) --------------------------

def test_doctor_command_reports_per_project(tmp_path):
    # a tree of candidate projects with varied metadata health
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "metadata.json").write_text(
        json.dumps({"cycle": "active", "tags": ["x"]})
    )
    (tmp_path / "thin").mkdir()
    (tmp_path / "thin" / "metadata.json").write_text(json.dumps({"name": "Thin"}))
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "metadata.json").write_text("{ not json ]")
    (tmp_path / "none").mkdir()
    (tmp_path / "archive").mkdir()  # ignored by default config

    runner = CliRunner()
    result = runner.invoke(cli, ["doctor", "--scan-root", str(tmp_path), "--json"])
    assert result.exit_code == 0, result.output

    by_name = {d["project"]: d for d in json.loads(result.output)}
    assert set(by_name) == {"good", "thin", "broken", "none"}  # archive excluded
    assert by_name["good"]["status"] == "ok" and by_name["good"]["missingFields"] == []
    assert by_name["thin"]["status"] == "ok"
    assert by_name["thin"]["missingFields"] == ["cycle", "tags"]
    assert by_name["broken"]["status"] == "invalid" and by_name["broken"]["detail"]
    assert by_name["none"]["status"] == "missing"


def test_doctor_command_table_renders(tmp_path):
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "metadata.json").write_text("{ bad ]")

    result = CliRunner().invoke(cli, ["doctor", "--scan-root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "broken" in result.output
    assert "invalid" in result.output


# --- config -----------------------------------------------------------------

def test_config_json_emits_effective_config():
    result = CliRunner().invoke(cli, ["config", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    # shape, not machine-specific values (a real user config file may exist)
    assert set(payload) >= {"db_dir", "db_name", "scan_roots", "ignore"}
    assert isinstance(payload["scan_roots"], list)


def test_config_default_view_shows_file_path():
    result = CliRunner().invoke(cli, ["config"])
    assert result.exit_code == 0, result.output
    assert "config.json" in result.output
    assert "effective config" in result.output
