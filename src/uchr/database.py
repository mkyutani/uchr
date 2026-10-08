#!/usr/bin/env python3

import io
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

from .cldr import (
    FALLBACK_RELEASE,
    download_annotations,
    parse_annotations,
    resolve_latest_release,
)
from .db import Connection, Database, delete_version_rows, set_meta
from .errors import DatabaseError, DownloadError
from .http_utils import download_zip_file
from .unicode_source import (
    check_version_status,
    download_emoji_pair,
    is_draft_url,
    list_published_versions,
    resolve_latest_version,
    ucd_zip_url,
    version_key,
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
    """Return (xml bytes, final URL after redirects)."""
    ucd_zip_url_path = Path(urlparse(url)[2])
    ucd_xml_filename = ucd_zip_url_path.with_suffix(".xml").name

    print(f"Downloading {url} ...", file=sys.stderr)
    xml_list, final_url = download_zip_file(url, ucd_xml_filename)
    print("Extracted unicode data xml", file=sys.stderr)
    return xml_list, final_url


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

    return (int(first_cp, 16), int(last_cp, 16))


# Repertoire entries that are not characters: tag -> (summary label,
# per-range message shown with --verbose).
_SKIPPED_RANGES = {
    tag_reserved: ("reserved ranges", "Found reserved code(s)"),
    tag_noncharacter: ("noncharacter ranges", "Found non character code(s)"),
    tag_surrogate: ("surrogate ranges", "Found surrogate code(s)"),
}


def get_ucd_char_cp(char, skipped, verbose=False):
    """Return the code points of a <char> entry. Other entries (reserved,
    noncharacter, surrogate) return [] and are counted in `skipped`."""
    r = get_ucd_cp(char)
    if not r:
        return None
    first, last = r
    if char.tag == tag_char:
        return range(first, last + 1)

    code_range = f"{first:X}" if first == last else f"{first:X}-{last:X}"
    if char.tag not in _SKIPPED_RANGES:
        print(f"Found unknown tag: {char.tag} {code_range}", file=sys.stderr)
        return []
    label, message = _SKIPPED_RANGES[char.tag]
    skipped[label] += 1
    if verbose:
        print(f"{message}: {code_range}", file=sys.stderr)
    return []


def _skipped_summary(skipped):
    parts = [f"{n} {label}" for label, n in skipped.items() if n]
    return f" (skipped {', '.join(parts)})" if parts else ""


def get_name(char, code):
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
    name = "; ".join(value)
    # Names derived from the code point, like CJK UNIFIED IDEOGRAPH-4E00,
    # are written once for a whole range as "CJK UNIFIED IDEOGRAPH-#".
    if name.endswith("-#"):
        name = name[:-1] + f"{code:X}"
    return name


def get_detail(char, name):
    definition = char.attrib.get("kDefinition")
    if definition and len(definition) > 0:
        return "; ".join([name, definition.upper()])
    else:
        return name


def insert_char(conn, name, detail, codetext, char, block, version, codes):
    """Insert one char row and its codepoint rows; return the new char id."""
    char_id = conn.execute(
        "insert into char(name, detail, codetext, char, block, version) "
        "values(?, ?, ?, ?, ?, ?)",
        (name, detail, codetext, char, block, version),
    ).lastrowid
    conn.executemany(
        "insert into codepoint(char, seq, code) values(?, ?, ?)",
        [(char_id, seq, code) for seq, code in enumerate(codes)],
    )
    return char_id


def store_ucd(conn, xml_list, version, verbose=False):
    """Store UCD characters for `version`; the caller owns the transaction.

    Code points without a name (mostly Private Use) and reserved,
    noncharacter and surrogate ranges are skipped and reported as counts;
    `verbose` also prints each one."""
    root = ElementTree.parse(io.BytesIO(xml_list)).getroot()
    if root.tag != tag_ucd:
        raise DatabaseError(f"Unexpected XML scheme: {root.tag}")

    repertoire = root.find(tag_repertoire)

    count = 0
    labels = [label for label, _ in _SKIPPED_RANGES.values()]
    skipped = dict.fromkeys(["unnamed code points", *labels], 0)
    for char in repertoire:
        code_range = get_ucd_char_cp(char, skipped, verbose)
        if not code_range:
            continue
        for code in code_range:
            name = get_name(char, code)
            if not name:
                skipped["unnamed code points"] += 1
                if verbose:
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

            insert_char(
                conn, name, detail, f"{code:X}", value_char, block, version, [code]
            )
            count = count + 1

    print(
        f"Stored {count} characters for version {version}" + _skipped_summary(skipped),
        file=sys.stderr,
    )
    return count


emoji_sequence_line_pattern = re.compile("^(.+);(.+);([^#]+)#")
emoji_sequence_cp_pattern = re.compile("([0-9A-Fa-f]+)")
emoji_sequence_continuous_pattern = re.compile(r"([0-9A-Fa-f]+)\.\.([0-9A-Fa-f]+)")


def parse_emoji_line(line):
    """Parse one emoji-sequences/zwj line into a list of
    (codetext, code point list, type, name); empty for comments/blanks."""
    if len(line) == 0 or line.startswith("#"):
        return []
    emoji = emoji_sequence_line_pattern.match(line)
    if not emoji:
        return []
    emoji_codes = emoji.group(1).strip()
    emoji_type = emoji.group(2).strip()
    emoji_name = emoji.group(3).strip()

    if re.fullmatch(emoji_sequence_cp_pattern, emoji_codes):
        code = int(emoji_codes, 16)
        return [(f"{code:X}", [code], emoji_type, emoji_name)]

    continuous = re.fullmatch(emoji_sequence_continuous_pattern, emoji_codes)
    if continuous:
        first = int(continuous.group(1), 16)
        last = int(continuous.group(2), 16)
        return [
            (f"{code:X}", [code], emoji_type, emoji_name)
            for code in range(first, last + 1)
        ]

    codes = [int(c, 16) for c in emoji_sequence_cp_pattern.findall(emoji_codes)]
    return [(emoji_codes, codes, emoji_type, emoji_name)]


def store_emoji(conn, emoji_sequences, version, verbose=False):
    """Store emoji sequences for `version`; the caller owns the transaction.

    Sequences already stored (single code points from the UCD) are skipped
    and reported as a count; `verbose` also prints each one."""
    count = 0
    duplicates = 0
    for line in emoji_sequences:
        for codetext, codes, emoji_type, emoji_name in parse_emoji_line(line):
            value_char = "".join(chr(c) for c in codes)
            try:
                insert_char(
                    conn,
                    emoji_name,
                    None,
                    codetext,
                    value_char,
                    emoji_type,
                    version,
                    codes,
                )
                count = count + 1
            except sqlite3.IntegrityError:
                duplicates += 1
                if verbose:
                    print(
                        f"Already registered: {codetext} {emoji_name}",
                        file=sys.stderr,
                    )

    summary = f" ({duplicates} already present)" if duplicates else ""
    print(
        f"Stored {count} emoji sequences for version {version}{summary}",
        file=sys.stderr,
    )
    return count


def resolve_search_version(requested_version):
    """Resolve which version `search` should query.

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

    if not db.exists() and requested_version is None:
        print(
            "No local database found; fetching the latest Unicode version ...",
            file=sys.stderr,
        )
        if update_database(version=None) != 0:
            return None, "Error: failed to fetch initial database"

    if not db.exists():
        return None, (
            f"Error: version {requested_version} is not stored locally. "
            f"Run 'uchr db update --version {requested_version}' first."
        )

    db.open_for_read()

    if requested_version is not None:
        if requested_version not in db.local_versions():
            return None, (
                f"Error: version {requested_version} is not stored locally. "
                f"Run 'uchr db update --version {requested_version}' first."
            )
        return requested_version, None

    current = db.get_current_version()
    if current is None:
        return None, "Error: no current version set. Run 'uchr db update' first."
    return current, None


def update_database(version=None, verbose=False):
    """Fetch a Unicode version into the DB and switch current_version to it.

    If `version` is omitted, resolve `latest` from unicode.org. A version
    that is already stored is not downloaded again, unless it was stored as
    draft data (drafts change until release). Draft data is accepted with a
    warning. Skipped entries are summarized; `verbose` lists each one.
    """
    db = Database()
    db.open_for_write()

    try:
        if version is None:
            version, url = resolve_latest_version()
        else:
            url = ucd_zip_url(version)

        stored = db.local_versions().get(version)
        if stored and not stored["draft"]:
            print(f"Version {version} is already stored", file=sys.stderr)
        else:
            xml_list, final_url = download_ucd(url)
            draft = is_draft_url(final_url)
            if draft:
                print(
                    f"Warning: version {version} is unreleased draft data",
                    file=sys.stderr,
                )
            sequences, zwj_sequences = download_emoji_pair(version)
            if sequences is None:
                print(
                    f"Warning: no emoji data published for version {version}",
                    file=sys.stderr,
                )
            _store_version(version, draft, xml_list, sequences, zwj_sequences, verbose)
    except DownloadError as e:
        print(f"Failed to fetch version {version or 'latest'}: {e}", file=sys.stderr)
        return 1

    db.set_current_version(version)
    print(f"Switched current version to {version}", file=sys.stderr)
    update_keywords(db)
    return 0


def update_keywords(db):
    """Store the CLDR keywords used for related-name search, unless the
    latest CLDR release is already stored. Keywords are optional, so a
    failure is a warning: name search still works, only without related
    results (or with the keywords stored before)."""
    stored = db.get_keyword_release()
    try:
        release = resolve_latest_release()
    except DownloadError as e:
        if stored:
            print(f"Warning: {e}; keeping CLDR {stored} keywords", file=sys.stderr)
            return
        release = FALLBACK_RELEASE
        print(f"Warning: {e}; using CLDR {release}", file=sys.stderr)
    if release == stored:
        return

    try:
        keywords = parse_annotations(download_annotations(release))
    except (DownloadError, ElementTree.ParseError) as e:
        print(f"Warning: failed to fetch CLDR keywords: {e}", file=sys.stderr)
        return
    if not keywords:
        print("Warning: no keywords found in CLDR annotations", file=sys.stderr)
        return
    with Connection() as conn:
        with conn:
            conn.execute("delete from keyword")
            conn.executemany(
                "insert into keyword(char, keyword) values(?, ?)",
                [(char, word) for char, words in keywords.items() for word in words],
            )
            set_meta(conn, "keyword_release", release)
    print(
        f"Stored keywords for {len(keywords)} emoji from CLDR {release}",
        file=sys.stderr,
    )


def _store_version(version, draft, xml_list, sequences, zwj_sequences, verbose):
    """Replace all rows of `version` in one transaction, so an interrupted
    update never leaves a half-stored version behind."""
    with Connection() as conn:
        with conn:
            delete_version_rows(conn, version)
            count = store_ucd(conn, xml_list, version, verbose)
            if count == 0:
                raise DatabaseError(f"No characters stored for version {version}")
            emoji_lines = [*(sequences or []), *(zwj_sequences or [])]
            if emoji_lines:
                count += store_emoji(conn, emoji_lines, version, verbose)
            conn.execute(
                "insert into version(version, draft, char_count) values(?, ?, ?)",
                (version, int(draft), count),
            )


def use_version(version):
    """Switch current_version to a version already present locally."""
    db = Database()
    db.open_for_write()
    if version not in db.local_versions():
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

    if not db.exists():
        print(f"No database file: {db.get_path()}", file=sys.stderr)
        return 1
    db.open_for_write()
    deleted = db.delete_version(version)
    if deleted == 0:
        print(f"No data found for version {version}", file=sys.stderr)
        return 1
    print(f"Deleted version {version} ({deleted} characters)", file=sys.stderr)
    return 0


def list_versions():
    """Print every version unicode.org publishes, each marked with its
    local/current/latest/draft status. Always hits the network fresh."""
    db = Database()
    local = {}
    current = None
    if db.exists():
        db.open_for_read()
        local = db.local_versions()
        current = db.get_current_version()

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

    for version in sorted(all_versions, key=version_key):
        markers = []
        if version == current:
            markers.append("(current)")
        elif version in local:
            markers.append("(local)")
        if version == latest:
            markers.append("(latest)")
        elif latest and version_key(version) > version_key(latest):
            if check_version_status(version) == "draft":
                markers.append("(draft)")

        stored = local.get(version)
        suffix = f" [{stored['chars']} chars]" if stored else ""
        marker_text = " " + " ".join(markers) if markers else ""
        print(f"{version}{marker_text}{suffix}")

    return 0
