"""Tests for the CLI writing to a closed pipe (no network access)."""

import os
import subprocess
import sys

import pytest

from uchr import database, db
from uchr.uchr import EXIT_BROKEN_PIPE

UCD_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ucd xmlns="http://www.unicode.org/ns/2003/ucd/1.0">
  <repertoire>
    <char cp="1F47A" na="JAPANESE GOBLIN" blk="Misc_Pictographs"/>
    <char cp="1F47B" na="GHOST" blk="Misc_Pictographs"/>
  </repertoire>
</ucd>
"""

# Run the CLI against the database path given as the first argument.
CHILD = (
    "import sys; from uchr import db; "
    "db.unicode_sqlite3_database_path = sys.argv.pop(1); "
    "from uchr.uchr import main; sys.exit(main())"
)


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "uchr" / "unicode.db"
    monkeypatch.setattr(db, "unicode_sqlite3_database_path", str(path))
    return path


@pytest.fixture
def stored_db(db_path, monkeypatch):
    monkeypatch.setattr(database, "download_ucd", lambda url: (UCD_XML, url))
    monkeypatch.setattr(database, "download_emoji_pair", lambda v: (None, None))
    monkeypatch.setattr(database, "resolve_latest_release", lambda: "48.2")
    monkeypatch.setattr(database, "download_annotations", lambda r: b"<ldml/>")
    assert database.update_database(version="17.0.0") == 0
    return db_path


def run_with_closed_stdout(db_path, *args, stdin=b""):
    """Run uchr with stdout connected to a pipe whose reader already exited."""
    r, w = os.pipe()
    os.close(r)
    try:
        return subprocess.run(
            [sys.executable, "-c", CHILD, str(db_path), *args],
            stdout=w,
            stderr=subprocess.PIPE,
            input=stdin,
            timeout=60,
        )
    finally:
        os.close(w)


def assert_quiet_exit(result):
    assert result.stderr.decode() == ""
    assert result.returncode == EXIT_BROKEN_PIPE


def test_search_to_closed_pipe_exits_quietly(stored_db):
    assert_quiet_exit(
        run_with_closed_stdout(stored_db, "search", "-b", "Misc_Pictographs")
    )


def test_normalize_to_closed_pipe_exits_quietly(db_path):
    result = run_with_closed_stdout(db_path, "normalize", stdin="ｱｲｳ\n".encode())
    # normalize prints a deprecation warning to stderr; nothing else may follow.
    assert "BrokenPipeError" not in result.stderr.decode()
    assert "Error" not in result.stderr.decode()
    assert result.returncode == EXIT_BROKEN_PIPE


@pytest.mark.parametrize("args", [[], ["--help"]])
def test_help_to_closed_pipe_exits_quietly(db_path, args):
    assert_quiet_exit(run_with_closed_stdout(db_path, *args))
