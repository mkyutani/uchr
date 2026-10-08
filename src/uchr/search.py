#!/usr/bin/env python3

import re

from .db import Connection, Cursor


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
):
    if output_format is not None:
        output_format = output_format.upper()

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
        else:
            column = f"upper({by})" if strict else by
            value = fragment.upper() if strict else f"%{fragment}%"
            operator = "=" if strict else "like"
            table = head_detail if by == "detail" else head
            dml = " ".join(
                [
                    table,
                    "where",
                    column,
                    operator,
                    "?",
                    "and char.version = ?",
                    "order by char.char",
                ]
            )
            params = (value, version)

        with Cursor(conn) as cur:
            cur.execute(dml, params)
            char_list = cur.fetchall()

        if first:
            char_list = char_list[0:1]

        for _id, codetext, name, char in char_list:
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

                print(delimiter.join([char, codetext, name]))
