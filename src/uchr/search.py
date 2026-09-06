#!/usr/bin/env python3

import re

from .db import Connection, Cursor


def get_code_range(fragment):
    if "-" in fragment:
        m = re.match("([0-9A-Fa-f]+)-([0-9A-Fa-f]+)", fragment)
        min = int(m.group(1), 16)
        max = int(m.group(2), 16)
        r = (min, max)
    else:
        m = re.match("[0-9A-Fa-f]+", fragment)
        r = int(fragment, 16)
    return r


def search(fragment, by, delimiter, strict=False, first=False, format=None):
    if format is not None:
        format = format.upper()

    with Connection() as conn:
        char_list = []
        head = "select char.id, char.codetext, char.name, char.char from char"
        head_detail = "select char.id, char.codetext, char.detail, char.char from char"
        if by == "code":
            code_range = get_code_range(fragment)
            if type(code_range) is tuple:
                cond = (
                    f"where cp.code >= {code_range[0]} and cp.code <= {code_range[1]}"
                )
            else:
                cond = f"where cp.code = {code_range}"
            dml = " ".join(
                [
                    head,
                    "inner join codepoint as cp on char.id = cp.char",
                    cond,
                    "order by char.char",
                ]
            )
        elif by == "char":
            cond = f'where char.char = "{fragment}"'
            dml = " ".join([head, cond])
        else:
            if strict:
                by = f"upper({by})"
                matched = f'= "{fragment.upper()}"'
            else:
                matched = f'like "%{fragment}%"'
            if by == "detail":
                dml = " ".join(
                    [head_detail, "where", by, matched, "order by char.char"]
                )
            else:
                dml = " ".join([head, "where", by, matched, "order by char.char"])

        with Cursor(conn) as cur:
            cur.execute(dml)
            char_list = cur.fetchall()

        if first == True:
            char_list = char_list[0:1]

        for id, codetext, name, char in char_list:
            if not char:
                char = str(char)

            if format == "SIMPLE":
                print(char, end="")
            else:
                if format == "UTF8":
                    codetext = " ".join(
                        f"{u:X}"
                        for u in [
                            int.from_bytes(chr(int(c, 16)).encode(), "big")
                            for c in codetext.split(" ")
                        ]
                    )

                print(delimiter.join([char, codetext, name]))
