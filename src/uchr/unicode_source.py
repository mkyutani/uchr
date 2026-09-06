"""Resolve Unicode versions and locate UCD/emoji source files on unicode.org.

Philosophy: don't pre-compute "what is the latest version" from a directory
listing or changelog text (fragile — unicode.org lists draft directories
too). Instead, always ask the question that actually matters: can we fetch
and build a DB from this URL? If a fetch succeeds, use it; if it turns out
to be draft data, say so, but the data is still valid.
"""

import re
from typing import List, Optional, Tuple

import requests

from .errors import DownloadError

UCD_LATEST_URL = "https://www.unicode.org/Public/UCD/latest/ucdxml/ucd.all.flat.zip"
PUBLIC_LATEST_URL = "https://www.unicode.org/Public/latest/ucdxml/ucd.all.flat.zip"
PUBLIC_INDEX_URL = "https://www.unicode.org/Public/"

_VERSION_IN_URL = re.compile(r"/Public/(\d+\.\d+\.\d+)/")
_VERSION_DIR = re.compile(r'href="(\d+\.\d+\.\d+)/"')


def ucd_zip_url(version: str) -> str:
    return f"https://www.unicode.org/Public/{version}/ucdxml/ucd.all.flat.zip"


def resolve_latest_version() -> Tuple[str, str]:
    """Resolve the current released version by following the `latest` redirect.

    Returns (version, resolved_zip_url). Raises DownloadError if the version
    can't be determined from the response.
    """
    try:
        res = requests.get(PUBLIC_LATEST_URL, stream=True)
        res.close()
    except Exception as e:
        raise DownloadError(f"Failed to resolve latest version: {e}") from e

    m = _VERSION_IN_URL.search(res.url)
    if not m:
        raise DownloadError(f"Could not determine version from {res.url}")
    return m.group(1), res.url


def is_draft_url(url: str) -> bool:
    return "draft" in url


def list_published_versions() -> List[str]:
    """Scrape unicode.org/Public/ for all published Unicode versions (X.Y.Z)."""
    try:
        res = requests.get(PUBLIC_INDEX_URL)
        res.raise_for_status()
    except Exception as e:
        raise DownloadError(f"Failed to list published versions: {e}") from e

    versions = _VERSION_DIR.findall(res.text)
    return sorted(set(versions), key=lambda v: tuple(int(p) for p in v.split(".")))


def check_version_status(version: str) -> Optional[str]:
    """Check whether a version above `latest` is real or still a draft.

    Returns "draft" if the fetch redirects to draft data, "released" if it
    fetches cleanly without going through draft, or None if it can't be
    fetched at all.
    """
    try:
        res = requests.get(ucd_zip_url(version), stream=True)
        res.close()
    except Exception:
        return None

    if res.status_code != 200:
        return None
    return "draft" if is_draft_url(res.url) else "released"


def emoji_urls(version: str) -> List[str]:
    """Candidate (sequences_url, zwj_url) pairs to probe in order for a version.

    Unicode.org's emoji file layout has changed over time (verified cutover
    at 17.0.0: unified under the UCD version dir from 17.0.0 on; a separate
    `emoji/X.Y` dir — no patch component — before that). Rather than branch
    on a hardcoded version comparison, callers should try each candidate in
    order via GET (not HEAD — some unicode.org paths return 520 on HEAD)
    and use whichever succeeds. A future layout change just needs a new
    candidate appended here.
    """
    major, minor, _ = version.split(".")
    new_layout = f"https://www.unicode.org/Public/{version}/emoji"
    old_layout = f"https://www.unicode.org/Public/emoji/{major}.{minor}"
    return [
        (f"{new_layout}/emoji-sequences.txt", f"{new_layout}/emoji-zwj-sequences.txt"),
        (f"{old_layout}/emoji-sequences.txt", f"{old_layout}/emoji-zwj-sequences.txt"),
    ]
