"""Tests for detail search (no network access)."""

import pytest

from uchr import database, db
from uchr.search import search

UCD_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ucd xmlns="http://www.unicode.org/ns/2003/ucd/1.0">
  <repertoire>
    <char cp="00AA" na="FEMININE ORDINAL INDICATOR" blk="Latin_1_Sup"/>
    <char cp="38C7" na="CJK UNIFIED IDEOGRAPH-#" kDefinition="a kind of beast with long hair, other name for pig, fox, wild cat, raccoon" blk="CJK"/>
    <char cp="54AA" na="CJK UNIFIED IDEOGRAPH-#" kDefinition="sound of cat, cat's meow" blk="CJK"/>
    <char cp="732B" na="CJK UNIFIED IDEOGRAPH-#" kDefinition="cat" blk="CJK"/>
    <char cp="9BF4" na="CJK UNIFIED IDEOGRAPH-#" kDefinition="cat fish" blk="CJK"/>
    <char cp="9C36" na="CJK UNIFIED IDEOGRAPH-#" kDefinition="catfish" blk="CJK"/>
    <char cp="4C22" na="CJK UNIFIED IDEOGRAPH-#" kDefinition="ghost; a star" blk="CJK"/>
    <char cp="5B7D" na="CJK UNIFIED IDEOGRAPH-#" kDefinition="evil; son of concubine; ghost" blk="CJK"/>
    <char cp="9B3C" na="CJK UNIFIED IDEOGRAPH-#" kDefinition="ghost; spirit of dead; devil" blk="CJK"/>
    <char cp="4C2C" na="CJK UNIFIED IDEOGRAPH-#" kDefinition="wild ghost; ghost without head; a demon" blk="CJK"/>
    <char cp="2EE4" na="CJK RADICAL GHOST" blk="CJK_Radicals_Sup"/>
    <char first-cp="17000" last-cp="17001" na="TANGUT IDEOGRAPH-#" blk="Tangut"/>
    <char cp="1F408" na="CAT" blk="Misc_Pictographs"/>
    <char cp="1F47B" na="GHOST" blk="Misc_Pictographs"/>
  </repertoire>
</ucd>
"""


@pytest.fixture(autouse=True)
def stored(tmp_path, monkeypatch, capsys):
    path = tmp_path / "uchr" / "unicode.db"
    monkeypatch.setattr(db, "unicode_sqlite3_database_path", str(path))
    monkeypatch.setattr(database, "download_ucd", lambda url: (UCD_XML, url))
    monkeypatch.setattr(database, "download_emoji_pair", lambda v: (None, None))
    monkeypatch.setattr(database, "resolve_latest_release", lambda: "48.2")
    monkeypatch.setattr(database, "download_annotations", lambda r: b"<ldml/>")
    assert database.update_database(version="17.0.0") == 0
    capsys.readouterr()


def detail_lines(capsys, fragment, **kwargs):
    search(fragment, "detail", " ", version="17.0.0", **kwargs)
    return capsys.readouterr().out.splitlines()


# Whole words only (not INDICATOR or CATFISH), closest first: the fewest
# words in a ";" item of the meaning, or else the name, that matches,
# then the shortest text. CJK ideographs show their meaning instead of
# the name.
CAT_LINES = [
    "猫 732B CAT",
    "🐈 1F408 CAT",
    "鯴 9BF4 CAT FISH",
    "咪 54AA SOUND OF CAT, CAT'S MEOW",
    "㣇 38C7 A KIND OF BEAST WITH LONG HAIR, OTHER NAME FOR PIG, FOX, WILD CAT, RACCOON",
]


def test_detail_search_matches_whole_words_best_first(capsys):
    assert detail_lines(capsys, "cat") == CAT_LINES


def test_name_search_also_matches_cjk_meanings(capsys):
    search("cat", "name", " ", version="17.0.0")
    assert capsys.readouterr().out.splitlines() == CAT_LINES


def test_detail_search_matches_phrases(capsys):
    assert detail_lines(capsys, "Sound of Cat") == [
        "咪 54AA SOUND OF CAT, CAT'S MEOW",
    ]


def test_items_with_fewer_words_rank_first(capsys):
    # GHOST alone first, then texts with an item that is GHOST itself,
    # shorter first wherever the item is, then items with more words.
    assert detail_lines(capsys, "ghost") == [
        "👻 1F47B GHOST",
        "䰢 4C22 GHOST; A STAR",
        "鬼 9B3C GHOST; SPIRIT OF DEAD; DEVIL",
        "孽 5B7D EVIL; SON OF CONCUBINE; GHOST",
        "䰬 4C2C WILD GHOST; GHOST WITHOUT HEAD; A DEMON",
        "⻤ 2EE4 CJK RADICAL GHOST",
    ]


def test_strict_detail_search_matches_whole_detail(capsys):
    assert detail_lines(capsys, "cjk unified ideograph-732b; cat", strict=True) == [
        "猫 732B CAT",
    ]


@pytest.mark.parametrize(
    "fragment, by", [("猫", "char"), ("732B", "code"), ("CJK", "block")]
)
def test_every_search_shows_cjk_meanings(capsys, fragment, by):
    search(fragment, by, " ", version="17.0.0")
    assert "猫 732B CAT" in capsys.readouterr().out.splitlines()


def test_names_derived_from_code_points_are_spelled_out(capsys):
    search("17000-17001", "code", " ", version="17.0.0")
    assert capsys.readouterr().out.splitlines() == [
        "\U00017000 17000 TANGUT IDEOGRAPH-17000",
        "\U00017001 17001 TANGUT IDEOGRAPH-17001",
    ]

    search("cjk unified ideograph-732b", "name", " ", strict=True, version="17.0.0")
    assert capsys.readouterr().out == "猫 732B CAT\n"
