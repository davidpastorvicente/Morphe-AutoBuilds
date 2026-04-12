"""APKMirror scraper: resolve download links and latest versions."""

import logging
import re
from urllib.parse import quote

from bs4 import BeautifulSoup
from curl_cffi.requests import RequestsError

from src import session, utils

BASE_URL = "https://www.apkmirror.com"


def _absolute_url(href: str) -> str:
    """Convert a relative href to an absolute APKMirror URL."""
    return href if href.startswith("http") else BASE_URL + href


# ---------------------------------------------------------------------------
# Build-number helpers
# ---------------------------------------------------------------------------

def _parse_build_from_version(version: str) -> tuple[str, str | None, str | None]:
    """Strip an inline build number from *version* and return
    ``(clean_version, build_number, build_format)``.
    """
    match = re.search(r'\((\d+)\)$', version)
    if match:
        return version[:match.start()], match.group(1), 'parentheses'

    match = re.search(r'\s+build\s+(\d+)$', version, re.IGNORECASE)
    if match:
        return version[:match.start()], match.group(1), 'build_suffix'

    return version, None, None


def get_build_number_for_version(
    version: str, config: dict
) -> tuple[str | None, str | None]:
    """Fetch the lowest build number for *version* from APKMirror."""
    try:
        main_url = f"{BASE_URL}/apk/{config['org']}/{config['name']}/"
        response = session.get(main_url)
        if response.status_code != 200:
            return None, None

        soup = BeautifulSoup(response.content, "html.parser")
        builds_found: list[tuple[str, str]] = []
        escaped = re.escape(version)
        for link in soup.find_all('a', href=True):
            text = link.get_text()
            if version not in text:
                continue
            m = re.search(rf'{escaped}\((\d+)\)', text)
            if m:
                builds_found.append((m.group(1), 'parentheses'))
            m = re.search(
                rf'{escaped}\s+build\s+(\d+)', text, re.IGNORECASE
            )
            if m:
                builds_found.append((m.group(1), 'build_suffix'))

        if builds_found:
            builds_found.sort(key=lambda x: int(x[0]))
            return builds_found[0]
    except (RequestsError, KeyError):
        logging.debug("Could not fetch build number for %s", version)
    return None, None


# ---------------------------------------------------------------------------
# URL-pattern generation
# ---------------------------------------------------------------------------

def _build_version_slug(
    version_parts: list[str],
    count: int,
    build_number: str | None,
    build_format: str | None,
) -> str:
    """Return the dash-separated version slug used in APKMirror URLs."""
    slug = "-".join(version_parts[:count])
    if build_number and count == len(version_parts):
        if build_format == 'build_suffix':
            slug = slug + "-build-" + build_number
        else:
            parts = list(version_parts[:count])
            parts[-1] = parts[-1] + build_number
            slug = "-".join(parts)
    return slug


def _generate_url_patterns(
    config: dict,
    release_name: str,
    ver_slug: str,
) -> list[str]:
    """Return deduplicated candidate release-page URLs in priority order."""
    enc_release = quote(release_name, safe='')
    enc_name = quote(config['name'], safe='')
    org = config['org']
    base = f"{BASE_URL}/apk/{org}/{enc_name}"
    patterns: list[str] = [
        f"{base}/{enc_release}-{ver_slug}-release/",
    ]
    if release_name != config['name']:
        patterns.append(
            f"{base}/{enc_name}-{ver_slug}-release/"
        )
    patterns.append(f"{base}/{enc_release}-{ver_slug}/")
    if release_name != config['name']:
        patterns.append(f"{base}/{enc_name}-{ver_slug}/")
    return list(dict.fromkeys(patterns))


# ---------------------------------------------------------------------------
# Page-validation helpers
# ---------------------------------------------------------------------------

def _version_checks(
    version: str,
    ver_slug: str,
    version_parts: list[str],
    part_count: int,
    build_number: str | None,
    build_format: str | None,
) -> list[str]:
    """Build the list of strings we accept as proof that the page
    matches the requested version."""
    checks = [
        version,
        version.replace('.', '-'),
        ver_slug,
        ".".join(version_parts[:part_count]),
    ]
    if build_number:
        if build_format == 'build_suffix':
            checks.append(f"{version} build {build_number}")
            checks.append(
                f"{version.replace('.', '-')}-build-{build_number}"
            )
        else:
            checks.append(f"{version}({build_number})")
    return checks


def _is_version_page(
    soup: BeautifulSoup,
    version: str,
    ver_slug: str,
    version_parts: list[str],
    part_count: int,
    build_number: str | None,
    build_format: str | None,
) -> bool:
    """Return *True* when *soup* belongs to the requested version."""
    checks = _version_checks(
        version, ver_slug, version_parts, part_count,
        build_number, build_format,
    )
    page_text = soup.get_text()
    for chk in checks:
        if chk and chk in page_text:
            if chk in (
                version, version.replace('.', '-'), ver_slug
            ):
                return True

    for heading in soup.find_all(['h1', 'h2', 'h3']):
        for chk in checks:
            if chk and chk in heading.get_text():
                return True

    title_tag = soup.find('title')
    if title_tag:
        title_text = title_tag.get_text()
        for chk in checks:
            if chk and chk in title_text:
                return True

    return False


# ---------------------------------------------------------------------------
# Variant finder
# ---------------------------------------------------------------------------

def _find_variant_url(
    soup: BeautifulSoup,
    version: str,
    target_arch: str,
    target_dpi: str,
    requested_type: str,
    app_name: str,
) -> str | None:
    """Locate the download-page URL for the best matching variant row."""

    def _row_matches(row_text: str) -> bool:
        normalized = " ".join(row_text.split())
        return (
            (not target_arch or target_arch in normalized)
            and (not target_dpi or target_dpi in normalized)
        )

    rows = soup.find_all('div', class_='table-row headerFont')

    for row in rows:
        row_text = row.get_text()
        if version not in row_text and version.replace('.', '-') not in row_text:
            continue
        if _row_matches(row_text):
            sub = row.find('a', class_='accent_color')
            if sub:
                return BASE_URL + sub['href']

    for row in rows:
        row_text = row.get_text()
        if not _row_matches(row_text):
            continue
        if re.search(r'\d+(\.\d+)+', row_text):
            sub = row.find('a', class_='accent_color')
            if sub:
                match = re.search(r'(\d+(\.\d+)+(\.\w+)*)', row_text)
                if match:
                    logging.warning(
                        "Using variant %s (criteria match)",
                        match.group(1),
                    )
                return BASE_URL + sub['href']

    logging.error(
        "No variant found for %s %s with criteria "
        "[type=%r, arch=%r, dpi=%r]",
        app_name, version, requested_type, target_arch, target_dpi,
    )
    logging.debug("Found %d rows total", len(rows))
    for idx, row in enumerate(rows[:5]):
        logging.debug("Row %d: %s...", idx, row.get_text()[:100])
    return None


# ---------------------------------------------------------------------------
# Download-flow helpers
# ---------------------------------------------------------------------------

def _find_release_link(
    soup: BeautifulSoup, version: str
) -> str | None:
    """Find a release-page anchor that matches *version*."""
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        classes = anchor.get("class", [])
        text = " ".join(anchor.get_text(" ", strip=True).split())
        if "android-apk-download" not in href:
            continue
        if version not in text and version not in href:
            continue
        if {"downloadLink", "fontBlack", "accent_color"} & set(classes):
            return _absolute_url(href)
    return None


def _find_direct_download(
    soup: BeautifulSoup, requested_type: str
) -> str | None:
    """Locate a direct-download link on *soup*."""
    button = soup.find("a", id="download-link")
    if button and button.get("href"):
        return _absolute_url(button["href"])

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        classes = anchor.get("class", [])
        rel = anchor.get("rel", [])
        text = " ".join(anchor.get_text(" ", strip=True).split())
        if "download.php" in href:
            return _absolute_url(href)
        if "nofollow" in rel and "/download/" in href:
            return _absolute_url(href)
        if "downloadButton" not in classes:
            continue
        if "/download/" in href or "Download APK" in text:
            if (
                requested_type != "BUNDLE"
                or "Bundle" in text
                or "/download/" in href
            ):
                return _absolute_url(href)
    return None


def _follow_download_chain(
    download_page_url: str,
    version: str,
    requested_type: str,
) -> str | None:
    """Navigate from the variant page through intermediate pages
    and return the final direct-download URL."""
    response = session.get(download_page_url)
    response.raise_for_status()
    csize = len(response.content)
    logging.info(
        "URL:%s [%d/%d] -> Variant Page", response.url, csize, csize
    )
    soup = BeautifulSoup(response.content, "html.parser")

    url = _resolve_keyed_download(soup, requested_type)
    if url:
        return url

    release_url = _find_release_link(soup, version)
    if release_url:
        response = session.get(release_url)
        response.raise_for_status()
        csize = len(response.content)
        logging.info(
            "URL:%s [%d/%d] -> Download Page",
            response.url, csize, csize,
        )
        soup = BeautifulSoup(response.content, "html.parser")
        url = _resolve_keyed_download(soup, requested_type)
        if url:
            return url

    return None


def _resolve_keyed_download(
    soup: BeautifulSoup, requested_type: str
) -> str | None:
    """Handle the optional ``/download/?key=`` redirect."""
    url = _find_direct_download(soup, requested_type)
    if not url:
        return None
    if "/download/?key=" in url:
        response = session.get(url)
        response.raise_for_status()
        csize = len(response.content)
        logging.info(
            "URL:%s [%d/%d] -> Keyed Download Page",
            response.url, csize, csize,
        )
        soup = BeautifulSoup(response.content, "html.parser")
        url = _find_direct_download(soup, requested_type)
    return url


# ---------------------------------------------------------------------------
# Release-page search
# ---------------------------------------------------------------------------

def _search_release_pages(
    version: str,
    config: dict,
    build_number: str | None,
    build_format: str | None,
) -> tuple[BeautifulSoup | None, bool]:
    """Walk version-part truncations and URL patterns to locate the
    correct release page.  Returns ``(soup, is_exact_match)``."""
    version_parts = version.split('.')
    release_name = config.get('releasePrefix', config['name'])
    found_soup: BeautifulSoup | None = None
    correct = False

    for i in range(len(version_parts), 0, -1):
        ver_slug = _build_version_slug(
            version_parts, i, build_number, build_format
        )
        urls = _generate_url_patterns(config, release_name, ver_slug)

        for url in urls:
            logging.info("Checking potential release URL: %s", url)
            try:
                response = session.get(url)
            except RequestsError as exc:
                logging.warning(
                    "Error checking %s: %.50s", url, str(exc)
                )
                continue

            if response.status_code == 404:
                logging.info("URL not found (404): %s", url)
                continue
            if response.status_code != 200:
                logging.warning(
                    "URL %s returned status %s",
                    url, response.status_code,
                )
                continue

            soup = BeautifulSoup(response.content, "html.parser")
            if _is_version_page(
                soup, version, ver_slug, version_parts, i,
                build_number, build_format,
            ):
                logging.info(
                    "✓ Correct version page found: %s", response.url
                )
                return soup, True

            logging.warning(
                "Page found but not for version %s: %s", version, url
            )
            if found_soup is None:
                found_soup = soup
                logging.warning(
                    "Saved as fallback page (may list multiple versions)"
                )

        if correct:
            break

    return found_soup, False


# ===================================================================
# Public API
# ===================================================================

def get_download_link(
    version: str,
    _app_name: str,
    config: dict,
    arch: str = None,
) -> str | None:
    """Return a direct APKMirror download URL for the requested app
    *version*, or *None* when no suitable link can be found."""
    target_arch = arch if arch else config.get('arch', 'universal')
    target_dpi = config.get('dpi', '')
    requested_type = config.get('type', '')

    version, build_number, build_format = _parse_build_from_version(
        version
    )
    if not build_number:
        build_number, build_format = get_build_number_for_version(
            version, config
        )
        if build_number:
            logging.info(
                "Found build number %s for version %s (format: %s)",
                build_number, version, build_format,
            )

    found_soup, exact = _search_release_pages(
        version, config, build_number, build_format
    )

    if not exact and found_soup:
        logging.warning(
            "Using fallback page for %s %s "
            "(may contain multiple versions)",
            _app_name, version,
        )
    if not found_soup:
        logging.error(
            "Could not find any release page for %s %s",
            _app_name, version,
        )
        return None

    download_page_url = _find_variant_url(
        found_soup, version, target_arch, target_dpi,
        requested_type, _app_name,
    )
    if not download_page_url:
        return None

    try:
        return _follow_download_chain(
            download_page_url, version, requested_type
        )
    except RequestsError as exc:
        logging.error("Error in download flow: %s", exc)
    return None


def get_latest_version(_app_name: str, config: dict) -> str | None:
    """Return the newest non-alpha/beta version string from APKMirror."""
    target_arch = config.get("arch", "")
    target_dpi = config.get("dpi", "")

    def extract_variant_versions(soup: BeautifulSoup) -> list[str]:
        versions: list[str] = []
        for row in soup.find_all("div", class_="table-row headerFont"):
            row_text = " ".join(row.get_text(" ", strip=True).split())
            lowered = row_text.lower()
            if (
                "latest:" not in lowered
                or "alpha" in lowered
                or "beta" in lowered
            ):
                continue
            if target_arch and target_arch not in row_text:
                continue
            if target_dpi and target_dpi not in row_text:
                continue
            latest_part = (
                row_text.split("Latest:", 1)[1]
                .split(" on ", 1)[0]
                .strip()
            )
            if latest_part:
                versions.append(latest_part)
        return versions

    def extract_versions(soup: BeautifulSoup) -> list[str]:
        versions: list[str] = []
        version_pattern = re.compile(
            r'\d+(\.\d+)*(-[a-zA-Z0-9]+(\.\d+)*)*'
        )
        app_path_prefix = f"/apk/{config['org']}/{config['name']}/"

        for row in soup.find_all("div", class_="appRow"):
            title = row.find("h5", class_="appRowTitle")
            link = title.find("a") if title else None
            href = link.get("href", "") if link else ""
            if not href.startswith(app_path_prefix):
                continue

            version_text = link.get_text(strip=True) if link else ""
            lowered = version_text.lower()
            if (
                not version_text
                or "alpha" in lowered
                or "beta" in lowered
            ):
                continue

            match = version_pattern.search(version_text)
            if not match:
                continue

            ver = match.group()
            ver_parts = ver.split('.')
            base_parts: list[str] = []
            for part in ver_parts:
                if part.isdigit():
                    base_parts.append(part)
                else:
                    break
            if not base_parts:
                continue

            parsed = ".".join(base_parts)
            bm = re.search(r'\((\d+)\)', version_text)
            if bm:
                parsed = f"{parsed}({bm.group(1)})"
            else:
                bm = re.search(
                    r'build\s+(\d+)', version_text, re.IGNORECASE
                )
                if bm:
                    parsed = f"{parsed} build {bm.group(1)}"

            versions.append(parsed)
        return versions

    main_url = f"{BASE_URL}/apk/{config['org']}/{config['name']}/"
    try:
        response = session.get(main_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        latest = utils.get_highest_version(
            extract_variant_versions(soup)
        )
        if latest:
            return latest
        latest = utils.get_highest_version(extract_versions(soup))
        if latest:
            return latest
    except (RequestsError, KeyError) as exc:
        logging.debug(
            "Could not fetch latest version from main app page: %s",
            exc,
        )

    url = f"{BASE_URL}/uploads/?appcategory={config['name']}"
    response = session.get(url)
    response.raise_for_status()
    csize = len(response.content)
    logging.info(
        "URL:%s [%d/%d] -> \"-\" [1]", response.url, csize, csize
    )
    soup = BeautifulSoup(response.content, "html.parser")

    latest = utils.get_highest_version(extract_versions(soup))
    if latest:
        return latest
    return None
