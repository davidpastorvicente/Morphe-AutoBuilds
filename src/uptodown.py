"""Uptodown download source: version lookup and APK download link resolution."""

import logging

from bs4 import BeautifulSoup

from src import session


def get_latest_version(app_name: str, config: dict) -> str:
    """Return the latest version string from Uptodown."""
    possible_names = _generate_possible_names(config)
    logging.info("Trying %d possible Uptodown names for %s", len(possible_names), app_name)

    for uptodown_name in possible_names:
        url = f"https://{uptodown_name}.en.uptodown.com/android/versions"
        try:
            response = session.get(url)
            if response.status_code == 200:
                logging.info("Found: %s", response.url)
                soup = BeautifulSoup(response.content, "html.parser")
                version_spans = soup.select("#versions-items-list .version")
                versions = [span.text for span in version_spans]
                if versions:
                    highest = max(versions)
                    logging.info("Found version %s for %s", highest, app_name)
                    return highest
            elif response.status_code == 404:
                logging.debug("Not found: %s", url)
            else:
                response.raise_for_status()
        except Exception:
            logging.debug("Failed for %s", url)

    raise RuntimeError(f"Could not find Uptodown page for {app_name}")


def get_download_link(version: str, app_name: str, config: dict) -> str | None:
    """Resolve the direct download URL for *version* on Uptodown."""
    possible_names = _generate_possible_names(config)
    logging.info(
        "Searching %d possible Uptodown names for %s v%s",
        len(possible_names), app_name, version,
    )

    for uptodown_name in possible_names:
        site_base = f"https://{uptodown_name}.en.uptodown.com/android"
        try:
            response = session.get(f"{site_base}/versions")
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.content, "html.parser")
            data_code = soup.find("h1", id="detail-app-name")["data-code"]
            download_url = _search_version_pages(
                site_base, data_code, version,
            )
            if download_url:
                return download_url
        except Exception:
            logging.debug("Pattern %s failed", uptodown_name)

    logging.error("Version %s not found for %s", version, app_name)
    return None


def _search_version_pages(
    site_base: str, data_code: str, version: str,
) -> str | None:
    """Paginate through Uptodown version API pages looking for *version*."""
    page = 1
    while True:
        response = session.get(f"{site_base}/apps/{data_code}/versions/{page}")
        response.raise_for_status()
        version_data = response.json().get("data", [])

        if not version_data:
            break

        for entry in version_data:
            if entry["version"] == version:
                url = _resolve_entry_download(entry)
                if url:
                    return url

        if all(entry["version"] < version for entry in version_data):
            break
        page += 1

    return None


def _resolve_entry_download(entry: dict) -> str | None:
    """Follow the Uptodown version entry to its final download URL."""
    parts = entry["versionURL"]
    version_url = f"{parts['url']}/{parts['extraURL']}/{parts['versionID']}"
    version_page = session.get(version_url)
    version_page.raise_for_status()
    soup = BeautifulSoup(version_page.content, "html.parser")

    button = soup.find("button", id="detail-download-button")
    if not button:
        return None

    onclick = button.get("onclick", "")
    if onclick and "download-link-deeplink" in onclick:
        version_url += "-x"
        version_page = session.get(version_url)
        version_page.raise_for_status()
        soup = BeautifulSoup(version_page.content, "html.parser")
        button = soup.find("button", id="detail-download-button")

    if button and "data-url" in button.attrs:
        return f"https://dw.uptodown.com/dwn/{button['data-url']}"
    return None


def _generate_possible_names(config: dict) -> list[str]:
    """Generate all plausible Uptodown URL slug variants from *config*."""
    app_name = config.get("name", "")
    package = config.get("package", "")

    names: set[str] = set()

    # Basic variations
    names.update([
        app_name,
        app_name.replace("-", ""),
        app_name.replace("-plus", "plus"),
        app_name.replace("-", "_"),
    ])

    # Package-based variations
    package_dash = package.replace(".", "-")
    names.add(package_dash)

    if package.startswith("com."):
        names.add(package_dash)
        names.add(package_dash.replace("com-", ""))

        parts = package.split(".")
        if len(parts) >= 2:
            names.update([
                f"com-{parts[1]}",
                f"com-{parts[1]}-{parts[-1]}",
                parts[1],
                parts[-1],
            ])
            if len(parts) >= 3:
                names.update([
                    f"com-{parts[1]}{parts[2]}",
                    f"com-{parts[1]}{parts[2]}-mea",
                    f"com-{'-'.join(parts[1:])}",
                ])

    # Suffix combinations
    suffixes = [
        "", "-android", "-mobile", "-mea", "-plus",
        "-pro", "-lite", "-hd", "-apk",
    ]
    for suffix in suffixes:
        names.add(app_name + suffix)
        names.add(package_dash + suffix)

    # Company / app combinations
    parts = package.split(".")
    if len(parts) >= 2:
        company = parts[1]
        app_basename = parts[-1]
        names.update([
            f"{company}-{app_basename}",
            f"{company}-{app_name}",
        ])
        if "adobe" in package.lower():
            names.update([
                f"adobe-{app_basename}",
                f"adobe-{app_basename}-mobile",
            ])

    # Keyword stripping
    for word in ("plus", "pro", "lite", "free", "paid", "mod"):
        if word in app_name:
            clean = app_name.replace(f"-{word}", "").replace(word, "")
            names.update([clean, f"{clean}-{word}"])

    # Ensure all lowercase
    names.update({n.lower() for n in names})

    return [n for n in names if n and len(n) > 1]
