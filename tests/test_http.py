"""Tests that downloads never use plain HTTP (no network access)."""

import io
import zipfile

import pytest
import requests

from uchr import cldr, http_utils, unicode_source
from uchr.errors import DownloadError

PUBLIC = "www.unicode.org/Public"
LATEST_ZIP = f"https://{PUBLIC}/latest/ucdxml/ucd.all.flat.zip"
ZIP_18 = f"{PUBLIC}/18.0.0/ucdxml/ucd.all.flat.zip"
ZIP_19 = f"{PUBLIC}/19.0.0/ucdxml/ucd.all.flat.zip"
DRAFT_ZIP = f"{PUBLIC}/draft/ucdxml/ucd.all.flat.zip"
CLDR_TAG = "https://github.com/unicode-org/cldr/releases/tag/"


def _zip_bytes(name, data):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, data)
    return buf.getvalue()


class FakeAdapter(requests.adapters.BaseAdapter):
    """Serve canned responses by URL and record every URL requested."""

    def __init__(self, routes):
        super().__init__()
        self.routes = routes
        self.requested = []

    def send(self, request, **kwargs):
        self.requested.append(request.url)
        if request.url not in self.routes:
            raise requests.ConnectionError(f"no route to {request.url}")
        status, headers, body = self.routes[request.url]
        res = requests.Response()
        res.status_code = status
        res.headers.update(headers)
        res.url = request.url
        res.request = request
        res.raw = io.BytesIO(body)
        return res

    def close(self):
        pass


@pytest.fixture
def serve(monkeypatch):
    """Install a FakeAdapter for both schemes; returns it for inspection."""

    def install(routes):
        adapter = FakeAdapter(routes)
        session = http_utils._HttpsOnlySession()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        monkeypatch.setattr(http_utils, "_session", session)
        return adapter

    return install


def redirect(location):
    return 302, {"Location": location}, b""


def test_latest_redirect_to_http_is_followed_over_https(serve):
    adapter = serve(
        {
            LATEST_ZIP: redirect(f"http://{ZIP_18}"),
            f"https://{ZIP_18}": (200, {"Content-Type": "application/zip"}, b""),
        }
    )

    version, url = unicode_source.resolve_latest_version()

    assert (version, url) == ("18.0.0", f"https://{ZIP_18}")
    assert adapter.requested == [LATEST_ZIP, f"https://{ZIP_18}"]


def test_zip_download_redirected_to_http_uses_https(serve):
    zip_data = _zip_bytes("ucd.all.flat.xml", b"<ucd/>")
    adapter = serve(
        {
            f"https://{ZIP_19}": redirect(f"http://{DRAFT_ZIP}"),
            f"https://{DRAFT_ZIP}": (
                200,
                {"Content-Type": "application/zip"},
                zip_data,
            ),
        }
    )

    data, final_url = http_utils.download_zip_file(
        f"https://{ZIP_19}", "ucd.all.flat.xml"
    )

    assert data == b"<ucd/>"
    assert final_url == f"https://{DRAFT_ZIP}"
    assert all(u.startswith("https://") for u in adapter.requested)


def test_draft_status_check_uses_https(serve):
    adapter = serve(
        {
            f"https://{ZIP_19}": redirect(f"http://{DRAFT_ZIP}"),
            f"https://{DRAFT_ZIP}": (200, {}, b""),
        }
    )

    assert unicode_source.check_version_status("19.0.0") == "draft"
    assert all(u.startswith("https://") for u in adapter.requested)


def test_no_fallback_to_http_when_https_is_unavailable(serve):
    # Only the http:// target exists; the upgraded https:// request fails.
    adapter = serve(
        {
            LATEST_ZIP: redirect(f"http://{ZIP_18}"),
            f"http://{ZIP_18}": (200, {"Content-Type": "application/zip"}, b""),
        }
    )

    with pytest.raises(DownloadError):
        unicode_source.resolve_latest_version()
    assert not any(u.startswith("http://") for u in adapter.requested)


def test_http_get_upgrades_an_http_url(serve):
    adapter = serve({f"https://{PUBLIC}/": (200, {}, b"index")})

    assert http_utils.http_get(f"http://{PUBLIC}/").text == "index"
    assert adapter.requested == [f"https://{PUBLIC}/"]


@pytest.mark.parametrize(
    "tag, release", [("release-48-2", "48.2"), ("release-49", "49")]
)
def test_latest_cldr_release_is_read_from_redirect(serve, tag, release):
    serve(
        {
            cldr.LATEST_RELEASE_URL: redirect(CLDR_TAG + tag),
            CLDR_TAG + tag: (200, {}, b""),
        }
    )

    assert cldr.resolve_latest_release() == release


def test_unexpected_cldr_tag_is_an_error(serve):
    tag = "release-49-beta3"
    serve(
        {
            cldr.LATEST_RELEASE_URL: redirect(CLDR_TAG + tag),
            CLDR_TAG + tag: (200, {}, b""),
        }
    )

    with pytest.raises(DownloadError, match="Could not determine CLDR release"):
        cldr.resolve_latest_release()
