"""Fetch CLDR emoji annotations, the keywords behind related-name search.

CLDR keywords are not tied to a Unicode version, so one set is stored and
shared by every version in the DB. `db update` follows the latest CLDR
release, the same way it follows the latest Unicode version.
"""

import re
import sys
from xml.etree import ElementTree

from .errors import DownloadError

# GitHub redirects this to the newest final release (never an alpha or
# beta), e.g. .../releases/tag/release-48-2 for CLDR 48.2.
LATEST_RELEASE_URL = "https://github.com/unicode-org/cldr/releases/latest"
_RELEASE_TAG = re.compile(r"/releases/tag/release-(\d+(?:-\d+)*)$")

# Used only when the latest release can't be resolved and no keywords are
# stored yet, so a change on GitHub's side doesn't leave the DB without any.
FALLBACK_RELEASE = "48.2"

# CLDR writes emoji without the emoji presentation selector, while the
# emoji sequence files keep it, so keys are compared with FE0F removed.
VARIATION_SELECTOR_16 = "\ufe0f"


def strip_vs16(text):
    return text.replace(VARIATION_SELECTOR_16, "")


def resolve_latest_release():
    """Return the latest CLDR release (e.g. "48.2") by following GitHub's
    `latest` redirect. Raises DownloadError if it can't be determined."""
    # Imported here: search needs only strip_vs16, and requests is slow to
    # import.
    from .http_utils import http_get

    try:
        res = http_get(LATEST_RELEASE_URL, stream=True)
        res.close()
    except Exception as e:
        raise DownloadError(f"Failed to resolve latest CLDR release: {e}") from e
    if res.status_code != 200:
        raise DownloadError(f"HTTP error {res.status_code}: {LATEST_RELEASE_URL}")
    m = _RELEASE_TAG.search(res.url)
    if not m:
        raise DownloadError(f"Could not determine CLDR release from {res.url}")
    return m.group(1).replace("-", ".")


def annotations_url(release):
    tag = "release-" + release.replace(".", "-")
    return (
        f"https://raw.githubusercontent.com/unicode-org/cldr/{tag}"
        "/common/annotations/en.xml"
    )


def download_annotations(release):
    """Return the annotations XML of a CLDR release as bytes."""
    from .http_utils import http_get

    url = annotations_url(release)
    print(f"Downloading {url} ...", file=sys.stderr)
    try:
        res = http_get(url)
    except Exception as e:
        raise DownloadError(f"Failed to download {url}: {e}") from e
    if res.status_code != 200:
        raise DownloadError(f"HTTP error {res.status_code}: {url}")
    return res.content


def parse_annotations(xml):
    """Return {emoji without FE0F: set of lowercase keywords}. The `tts`
    entries are spoken names, not keywords, and are skipped."""
    keywords = {}
    for annotation in ElementTree.fromstring(xml).iter("annotation"):
        if annotation.attrib.get("type") == "tts" or not annotation.text:
            continue
        words = {w.strip().lower() for w in annotation.text.split("|")} - {""}
        if words:
            char = strip_vs16(annotation.attrib["cp"])
            keywords.setdefault(char, set()).update(words)
    return keywords
