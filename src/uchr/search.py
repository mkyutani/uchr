#!/usr/bin/env python3

import math
import re
import sys
from collections import Counter

from .cldr import VARIATION_SELECTOR_16, strip_vs16
from .db import Connection, Cursor

# Minimum similarity (0-1) for a related emoji to be listed.
DEFAULT_THRESHOLD = 0.3


def whole_words(fragment):
    """Regex that finds `fragment` as whole words, ignoring case."""
    return re.compile(rf"(?<!\w){re.escape(fragment)}(?!\w)", re.IGNORECASE)


# Notes like "(SAME AS 雪)" that a meaning item is not measured by.
_NOTE = re.compile(r"\([^)]*\)")


def word_score(pattern, text, name):
    """How well the whole-word matches of `pattern` fit a character, 0-1.

    `text` is the name or, for a CJK ideograph, the name, "; " and its
    meaning (kDefinition); the meaning is what counts when it matches.
    Each item of it (split at ";" and ",") scores the share of it that the
    matches take up, halved for every item before it: 1 for 猫 (CAT) and
    鬼 (GHOST; SPIRIT OF DEAD; ...), 0.05 for 㣇 (A KIND OF BEAST WITH LONG
    HAIR, OTHER NAME FOR PIG, FOX, WILD CAT, RACCOON). The best item is
    lifted by 1 - (1 - w)^2, nearly doubling a partial match so it can
    compete with the CLDR similarity of related emoji, while 1 stays 1.
    """
    meaning = text[len(name) + 2 :]
    w = (
        _item_score(pattern, meaning)
        or _item_score(pattern, text)
        or _share(pattern, text)
    )
    return 1 - (1 - w) ** 2


def _item_score(pattern, text):
    return max(
        (
            _share(pattern, _NOTE.sub("", item).strip()) * 0.5**i
            for i, item in enumerate(re.split("[;,]", text))
        ),
        default=0,
    )


def _share(pattern, text):
    matched = sum(len(m.group()) for m in pattern.finditer(text))
    return matched / len(text) if matched else 0


def shown_text(text, name):
    """What to print for a match: a CJK ideograph's meaning, else the name."""
    return text[len(name) + 2 :] or text


def get_code_range(fragment):
    if "-" in fragment:
        m = re.match("([0-9A-Fa-f]+)-([0-9A-Fa-f]+)", fragment)
        r = (int(m.group(1), 16), int(m.group(2), 16))
    else:
        m = re.match("[0-9A-Fa-f]+", fragment)
        r = int(fragment, 16)
    return r


def search(
    fragment,
    by,
    delimiter,
    strict=False,
    first=False,
    output_format=None,
    version=None,
    threshold=DEFAULT_THRESHOLD,
):
    if output_format is not None:
        output_format = output_format.upper()

    with Connection() as conn:
        # Every query yields (id, codetext, text, char, name): `text` is the
        # name or, for a CJK ideograph, the name, "; " and its meaning
        # (kDefinition), which `detail` appends to the name. Emoji
        # sequences have no detail.
        text = "coalesce(char.detail, char.name)"
        head = f"select char.id, char.codetext, {text}, char.char, char.name from char"
        if by == "code":
            code_range = get_code_range(fragment)
            if type(code_range) is tuple:
                dml = " ".join(
                    [
                        head,
                        "inner join codepoint as cp on char.id = cp.char",
                        "where cp.code >= ? and cp.code <= ? and char.version = ?",
                        "order by char.char",
                    ]
                )
                params = (code_range[0], code_range[1], version)
            else:
                dml = " ".join(
                    [
                        head,
                        "inner join codepoint as cp on char.id = cp.char",
                        "where cp.code = ? and char.version = ?",
                        "order by char.char",
                    ]
                )
                params = (code_range, version)
        elif by == "char":
            dml = " ".join([head, "where char.char = ? and char.version = ?"])
            params = (fragment, version)
        elif by == "block" or strict:
            column = f"upper({by})" if strict else by
            value = fragment.upper() if strict else f"%{fragment}%"
            operator = "=" if strict else "like"
            dml = " ".join(
                [
                    head,
                    "where",
                    column,
                    operator,
                    "?",
                    "and char.version = ?",
                    "order by char.char",
                ]
            )
            params = (value, version)
        else:
            # Name (and detail) search looks for whole words of `text`.
            dml = " ".join(
                [
                    head,
                    f"where {text} like ? and char.version = ?",
                    "order by char.char",
                ]
            )
            params = (f"%{fragment}%", version)

        with Cursor(conn) as cur:
            cur.execute(dml, params)
            char_list = cur.fetchall()

        if by in ("name", "detail") and not strict:
            # LIKE found substrings ("cat" in "INDICATOR"); keep whole
            # words. Name search adds related emoji, scored by their CLDR
            # similarity. Best score first, ties in code order.
            pattern = whole_words(fragment)
            scores = {}
            for row in char_list:
                score = word_score(pattern, row[2], row[4])
                if score:
                    scores[row[0]] = (score, row)
            if by == "name":
                matched = [row for _score, row in scores.values()]
                for score, row in related_emoji(
                    conn, fragment, matched, version, threshold
                ):
                    if score > scores.get(row[0], (0,))[0]:
                        scores[row[0]] = (score, row)
            ranked = sorted(scores.values(), key=lambda s: (-s[0], s[1][3] or ""))
            char_list = [row for _score, row in ranked]

        if first:
            char_list = char_list[0:1]

        for _id, codetext, text, char, name in char_list:
            if not char:
                char = str(char)

            if output_format == "SIMPLE":
                print(char, end="")
            else:
                if output_format == "UTF8":
                    codetext = " ".join(
                        f"{u:X}"
                        for u in [
                            int.from_bytes(chr(int(c, 16)).encode(), "big")
                            for c in codetext.split(" ")
                        ]
                    )

                print(delimiter.join([char, codetext, shown_text(text, name)]))


def related_emoji(conn, fragment, matched, version, threshold):
    """Return (similarity, row) for the emoji related to `fragment`, those
    whose similarity reaches `threshold`.

    The emoji that `fragment` names directly (a CLDR keyword, or a whole
    word of their name: the `matched` rows) are the seeds; every emoji is
    then scored by how much its CLDR keywords overlap with theirs.
    """
    keywords = {}
    for char, keyword in conn.execute("select char, keyword from keyword"):
        keywords.setdefault(char, set()).add(keyword)
    if not keywords:
        print(
            "Note: no keyword data for related results; run 'uchr db update'",
            file=sys.stderr,
        )
        return []

    query = fragment.lower()
    words = query.split()
    seeds = {
        char
        for char, ks in keywords.items()
        if query in ks or (words and all(w in ks for w in words))
    }
    seeds |= {strip_vs16(row[3]) for row in matched if row[3]} & keywords.keys()
    if not seeds:
        return []

    scores = {
        char: score
        for char, score in rank_related(keywords, seeds).items()
        if score >= threshold
    }
    if not scores:
        return []
    rows = conn.execute(
        "select id, codetext, coalesce(detail, name), char, name from char "
        "where version = ? and replace(char, ?, '') in (select char from keyword)",
        (version, VARIATION_SELECTOR_16),
    ).fetchall()
    return [
        (scores[strip_vs16(row[3])], row)
        for row in rows
        if strip_vs16(row[3]) in scores
    ]


def rank_related(keywords, seeds):
    """Score each emoji by the cosine similarity between its keywords and
    the seeds' keywords averaged together, as IDF-weighted vectors so that
    generic keywords like "face" count for little."""
    df = Counter(k for ks in keywords.values() for k in ks)
    idf = {k: math.log(len(keywords) / n) for k, n in df.items()}

    def unit_vector(ks):
        norm = math.sqrt(sum(idf[k] ** 2 for k in ks))
        return {k: idf[k] / norm for k in ks} if norm else {}

    centroid = Counter()
    for seed in seeds:
        for k, v in unit_vector(keywords[seed]).items():
            centroid[k] += v / len(seeds)
    norm = math.sqrt(sum(v * v for v in centroid.values()))
    if not norm:
        return {}

    scores = {}
    for char, ks in keywords.items():
        dot = sum(v * centroid[k] for k, v in unit_vector(ks).items())
        if dot > 0:
            scores[char] = dot / norm
    return scores
