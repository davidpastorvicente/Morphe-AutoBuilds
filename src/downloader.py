"""Download orchestration: resource fetching and platform-specific APK resolution."""

import importlib
import json
import logging
from pathlib import Path

from src import session, utils


def download_resource(url: str, name: str | None = None) -> Path:
    """Download a file from *url* and return the local ``Path``."""
    res = session.get(url, stream=True)
    res.raise_for_status()
    final_url = res.url

    if not name:
        name = utils.extract_filename(res, fallback_url=final_url)

    filepath = Path(name)
    total_size = int(res.headers.get("content-length", 0))
    downloaded_size = 0

    with filepath.open("wb") as fh:
        for chunk in res.iter_content(chunk_size=8192):
            if chunk:
                fh.write(chunk)
                downloaded_size += len(chunk)

    logging.info(
        'URL: %s [%d/%d] -> "%s" [1]',
        final_url, downloaded_size, total_size, filepath,
    )

    return filepath


def download_required(source: str) -> tuple[list[Path], str]:
    """Download CLI, patches, and integrations from a source definition file."""
    source_path = Path("sources") / f"{source}.json"
    with source_path.open(encoding="utf-8") as fh:
        repos_info = json.load(fh)

    if isinstance(repos_info, dict) and "bundle_url" in repos_info:
        return download_from_bundle(repos_info)

    name = repos_info[0]["name"]
    downloaded_files: list[Path] = []

    for repo_info in repos_info[1:]:
        user = repo_info["user"]
        repo = repo_info["repo"]
        tag = repo_info["tag"]
        release = utils.detect_github_release(user, repo, tag)

        if repo in ("morphe-patches", "morphe-cli"):
            _download_morphe_assets(release, downloaded_files)
        else:
            _download_generic_assets(release, downloaded_files)

    return downloaded_files, name


def _download_morphe_assets(release: dict, out: list[Path]) -> None:
    """Download .mpp patches or morphe-cli .jar assets."""
    for asset in release["assets"]:
        if asset["name"].endswith(".asc"):
            continue
        name = asset["name"]
        if name.endswith(".mpp") or (
            "morphe-cli" in name and name.endswith(".jar")
        ):
            out.append(download_resource(asset["browser_download_url"]))


def _download_generic_assets(release: dict, out: list[Path]) -> None:
    """Download all non-signature assets from a release."""
    for asset in release["assets"]:
        if asset["name"].endswith(".asc"):
            continue
        out.append(download_resource(asset["browser_download_url"]))


def download_from_bundle(bundle_info: dict) -> tuple[list[Path], str]:
    """Download resources from a bundle URL."""
    bundle_url = bundle_info["bundle_url"]
    name = bundle_info.get("name", "bundle-patches")

    logging.info("Downloading bundle from %s", bundle_url)

    with session.get(bundle_url) as res:
        res.raise_for_status()
        bundle_data = res.json()

    downloaded_files: list[Path] = []

    if "patches" in bundle_data:
        _download_bundle_parts(bundle_data, downloaded_files)

    _download_cli_for_bundle(downloaded_files)

    return downloaded_files, name


def _download_bundle_parts(bundle_data: dict, out: list[Path]) -> None:
    """Download patches and integrations from API v4 bundle format."""
    for patch in bundle_data.get("patches", []):
        if "url" in patch:
            out.append(download_resource(patch["url"]))
            logging.info("Downloaded patch: %s", patch.get("name", "unknown"))

    for integration in bundle_data.get("integrations", []):
        if "url" in integration:
            out.append(download_resource(integration["url"]))
            logging.info(
                "Downloaded integration: %s",
                integration.get("name", "unknown"),
            )


def _download_cli_for_bundle(out: list[Path]) -> None:
    """Attempt to download the latest ReVanced CLI for bundle builds."""
    try:
        cli_release = utils.detect_github_release(
            "revanced", "revanced-cli", "latest",
        )
        for asset in cli_release["assets"]:
            if asset["name"].endswith(".asc"):
                continue
            name = asset["name"]
            if name.endswith(".jar") and "cli" in name.lower():
                out.append(download_resource(asset["browser_download_url"]))
                logging.info("Downloaded ReVanced CLI")
                break
    except Exception:
        logging.warning("Could not download ReVanced CLI")


def _load_app_config(app_name: str) -> dict | None:
    """Load the unified app config from apps/{app_name}.json."""
    config_path = Path("apps") / f"{app_name}.json"
    if not config_path.exists():
        return None
    with config_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _platform_config(config: dict, platform: str) -> dict | None:
    """Return a flat config dict suitable for the given *platform* module.

    For apkmirror, merges the ``apkmirror`` sub-object with ``package``.
    For apkpure/uptodown/aptoide, uses ``{platform}_name`` override if present.
    Returns ``None`` when the platform has no config for this app.
    """
    if platform == "apkmirror":
        am = config.get("apkmirror")
        if not am:
            return None
        return {**am, "package": config.get("package", "")}

    platform_obj = config.get(platform, {})
    excluded = {"apkmirror", "apkpure", "uptodown", "aptoide"}
    flat = {k: v for k, v in config.items() if k not in excluded}
    flat["name"] = platform_obj.get("name") or config.get("name", "")
    if not flat.get("name"):
        return None
    return flat


def resolve_platform(
    app_name: str, platform: str, cli: str, patches: str,
    arch: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve the download URL and version for *app_name* on *platform*."""
    try:
        config = _load_app_config(app_name)
        if not config:
            return None, None

        platform_cfg = _platform_config(config, platform)
        if not platform_cfg:
            return None, None

        if arch:
            platform_cfg["arch"] = arch

        version = platform_cfg.get("version") or config.get("version") or \
            utils.get_supported_version(platform_cfg["package"], cli, patches)
        platform_module = importlib.import_module(f"src.{platform}")
        version = version or platform_module.get_latest_version(app_name, platform_cfg)
        if not version:
            return None, None

        download_link = platform_module.get_download_link(version, app_name, platform_cfg)
        if not download_link:
            return None, None

        return download_link, version

    except Exception as e:
        logging.error("Unexpected error: %s", e)
        return None, None


def get_source_name(source: str) -> str:
    """Read the display name for *source* from its definition file without downloading."""
    source_path = Path("sources") / f"{source}.json"
    with source_path.open(encoding="utf-8") as fh:
        repos_info = json.load(fh)
    if isinstance(repos_info, dict):
        return repos_info.get("name", source)
    return repos_info[0]["name"]


def resolve_platform_version(
    app_name: str, platform: str, cli: str, patches: str,
    arch: str | None = None,
) -> str | None:
    """Resolve only the target version for *app_name* on *platform* (no download link)."""
    try:
        config = _load_app_config(app_name)
        if not config:
            return None

        platform_cfg = _platform_config(config, platform)
        if not platform_cfg:
            return None

        if arch:
            platform_cfg["arch"] = arch

        version = platform_cfg.get("version") or config.get("version") or \
            utils.get_supported_version(platform_cfg["package"], cli, patches)
        if not version:
            platform_module = importlib.import_module(f"src.{platform}")
            version = platform_module.get_latest_version(app_name, platform_cfg)
        return version
    except Exception as e:
        logging.debug("Version resolution failed for %s on %s: %s", app_name, platform, e)
        return None


def resolve_platform_link(
    app_name: str, platform: str, version: str,
    arch: str | None = None,
) -> str | None:
    """Resolve the download URL for a known *version* of *app_name* on *platform*."""
    try:
        config = _load_app_config(app_name)
        if not config:
            return None

        platform_cfg = _platform_config(config, platform)
        if not platform_cfg:
            return None

        if arch:
            platform_cfg["arch"] = arch
        platform_module = importlib.import_module(f"src.{platform}")
        return platform_module.get_download_link(version, app_name, platform_cfg)
    except Exception as e:
        logging.debug("Link resolution failed for %s v%s on %s: %s", app_name, version, platform, e)
        return None


# Platform-specific convenience wrappers

def resolve_apkmirror(app_name, cli, patches, arch=None):
    """Resolve download URL from APKMirror."""
    return resolve_platform(app_name, "apkmirror", cli, patches, arch)


def resolve_apkpure(app_name, cli, patches, arch=None):
    """Resolve download URL from APKPure."""
    return resolve_platform(app_name, "apkpure", cli, patches, arch)


def resolve_aptoide(app_name, cli, patches, arch=None):
    """Resolve download URL from Aptoide."""
    return resolve_platform(app_name, "aptoide", cli, patches, arch)


def resolve_uptodown(app_name, cli, patches, arch=None):
    """Resolve download URL from Uptodown."""
    return resolve_platform(app_name, "uptodown", cli, patches, arch)


def download_apkeditor() -> Path:
    """Download the latest APKEditor JAR from GitHub."""
    release = utils.detect_github_release("REAndroid", "APKEditor", "latest")

    for asset in release["assets"]:
        name = asset["name"]
        if name.startswith("APKEditor") and name.endswith(".jar"):
            return download_resource(asset["browser_download_url"])

    raise RuntimeError("APKEditor .jar file not found in the latest release")
