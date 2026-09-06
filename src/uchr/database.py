#!/usr/bin/env python3

import io
import os
import re
import sqlite3
import sys
import tempfile
import xml.etree.ElementTree as et
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests

from .db import AutoID, Connection, Cursor, Database

namespace = "{http://www.unicode.org/ns/2003/ucd/1.0}"
tag_ucd = namespace + "ucd"
tag_description = namespace + "description"
tag_repertoire = namespace + "repertoire"
tag_char = namespace + "char"
tag_noncharacter = namespace + "noncharacter"
tag_reserved = namespace + "reserved"
tag_surrogate = namespace + "surrogate"
tag_name_alias = namespace + "name-alias"

table_char_autoincrement_id = AutoID().init()


def download_ucd(ucd_zip_url):
    ucd_zip_url_path = Path(urlparse(ucd_zip_url)[2])
    ucd_zip_filename = ucd_zip_url_path.name
    ucd_xml_filename = ucd_zip_url_path.with_suffix(".xml").name

    zip_filepath = "(Not assigned)"

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_filepath = os.path.join(tmpdir, ucd_zip_filename)

            print(f"Downloading {ucd_zip_url} ...", file=sys.stderr)

            res = requests.get(ucd_zip_url, stream=True)
            if res.status_code >= 400:
                print(f"Fetch error: {res.status_code}", file=sys.stderr)
                return None

            content_type = res.headers["Content-Type"]
            if content_type != "application/zip":
                print(f"Invalid content type: {content_type}")
                return None

            with open(zip_filepath, "wb") as fzip:
                for chunk in res.iter_content(chunk_size=1024):
                    if chunk:
                        fzip.write(chunk)
                        fzip.flush()

            print(f"Downloaded {zip_filepath}", file=sys.stderr)

            with zipfile.ZipFile(zip_filepath, "r") as zip:
                xml_list = zip.read(ucd_xml_filename)

            print("Extracted unicode data xml", file=sys.stderr)

            return xml_list

    except Exception as e:
        print(
            f"Failed to download zip from {ucd_zip_url} to {zip_filepath}",
            file=sys.stderr,
        )
        print(f"{type(e).__name__}: {str(e)}", file=sys.stderr)
        return None


def get_ucd_cp(tag):
    cp = tag.attrib.get("cp")
    first_cp = tag.attrib.get("first-cp")
    last_cp = tag.attrib.get("last-cp")

    if cp:
        first_cp = cp
        last_cp = cp

    if not (first_cp and last_cp):
        print(
            f"Invalid code range: cp={cp}, first_cp={first_cp}, last_cp={last_cp}",
            file=sys.stderr,
        )
        return None

    min = int(first_cp, 16)
    max = int(last_cp, 16)

    return (min, max)


def get_ucd_char_cp(char):
    value = None
    r = get_ucd_cp(char)
    if r:
        min = r[0]
        max = r[1]
        if char.tag != tag_char:
            if min == max:
                code_range = f"{min:X}"
            else:
                code_range = f"{min:X}-{max:X}"

            if char.tag == tag_reserved:
                print(f"Found reserved code(s): {code_range}", file=sys.stderr)
            elif char.tag == tag_noncharacter:
                print(f"Found non character code(s): {code_range}", file=sys.stderr)
            elif char.tag == tag_surrogate:
                print(f"Found surrogate code(s): {code_range}", file=sys.stderr)
            else:
                print(f"Found unknown tag: {char.tag} {code_range}", file=sys.stderr)
            return []

        value = range(min, max + 1)
        return value


def get_name(char):
    value = []
    name = char.attrib.get("na")
    name1 = char.attrib.get("na1")
    if name and len(name) > 0:
        value.append(name)
    if name1 and len(name1) > 0 and name != name1:
        value.append(name1)
    for alias in char:
        if alias.tag == tag_name_alias:
            alias_name = alias.attrib.get("alias")
            if alias_name and len(alias_name) > 0 and alias_name not in value:
                value.append(alias_name)
    return "; ".join(value)


def get_detail(char, name):
    definition = char.attrib.get("kDefinition")
    if definition and len(definition) > 0:
        return "; ".join([name, definition.upper()])
    else:
        return name


def store_ucd(xml_list):
    if not xml_list:
        return None

    root = et.parse(io.BytesIO(xml_list)).getroot()
    if root.tag != tag_ucd:
        print(f"Unexpected XML scheme: {root.tag}", file=sys.stderr)
        return None

    repertoire = root.find(tag_repertoire)

    with Connection() as conn:
        with Cursor(conn) as cur:
            count = 0
            for char in repertoire:
                code_range = get_ucd_char_cp(char)
                for code in code_range:
                    value_code = code
                    value_code_text = f'"{value_code:X}"'
                    name = get_name(char)
                    if not name:
                        print(f"Found no character: {code:X}", file=sys.stderr)
                        continue
                    value_name = f'"{name}"'
                    detail = get_detail(char, name)
                    value_detail = f'"{detail}"'

                    try:
                        if code == 0:
                            value_char = "NULL"
                        else:
                            escaped_char = str(chr(code)).replace('"', '""')
                            value_char = f'"{escaped_char}"'
                    except ValueError:
                        print(f"Invalid character {code:X} ({name})", file=sys.stderr)
                        continue

                    block = char.attrib.get("blk")
                    if not block:
                        print(f"No block name: {code:X}", file=sys.stderr)
                        value_block = '"(None)"'
                    else:
                        value_block = f'"{block}"'

                    id = table_char_autoincrement_id.next()
                    dml = f"insert into char(id, name, detail, codetext, char, block) values({id}, {value_name}, {value_detail}, {value_code_text}, {value_char}, {value_block})"
                    cur.execute(dml)
                    dml_seq = f"insert into codepoint(char, seq, code) values({id}, 1, {value_code})"
                    cur.execute(dml_seq)
                    count = count + 1

            conn.commit()
            print(f"Stored {count} characters", file=sys.stderr)


def download_emoji(emoji_txt_url):
    try:
        res = requests.get(emoji_txt_url)
        if res.status_code >= 400:
            print(f"Fetch error: {res.status_code}", file=sys.stderr)
            return None

        content_type = res.headers["Content-Type"]
        if not ("text/plain" in content_type and "charset=utf-8" in content_type):
            print(f"Invalid content type: {content_type}")
            return None

        return res.text.splitlines()

    except Exception as e:
        print(f"Failed to download emoji from {emoji_txt_url}", file=sys.stderr)
        print(f"{type(e).__name__}: {str(e)}", file=sys.stderr)
        return None


def store_emoji(emoji_sequences):
    if not emoji_sequences:
        return

    emoji_sequence_line_pattern = re.compile("^(.+);(.+);([^#]+)#")
    emoji_sequence_cp_pattern = re.compile("([0-9A-Fa-f]+)")
    emoji_sequence_multi_pattern = re.compile("([0-9A-Fa-f]+)")
    emoji_sequence_continuous_pattern = re.compile(r"([0-9A-Fa-f]+)\.\.([0-9A-Fa-f]+)")

    with Connection() as conn:
        with Cursor(conn) as cur:
            count = 0
            for sequence in emoji_sequences:
                if len(sequence) == 0 or sequence.startswith("#"):
                    continue
                emoji = emoji_sequence_line_pattern.match(sequence)
                emoji_codes = emoji.group(1).strip()
                emoji_type = emoji.group(2).strip()
                emoji_name = emoji.group(3).strip()

                cp_list = []
                cp = re.fullmatch(emoji_sequence_cp_pattern, emoji_codes)
                if cp:
                    cp_list.append(int(emoji_codes, 16))
                else:
                    cp = re.match(emoji_sequence_continuous_pattern, emoji_codes)
                    if cp:
                        min = int(cp.group(1), 16)
                        max = int(cp.group(2), 16)
                        cp_list.extend(list(range(min, max + 1)))
                    else:
                        seq = []
                        for cp in re.finditer(
                            emoji_sequence_multi_pattern, emoji_codes
                        ):
                            seq.append(int(cp.group(1), 16))
                        cp_list.append(seq)
                if len(cp_list) == 0:
                    print(
                        f"Failed to get code points: {emoji_codes}, {emoji_name}",
                        file=sys.stderr,
                    )
                    continue

                value_name = f'"{emoji_name}"'
                value_code_text = f'"{emoji_codes}"'
                value_block = f'"{emoji_type}"'
                for code in cp_list:
                    if type(code) is int:
                        value_code_text = f'"{code:X}"'
                        char = chr(code)
                        value_char = f'"{char}"'
                    else:
                        char = ""
                        for c in code:
                            char = char + chr(c)
                        value_char = f'"{char}"'

                    try:
                        id = table_char_autoincrement_id.next()
                        dml = f"insert into char(id, name, codetext, char, block) values({id}, {value_name}, {value_code_text}, {value_char}, {value_block})"
                        cur.execute(dml)
                        if type(code) is int:
                            dml_seq = f"insert into codepoint(char, seq, code) values({id}, 1, {code})"
                            cur.execute(dml_seq)
                        else:
                            for i, c in enumerate(code):
                                dml_seq = f"insert into codepoint(char, seq, code) values({id}, {i}, {c})"
                                cur.execute(dml_seq)
                        count = count + 1
                    except sqlite3.IntegrityError:
                        print(
                            f"Already registered: {value_code_text} {value_name}",
                            file=sys.stderr,
                        )

            conn.commit()
            print(f"Stored {count} emoji characters", file=sys.stderr)


def create_database():
    """Create Unicode database"""
    Database().create()
    store_ucd(
        download_ucd("https://www.unicode.org/Public/15.0.0/ucdxml/ucd.all.flat.zip")
    )
    store_emoji(
        download_emoji("https://www.unicode.org/Public/emoji/15.0/emoji-sequences.txt")
    )
    store_emoji(
        download_emoji(
            "https://www.unicode.org/Public/emoji/15.0/emoji-zwj-sequences.txt"
        )
    )
    return 0


def delete_database():
    """Delete Unicode database"""
    Database().delete()
    return 0


def database_info():
    """Show database information"""
    print(Database().get_path())
    return 0
