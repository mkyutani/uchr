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
                dml = " ".join(
                    [
                        head,
                        "inner join codepoint as cp on char.id = cp.char",
                        "where cp.code >= ? and cp.code <= ?",
                        "order by char.char",
                    ]
                )
                params = (code_range[0], code_range[1])
            else:
                dml = " ".join(
                    [
                        head,
                        "inner join codepoint as cp on char.id = cp.char",
                        "where cp.code = ?",
                        "order by char.char",
                    ]
                )
                params = (code_range,)
        elif by == "char":
            dml = " ".join([head, "where char.char = ?"])
            params = (fragment,)
        else:
            column = f"upper({by})" if strict else by
            value = fragment.upper() if strict else f"%{fragment}%"
            operator = "=" if strict else "like"
            table = head_detail if by == "detail" else head
            dml = " ".join([table, "where", column, operator, "?", "order by char.char"])
            params = (value,)

        with Cursor(conn) as cur:
            cur.execute(dml, params)
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
