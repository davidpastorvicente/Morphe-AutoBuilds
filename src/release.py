"""GitHub release helpers: version extraction, title formatting, and release management."""

import re
import sys
from pathlib import Path

from src import REPOSITORY, gh


def convert_title(text: str) -> str:
    """Convert kebab-case text to Title Case (e.g. ``youtube-music`` → ``Youtube Music``)."""
    if not text or not isinstance(text, str):
        return text
    return re.sub(
        r"\b([a-z0-9]+(?:-[a-z0-9]+)*)\b",
        lambda m: m.group(1).replace("-", " ").title(),
        text,
        flags=re.IGNORECASE,
    )


def extract_version(file_path: str) -> str:
    """Pull a semver-like version string from a file name."""
    if not file_path:
        return "unknown"
    base_name = Path(file_path).stem
    match = re.search(
        r"(\d+\.\d+\.\d+(-[a-z]+\.\d+)?(-release\d*)?)", base_name
    )
    return match.group(1) if match else "unknown"


def create_github_release(
    name: str,
    patches_name: str,
    cli_name: str,
    apk_file_path: str,
) -> None:
    """Create (or update) a GitHub release and upload the built APK."""
    patchver = extract_version(patches_name)
    cliver = extract_version(cli_name)
    tag_name = f"{name}-v{patchver}"

    apk_path = Path(apk_file_path)
    if not apk_path.exists():
        sys.exit(1)

    repo = gh.get_repo(REPOSITORY)

    existing_release = _get_existing_release(repo, tag_name)

    if existing_release:
        _delete_duplicate_asset(existing_release, apk_path.name)

    _cleanup_old_releases(repo, name, tag_name, patchver)

    if not existing_release:
        existing_release = _create_new_release(
            repo, tag_name, name, patchver, cliver
        )

    existing_release.upload_asset(
        path=str(apk_path),
        label=apk_path.name,
        content_type="application/vnd.android.package-archive",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_existing_release(repo, tag_name):
    """Return the release for *tag_name*, or ``None`` if it doesn't exist."""
    try:
        return repo.get_release(tag_name)
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def _delete_duplicate_asset(release, asset_name: str) -> None:
    """Remove an existing asset with the same name to allow re-upload."""
    for asset in release.get_assets():
        if asset.name == asset_name:
            asset.delete_asset()


def _cleanup_old_releases(repo, name: str, tag_name: str, patchver: str) -> None:
    """Delete older releases that share the same base name and version suffix."""
    suffix_match = re.search(r"(-[a-z]+\.\d+)$", patchver)
    current_suffix = suffix_match.group(1) if suffix_match else ""
    current_numeric = re.sub(
        r"(-[a-z]+\.\d+)?(-release\d*)?$", "", patchver
    )

    for release in repo.get_releases():
        release_tag = release.tag_name
        if not release_tag.startswith(f"{name}-v") or release_tag == tag_name:
            continue

        old_version = release_tag[len(name) + 2:]
        old_suffix_match = re.search(r"(-[a-z]+\.\d+)$", old_version)
        old_suffix = old_suffix_match.group(1) if old_suffix_match else ""

        if old_suffix != current_suffix:
            continue

        old_numeric = re.sub(
            r"(-[a-z]+\.\d+)?(-release\d*)?$", "", old_version
        )
        if old_numeric < current_numeric:
            release.delete_release()


def _create_new_release(repo, tag_name, name, patchver, cliver):
    """Create a fresh GitHub release with standard release notes."""
    release_body = (
        "# Release Notes\n"
        "\n"
        "## Build Tools:\n"
        f"- **ReVanced Patches:** v{patchver}\n"
        f"- **ReVanced CLI:** v{cliver}\n"
        "\n"
        "## Note:\n"
        "**ReVanced GmsCore** is **necessary** to work.\n"
        "- Please **download** it from "
        "[HERE](https://github.com/revanced/gmscore/releases/latest).\n"
    )
    release_name = f"{convert_title(name)} v{patchver}"
    return repo.create_git_release(
        tag=tag_name,
        name=release_name,
        message=release_body,
        draft=False,
        prerelease=False,
    )
