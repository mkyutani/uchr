import tempfile
import zipfile
from pathlib import Path
from typing import Tuple

import requests

from .errors import DownloadError

# Seconds to wait for connect / between bytes; unicode.org can stall.
HTTP_TIMEOUT = 60


def download_zip_file(url: str, target_filename: str) -> Tuple[bytes, str]:
    """Download a ZIP file and extract the specified file as bytes.

    Returns (data, final URL after redirects).
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "download.zip"
            res = requests.get(url, stream=True, timeout=HTTP_TIMEOUT)
            if res.status_code >= 400:
                raise DownloadError(f"HTTP error {res.status_code}: {url}")
            content_type = res.headers.get("Content-Type", "")
            if "application/zip" not in content_type:
                raise DownloadError(f"Invalid content type: {content_type}")
            with open(zip_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            with zipfile.ZipFile(zip_path, "r") as zip_file:
                return zip_file.read(target_filename), res.url
    except DownloadError:
        raise
    except Exception as e:
        raise DownloadError(f"Failed to download zip from {url}: {e}") from e
