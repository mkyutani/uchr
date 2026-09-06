#!/usr/bin/env python3

import io
import re
import sqlite3
import sys
import xml.etree.ElementTree as et
from pathlib import Path
from urllib.parse import urlparse

import requests

from .db import AutoID, Connection, Cursor, Database
from .errors import DownloadError
from .http_utils import download_zip_file
from .unicode_source import (
    check_version_status,
    emoji_urls,
    is_draft_url,
    list_published_versions,
    resolve_latest_version,
    ucd_zip_url,
)

namespace = "{http://www.unicode.org/ns/2003/ucd/1.0}"
tag_ucd = namespace + "ucd"
tag_description = namespace + "description"
tag_repertoire = namespace + "repertoire"
tag_char = namespace + "char"
tag_noncharacter = namespace + "noncharacter"
tag_reserved = namespace + "reserved"
tag_surrogate = namespace + "surrogate"
tag_name_alias = namespace + "name-alias"


def download_ucd(url):
    ucd_zip_url_path = Path(urlparse(url)[2])
    ucd_xml_filename = ucd_zip_url_path.with_suffix(".xml").name

    print(f"Downloading {url} ...", file=sys.stderr)
    try:
        xml_list = download_zip_file(url, ucd_xml_filename)
        print("Extracted unicode data xml", file=sys.stderr)
        return xml_list
    except DownloadError as e:
        print(f"Failed to download UCD: {e}", file=sys.stderr)
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


def store_ucd(xml_list, version, autoincrement_id):
    if not xml_list:
        return 0

    root = et.parse(io.BytesIO(xml_list)).getroot()
    if root.tag != tag_ucd:
        print(f"Unexpected XML scheme: {root.tag}", file=sys.stderr)
        return 0

    repertoire = root.find(tag_repertoire)

    with Connection() as conn:
        with Cursor(conn) as cur:
            count = 0
            for char in repertoire:
                code_range = get_ucd_char_cp(char)
                for code in code_range:
                    value_code = code
                    value_code_text = f"{value_code:X}"
                    name = get_name(char)
                    if not name:
                        print(f"Found no character: {code:X}", file=sys.stderr)
                        continue
                    detail = get_detail(char, name)

                    try:
                        value_char = None if code == 0 else str(chr(code))
                    except ValueError:
                        print(f"Invalid character {code:X} ({name})", file=sys.stderr)
                        continue

                    block = char.attrib.get("blk")
                    if not block:
                        print(f"No block name: {code:X}", file=sys.stderr)
                        block = "(None)"

                    id = autoincrement_id.next()
                    cur.execute(
                        "insert into char(id, name, detail, codetext, char, block, version) "
                        "values(?, ?, ?, ?, ?, ?, ?)",
                        (id, name, detail, value_code_text, value_char, block, version),
                    )
                    cur.execute(
                        "insert into codepoint(char, seq, code) values(?, ?, ?)",
                        (id, 1, value_code),
                    )
                    count = count + 1

            conn.commit()
            print(f"Stored {count} characters for version {version}", file=sys.stderr)
            return count


def download_emoji_pair(version):
    """Probe candidate emoji URL layouts for `version` and return the lines
    of (sequences, zwj_sequences) from whichever candidate succeeds."""
    for sequences_url, zwj_url in emoji_urls(version):
        try:
            res = requests.get(sequences_url)
            if res.status_code != 200:
                continue
            sequences = res.text.splitlines()
            zwj_res = requests.get(zwj_url)
            zwj_sequences = (
                zwj_res.text.splitlines() if zwj_res.status_code == 200 else []
            )
            return sequences, zwj_sequences
        except Exception:
            continue
    print(f"Failed to find emoji data for version {version}", file=sys.stderr)
    return None, None


def store_emoji(emoji_sequences, version, autoincrement_id):
    if not emoji_sequences:
        return 0

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
                if not emoji:
                    continue
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

                for code in cp_list:
                    if type(code) is int:
                        value_code_text = f"{code:X}"
                        value_char = chr(code)
                    else:
                        value_code_text = emoji_codes
                        value_char = "".join(chr(c) for c in code)

                    try:
                        id = autoincrement_id.next()
                        cur.execute(
                            "insert into char(id, name, codetext, char, block, version) "
                            "values(?, ?, ?, ?, ?, ?)",
                            (
                                id,
                                emoji_name,
                                value_code_text,
                                value_char,
                                emoji_type,
                                version,
                            ),
                        )
                        if type(code) is int:
                            cur.execute(
                                "insert into codepoint(char, seq, code) values(?, ?, ?)",
                                (id, 1, code),
                            )
                        else:
                            for i, c in enumerate(code):
                                cur.execute(
                                    "insert into codepoint(char, seq, code) "
                                    "values(?, ?, ?)",
                                    (id, i, c),
                                )
                        count = count + 1
                    except sqlite3.IntegrityError:
                        print(
                            f"Already registered: {value_code_text} {emoji_name}",
                            file=sys.stderr,
                        )

            conn.commit()
            print(
                f"Stored {count} emoji characters for version {version}",
                file=sys.stderr,
            )
            return count


def resolve_search_version(requested_version):
    """Resolve which version `search`/`normalize` should query.

    - explicit version requested but not stored locally -> error (caller
      should tell the user to run `db update --version X.Y.Z`), since an
      explicit version might be a typo and silently fetching on a bad
      guess is the wrong failure mode.
    - no version requested and the DB doesn't exist yet (true first run)
      -> auto-fetch `latest` and use it, since there's no typo risk when
      no version was specified.
    - no version requested and the DB exists -> use current_version.
    """
    db = Database()
    db_existed = db.exists()

    if not db_existed and requested_version is None:
        print(
            "No local database found; fetching the latest Unicode version ...",
            file=sys.stderr,
        )
        if update_database(version=None) != 0:
            return None, "Error: failed to fetch initial database"
        db_existed = True

    if db_existed:
        # Ensure schema is current and any legacy (pre-version-column) rows
        # are migrated before querying — create() is idempotent.
        db.create()

    if requested_version is not None:
        if not db_existed or requested_version not in dict(db.local_versions()):
            return None, (
                f"Error: version {requested_version} is not stored locally. "
                f"Run 'uchr db update --version {requested_version}' first."
            )
        return requested_version, None

    current = db.get_current_version()
    if current is None:
        return None, ("Error: no current version set. Run 'uchr db update' first.")
    return current, None


def _next_autoincrement_id():
    with Connection() as conn:
        with Cursor(conn) as cur:
            cur.execute("select max(id) from char")
            (max_id,) = cur.fetchone()
    autoincrement_id = AutoID().init()
    autoincrement_id.value = (max_id or 0) + 1
    return autoincrement_id


def update_database(version=None):
    """Fetch a Unicode version into the DB and switch current_version to it.

    If `version` is omitted, resolve `latest` from unicode.org. If given
    explicitly and it turns out to be draft data, warn but proceed.
    """
    Database().create()

    if version is None:
        try:
            version, url = resolve_latest_version()
        except DownloadError as e:
            print(f"Failed to resolve latest version: {e}", file=sys.stderr)
            return 1
    else:
        url = ucd_zip_url(version)

    if is_draft_url(url):
        print(f"Warning: version {version} is unreleased draft data", file=sys.stderr)

    autoincrement_id = _next_autoincrement_id()

    xml_list = download_ucd(url)
    if xml_list is None:
        return 1
    char_count = store_ucd(xml_list, version, autoincrement_id)
    if char_count == 0:
        print(f"No characters stored for version {version}", file=sys.stderr)
        return 1

    sequences, zwj_sequences = download_emoji_pair(version)
    store_emoji(sequences, version, autoincrement_id)
    store_emoji(zwj_sequences, version, autoincrement_id)

    Database().set_current_version(version)
    print(f"Switched current version to {version}", file=sys.stderr)
    return 0


def use_version(version):
    """Switch current_version to a version already present locally."""
    db = Database()
    if db.exists():
        db.create()  # ensure schema is current / legacy rows migrated
    local = dict(db.local_versions())
    if version not in local:
        print(
            f"Error: version {version} is not stored locally. "
            f"Run 'uchr db update --version {version}' first.",
            file=sys.stderr,
        )
        return 1
    db.set_current_version(version)
    print(f"Switched current version to {version}", file=sys.stderr)
    return 0


def delete_version(version=None, delete_all=False):
    """Delete one version's data, or wipe the whole database file."""
    db = Database()
    if delete_all:
        db.delete_all()
        return 0

    if db.exists():
        db.create()  # ensure schema is current / legacy rows migrated
    deleted = db.delete_version(version)
    if deleted == 0:
        print(f"No data found for version {version}", file=sys.stderr)
        return 1
    print(f"Deleted version {version} ({deleted} rows)", file=sys.stderr)
    return 0


def _version_key(version):
    return tuple(int(p) for p in version.split("."))


def list_versions():
    """Print every version unicode.org publishes, each marked with its
    local/current/latest/draft status. Always hits the network fresh."""
    db = Database()
    db_existed = db.exists()
    if db_existed:
        db.create()  # ensure schema is current / legacy rows migrated
    local = dict(db.local_versions()) if db_existed else {}
    current = db.get_current_version() if db_existed else None

    try:
        published = list_published_versions()
    except DownloadError as e:
        print(f"Warning: could not reach unicode.org ({e})", file=sys.stderr)
        published = []

    try:
        latest, _ = resolve_latest_version()
    except DownloadError as e:
        print(f"Warning: could not resolve latest version ({e})", file=sys.stderr)
        latest = None

    all_versions = set(published) | set(local)
    if latest:
        all_versions.add(latest)

    for version in sorted(all_versions, key=_version_key):
        markers = []
        if version == current:
            markers.append("(current)")
        elif version in local:
            markers.append("(local)")
        if version == latest:
            markers.append("(latest)")
        elif latest and _version_key(version) > _version_key(latest):
            status = check_version_status(version)
            if status == "draft":
                markers.append("(draft)")

        row_count = local.get(version)
        suffix = f" [{row_count} rows]" if row_count is not None else ""
        marker_text = " " + " ".join(markers) if markers else ""
        print(f"{version}{marker_text}{suffix}")

    return 0
