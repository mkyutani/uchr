"""Tests for the version-aware database (no network access)."""

import os
import sqlite3
import stat

import pytest

from uchr import database, db
from uchr.errors import DatabaseError, DownloadError
from uchr.search import search
from uchr.uchr import create_parser

UCD_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ucd xmlns="http://www.unicode.org/ns/2003/ucd/1.0">
  <repertoire>
    <char cp="0041" na="LATIN CAPITAL LETTER A" blk="ASCII"/>
    <char cp="1F47B" na="GHOST" blk="Misc_Pictographs"/>
    <char cp="E000" blk="PUA"/>
    <reserved first-cp="E0080" last-cp="E00FF"/>
  </repertoire>
</ucd>
"""

EMOJI_SEQUENCES = [
    "# comment",
    "",
    "1F47B ; Basic_Emoji ; ghost # E0.6",
    "1F600..1F601 ; Basic_Emoji ; grinning face # E1.0",
    r"0023 FE0F 20E3 ; Emoji_Keycap_Sequence ; keycap: \x{23} # E0.6",
]
EMOJI_ZWJ = ["1F468 200D 1F469 ; RGI_Emoji_ZWJ_Sequence ; couple # E2.0"]

ANNOTATIONS_XML = """<ldml><annotations>
  <annotation cp="👻">creature | ghost | monster</annotation>
  <annotation cp="👻" type="tts">ghost</annotation>
</annotations></ldml>
""".encode()


@pytest.fixture(autouse=True)
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "uchr" / "unicode.db"
    monkeypatch.setattr(db, "unicode_sqlite3_database_path", str(path))
    return path


@pytest.fixture
def fake_network(monkeypatch):
    """Serve UCD/emoji data from memory and record what was downloaded."""
    calls = {"ucd": [], "latest": "17.0.0", "drafts": set()}

    def fake_download_ucd(url):
        calls["ucd"].append(url)
        version = url.split("/Public/")[1].split("/")[0]
        final = url.replace(version, "draft") if version in calls["drafts"] else url
        return UCD_XML, final

    def fake_latest():
        v = calls["latest"]
        return v, f"https://www.unicode.org/Public/{v}/ucdxml/ucd.all.flat.zip"

    monkeypatch.setattr(database, "download_ucd", fake_download_ucd)
    monkeypatch.setattr(database, "resolve_latest_version", fake_latest)
    monkeypatch.setattr(
        database, "download_emoji_pair", lambda v: (EMOJI_SEQUENCES, EMOJI_ZWJ)
    )
    monkeypatch.setattr(database, "resolve_latest_release", lambda: "48.2")
    monkeypatch.setattr(database, "download_annotations", lambda r: ANNOTATIONS_XML)
    return calls


def query(sql, params=()):
    with db.Connection() as conn:
        return conn.execute(sql, params).fetchall()


def create_legacy_db(path):
    """Build a DB with the pre-versioning schema, as `db create` used to."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table char(id integer primary key, name text, detail text,
                          codetext text, char text, block text);
        create table codepoint(char integer, seq integer, code integer,
                               primary key(char, seq));
        create unique index char_index on char(codetext);
        insert into char values(1, 'GHOST', 'GHOST', '1F47B', '👻', 'Misc');
        insert into codepoint values(1, 1, 128123);
        """
    )
    conn.commit()
    conn.close()


def test_update_stores_version_and_sets_current(fake_network):
    assert database.update_database() == 0

    database_ = db.Database()
    assert database_.get_current_version() == "17.0.0"
    local = database_.local_versions()
    # 2 UCD chars + ghost(dup, skipped) + 2 range + keycap + zwj
    assert local == {"17.0.0": {"draft": False, "chars": 6}}
    assert query("select count(*) from char where version = '17.0.0'") == [(6,)]


def test_update_summarizes_skipped_entries(fake_network, capsys):
    database.update_database()

    err = capsys.readouterr().err
    assert (
        "Stored 2 characters for version 17.0.0 "
        "(skipped 1 unnamed code points, 1 reserved ranges)"
    ) in err
    assert "Stored 4 emoji sequences for version 17.0.0 (1 already present)" in err
    assert "Found " not in err
    assert "Already registered" not in err


def test_update_verbose_lists_each_skipped_entry(fake_network, capsys):
    database.update_database(verbose=True)

    err = capsys.readouterr().err
    assert "Found no character: E000" in err
    assert "Found reserved code(s): E0080-E00FF" in err
    assert "Already registered: 1F47B ghost" in err


def test_db_update_verbose_option(monkeypatch):
    calls = []

    def fake_update(version=None, verbose=False):
        calls.append((version, verbose))
        return 0

    monkeypatch.setattr(database, "update_database", fake_update)
    args = create_parser().parse_args(["db", "update", "--verbose"])
    assert args.func(args) == 0
    assert calls == [(None, True)]


def test_db_file_is_created_with_mode_0644(fake_network, db_path):
    old_umask = os.umask(0o000)
    try:
        database.update_database()
    finally:
        os.umask(old_umask)
    assert stat.S_IMODE(os.stat(db_path).st_mode) == 0o644


def test_update_skips_already_stored_version(fake_network):
    database.update_database(version="16.0.0")
    database.update_database(version="17.0.0")
    assert database.update_database(version="16.0.0") == 0

    assert len(fake_network["ucd"]) == 2
    assert db.Database().get_current_version() == "16.0.0"


def test_update_refetches_draft_version(fake_network, capsys):
    fake_network["drafts"].add("18.0.0")
    database.update_database(version="18.0.0")
    assert "draft" in capsys.readouterr().err
    assert db.Database().local_versions()["18.0.0"]["draft"] is True

    fake_network["drafts"].clear()  # 18.0.0 got released
    database.update_database(version="18.0.0")
    assert len(fake_network["ucd"]) == 2
    local = db.Database().local_versions()
    assert local["18.0.0"]["draft"] is False
    assert query("select count(*) from char where version = '18.0.0'") == [(6,)]


def test_failed_download_leaves_no_partial_version(fake_network, monkeypatch):
    def broken_emoji(version):
        raise DownloadError("connection reset")

    monkeypatch.setattr(database, "download_emoji_pair", broken_emoji)
    assert database.update_database(version="16.0.0") == 1
    assert db.Database().local_versions() == {}
    assert query("select count(*) from char") == [(0,)]


def test_missing_emoji_data_still_stores_ucd(fake_network, monkeypatch):
    monkeypatch.setattr(database, "download_emoji_pair", lambda v: (None, None))
    assert database.update_database(version="6.0.0") == 0
    assert db.Database().local_versions()["6.0.0"]["chars"] == 2


def test_delete_version_removes_only_that_version(fake_network):
    database.update_database(version="16.0.0")
    database.update_database(version="17.0.0")

    assert database.delete_version("17.0.0") == 0
    assert set(db.Database().local_versions()) == {"16.0.0"}
    assert db.Database().get_current_version() is None
    orphans = query(
        "select count(*) from codepoint where char not in (select id from char)"
    )
    assert orphans == [(0,)]

    assert database.delete_version("17.0.0") == 1


def test_use_requires_local_version(fake_network):
    database.update_database(version="16.0.0")
    database.update_database(version="17.0.0")

    assert database.use_version("16.0.0") == 0
    assert db.Database().get_current_version() == "16.0.0"
    assert database.use_version("15.1.0") == 1


def test_search_filters_by_version(fake_network, capsys):
    database.update_database(version="16.0.0")
    database.update_database(version="17.0.0")
    capsys.readouterr()

    search("GHOST", "name", " ", version="16.0.0")
    assert capsys.readouterr().out == "👻 1F47B GHOST\n"

    search("1F600-1F601", "code", " ", version="17.0.0")
    assert capsys.readouterr().out.count("grinning face") == 2


def test_resolve_search_version(fake_network):
    # First run without a DB fetches latest.
    assert database.resolve_search_version(None) == ("17.0.0", None)
    # An explicit version that isn't stored is an error, not a fetch.
    version, error = database.resolve_search_version("16.0.0")
    assert version is None and "db update --version 16.0.0" in error
    assert len(fake_network["ucd"]) == 1


def test_explicit_version_without_db_does_not_fetch(fake_network, db_path):
    version, error = database.resolve_search_version("16.0.0")
    assert version is None and error
    assert fake_network["ucd"] == []
    assert not db_path.exists()


def test_legacy_db_is_migrated(db_path):
    create_legacy_db(db_path)

    database_ = db.Database()
    database_.open_for_read()

    assert database_.local_versions() == {
        db.LEGACY_VERSION: {"draft": False, "chars": 1}
    }
    assert database_.get_current_version() == db.LEGACY_VERSION
    assert query("pragma user_version") == [(db.SCHEMA_VERSION,)]
    assert query("select count(*) from keyword") == [(0,)]
    # The unique index now spans (codetext, version).
    with db.Connection() as conn:
        conn.execute("insert into char(codetext, version) values('1F47B', '16.0.0')")


def test_read_of_current_schema_does_not_write(fake_network, db_path):
    database.update_database(version="17.0.0")
    os.chmod(db_path, 0o444)
    mtime = os.stat(db_path).st_mtime_ns

    assert database.resolve_search_version(None) == ("17.0.0", None)
    assert os.stat(db_path).st_mtime_ns == mtime


@pytest.mark.skipif(os.getuid() == 0, reason="root bypasses file permissions")
def test_write_to_read_only_db_fails_clearly(fake_network, db_path):
    database.update_database(version="17.0.0")
    os.chmod(db_path, 0o444)

    with pytest.raises(DatabaseError, match="Permission denied"):
        database.use_version("17.0.0")


def test_parse_emoji_line():
    assert database.parse_emoji_line("# x") == []
    assert database.parse_emoji_line("1F600..1F601 ; T ; name # c") == [
        ("1F600", [0x1F600], "T", "name"),
        ("1F601", [0x1F601], "T", "name"),
    ]
    assert database.parse_emoji_line(r"0023 FE0F 20E3 ; K ; keycap: \x{23} # c") == [
        ("0023 FE0F 20E3", [0x23, 0xFE0F, 0x20E3], "K", r"keycap: \x{23}"),
    ]


def test_migration_spells_out_code_point_names(db_path):
    create_legacy_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "insert into char values(2, 'CJK UNIFIED IDEOGRAPH-#', "
            "'CJK UNIFIED IDEOGRAPH-#; CAT', '732B', '猫', 'CJK')"
        )
    db.Database().open_for_read()

    assert query("select name, detail from char where codetext = '732B'") == [
        ("CJK UNIFIED IDEOGRAPH-732B", "CJK UNIFIED IDEOGRAPH-732B; CAT")
    ]
    assert query("select name, detail from char where codetext = '1F47B'") == [
        ("GHOST", "GHOST")
    ]
