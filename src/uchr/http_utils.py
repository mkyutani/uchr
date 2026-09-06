import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional

import requests

from .errors import DownloadError


def download_text_file(
    url: str, expected_content_type: str = "text/plain"
) -> Optional[List[str]]:
    """Download a text file and return its lines as a list of strings."""
    try:
        res = requests.get(url)
        if res.status_code >= 400:
            raise DownloadError(f"HTTP error {res.status_code}: {url}")
        content_type = res.headers.get("Content-Type", "")
        if expected_content_type not in content_type:
            raise DownloadError(f"Invalid content type: {content_type}")
        return res.text.splitlines()
    except DownloadError:
        raise
    except Exception as e:
        raise DownloadError(f"Failed to download from {url}: {e}") from e


def download_zip_file(url: str, target_filename: str) -> Optional[bytes]:
    """Download a ZIP file and extract the specified file as bytes."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "download.zip"
            res = requests.get(url, stream=True)
            if res.status_code >= 400:
                raise DownloadError(f"HTTP error {res.status_code}: {url}")
            content_type = res.headers.get("Content-Type", "")
            if "application/zip" not in content_type:
                raise DownloadError(f"Invalid content type: {content_type}")
            with open(zip_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
            with zipfile.ZipFile(zip_path, "r") as zip_file:
                return zip_file.read(target_filename)
    except DownloadError:
        raise
    except Exception as e:
        raise DownloadError(f"Failed to download zip from {url}: {e}") from e
