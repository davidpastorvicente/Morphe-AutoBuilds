"""APKPure download source: version lookup and APK download link resolution."""

import logging

from bs4 import BeautifulSoup
from requests.exceptions import RequestException

from src import session

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://apkpure.net/",
}


def get_latest_version(_app_name: str, config: dict) -> str | None:
    """Return the latest version string from APKPure, or ``None``."""
    url = (
        f"https://apkpure.net/{config['name']}/"
        f"{config['package']}/versions"
    )

    try:
        response = session.get(url, headers=HEADERS)
        response.raise_for_status()

        logging.info(
            "URL:%s [%d/%d] -> \"-\" [1]",
            response.url,
            len(response.content),
            len(response.content),
        )

        soup = BeautifulSoup(response.content, "html.parser")
        version_info = soup.find("div", class_="ver-top-down")

        if version_info and "data-dt-version" in version_info.attrs:
            return version_info["data-dt-version"]

    except RequestException as exc:
        logging.error(
            "Failed to fetch latest version for %s: %s", _app_name, exc
        )

    return None


def get_download_link(version: str, _app_name: str, config: dict) -> str | None:
    """Resolve the direct download URL for a specific version on APKPure."""
    url = (
        f"https://apkpure.net/{config['name']}/"
        f"{config['package']}/download/{version}"
    )

    try:
        response = session.get(url, headers=HEADERS)
        response.raise_for_status()

        logging.info(
            "URL:%s [%d/%d] -> \"-\" [1]",
            response.url,
            len(response.content),
            len(response.content),
        )

        soup = BeautifulSoup(response.content, "html.parser")
        download_link = soup.find("a", id="download_link")
        if download_link:
            return download_link["href"]

    except RequestException as exc:
        logging.error(
            "Failed to fetch download link for %s v%s: %s",
            _app_name, version, exc,
        )

    return None
