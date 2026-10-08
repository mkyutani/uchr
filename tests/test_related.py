"""Tests for related-emoji results in name search (no network access)."""

import pytest

from uchr import cldr, database, db
from uchr.errors import DownloadError
from uchr.search import search
from uchr.uchr import create_parser

UCD_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ucd xmlns="http://www.unicode.org/ns/2003/ucd/1.0">
  <repertoire>
    <char cp="2603" na="SNOWMAN" blk="Misc_Symbols"/>
    <char cp="2EE4" na="CJK RADICAL GHOST" blk="CJK_Radicals_Sup"/>
    <char cp="1F47A" na="JAPANESE GOBLIN" blk="Misc_Pictographs"/>
    <char cp="1F47B" na="GHOST" blk="Misc_Pictographs"/>
    <char cp="1F600" na="GRINNING FACE" blk="Emoticons"/>
  </repertoire>
</ucd>
"""

EMOJI_SEQUENCES = ["2603 FE0F ; Basic_Emoji ; snowman # E0.6"]

# ❄ has keywords but no row in the DB.
ANNOTATIONS_XML = """<ldml><annotations>
  <annotation cp="👻">Creature | fantasy | ghost | monster | scary</annotation>
  <annotation cp="👻" type="tts">ghost</annotation>
  <annotation cp="👺">creature | fantasy | goblin | monster | scary</annotation>
  <annotation cp="😀">face | grin | smile</annotation>
  <annotation cp="☃️">cold | snow | snowman</annotation>
  <annotation cp="❄">cold | snow | snowflake</annotation>
</annotations></ldml>
""".encode()


@pytest.fixture(autouse=True)
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "uchr" / "unicode.db"
    monkeypatch.setattr(db, "unicode_sqlite3_database_path", str(path))
    return path


@pytest.fixture
def annotations(monkeypatch):
    """Serve UCD/emoji/CLDR data from memory. Returns a dict holding the
    latest CLDR release to report and the releases fetched so far."""
    cldr_state = {"latest": "48.2", "fetched": []}

    def fake_latest():
        if cldr_state["latest"] is None:
            raise DownloadError("github.com unreachable")
        return cldr_state["latest"]

    def fake_download_annotations(release):
        cldr_state["fetched"].append(release)
        return ANNOTATIONS_XML

    monkeypatch.setattr(database, "download_ucd", lambda url: (UCD_XML, url))
    monkeypatch.setattr(
        database, "download_emoji_pair", lambda v: (EMOJI_SEQUENCES, None)
    )
    monkeypatch.setattr(database, "resolve_latest_release", fake_latest)
    monkeypatch.setattr(database, "download_annotations", fake_download_annotations)
    return cldr_state


@pytest.fixture
def stored(annotations, capsys):
    assert database.update_database(version="17.0.0") == 0
    capsys.readouterr()
    return annotations


def search_lines(capsys, fragment, **kwargs):
    search(fragment, "name", " ", version="17.0.0", **kwargs)
    return capsys.readouterr().out.splitlines()


def test_parse_annotations():
    assert cldr.parse_annotations(ANNOTATIONS_XML) == {
        "👻": {"creature", "fantasy", "ghost", "monster", "scary"},
        "👺": {"creature", "fantasy", "goblin", "monster", "scary"},
        "😀": {"face", "grin", "smile"},
        "☃": {"cold", "snow", "snowman"},
        "❄": {"cold", "snow", "snowflake"},
    }


def test_update_stores_keywords_once(stored):
    assert db.Database().get_keyword_release() == "48.2"
    assert database.update_database(version="16.0.0") == 0
    assert stored["fetched"] == ["48.2"]


def test_keywords_follow_the_latest_release(stored):
    stored["latest"] = "49"
    database.update_database(version="17.0.0")
    assert stored["fetched"] == ["48.2", "49"]
    assert db.Database().get_keyword_release() == "49"


def test_unresolved_release_keeps_stored_keywords(stored, capsys):
    stored["latest"] = None
    assert database.update_database(version="17.0.0") == 0
    assert "keeping CLDR 48.2 keywords" in capsys.readouterr().err
    assert stored["fetched"] == ["48.2"]


def test_unresolved_release_without_keywords_uses_fallback(annotations, capsys):
    annotations["latest"] = None
    assert database.update_database(version="17.0.0") == 0
    assert f"using CLDR {cldr.FALLBACK_RELEASE}" in capsys.readouterr().err
    assert annotations["fetched"] == [cldr.FALLBACK_RELEASE]
    assert db.Database().get_keyword_release() == cldr.FALLBACK_RELEASE


def test_keyword_download_failure_is_only_a_warning(annotations, monkeypatch, capsys):
    def broken(release):
        raise DownloadError("connection reset")

    monkeypatch.setattr(database, "download_annotations", broken)
    assert database.update_database(version="17.0.0") == 0
    assert "Warning: failed to fetch CLDR keywords" in capsys.readouterr().err
    assert db.Database().get_keyword_release() is None


def test_related_emoji_mix_with_word_matches_by_score(stored, capsys):
    # 👺 shares 4 of 5 keywords with 👻 (similarity 0.56); ⻤ is a partial
    # match (5 of 17 letters, lifted to 0.50).
    assert search_lines(capsys, "ghost") == [
        "👻 1F47B GHOST",
        "👺 1F47A JAPANESE GOBLIN",
        "⻤ 2EE4 CJK RADICAL GHOST",
    ]


def test_strict_search_lists_no_related_emoji(stored, capsys):
    assert search_lines(capsys, "ghost", strict=True) == ["👻 1F47B GHOST"]


def test_threshold_drops_less_similar_emoji(stored, capsys):
    assert search_lines(capsys, "ghost", threshold=0.6) == [
        "👻 1F47B GHOST",
        "⻤ 2EE4 CJK RADICAL GHOST",
    ]


def test_keyword_seeds_match_emoji_with_and_without_fe0f(stored, capsys):
    # No name contains "cold"; both snowman rows share the ☃ keywords.
    assert search_lines(capsys, "cold") == [
        "☃ 2603 SNOWMAN",
        "☃️ 2603 FE0F snowman",
    ]


def test_search_without_keywords_lists_name_matches(annotations, monkeypatch, capsys):
    monkeypatch.setattr(database, "download_annotations", lambda r: b"<ldml/>")
    database.update_database(version="17.0.0")
    capsys.readouterr()

    search("ghost", "name", " ", version="17.0.0")
    out, err = capsys.readouterr()
    assert out.splitlines() == ["👻 1F47B GHOST", "⻤ 2EE4 CJK RADICAL GHOST"]
    assert "uchr db update" in err


@pytest.mark.parametrize("value", ["0", "1.5", "-0.1", "nan", "high"])
def test_threshold_must_be_in_unit_interval(value):
    with pytest.raises(SystemExit):
        create_parser().parse_args(["search", "-t", value, "ghost"])


def test_threshold_is_ignored_in_strict_search(stored, capsys):
    args = create_parser().parse_args(["search", "-s", "-t", "0.5", "ghost"])
    args.func(args)
    out, err = capsys.readouterr()
    assert "Ignore --threshold in strict search" in err
    assert out == "👻 1F47B GHOST\n"
