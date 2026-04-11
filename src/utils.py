"""Shared utilities: file finding, process execution, version parsing, GitHub helpers."""

import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

from src import gh


def _parseparam(text: str):
    """Yield semicolon-delimited parameter tokens from a header value."""
    while text[:1] == ";":
        text = text[1:]
        end = text.find(";")
        while end > 0 and (text.count('"', 0, end) - text.count('\\"', 0, end)) % 2:
            end = text.find(";", end + 1)
        if end < 0:
            end = len(text)
        token = text[:end]
        yield token.strip()
        text = text[end:]


def parse_header(line: str) -> tuple[str, dict[str, str]]:
    """Parse a Content-type like header into ``(key, params_dict)``."""
    parts = _parseparam(";" + line)
    key = parts.__next__()
    pdict: dict[str, str] = {}
    for part in parts:
        idx = part.find("=")
        if idx >= 0:
            name = part[:idx].strip().lower()
            value = part[idx + 1:].strip()
            if len(value) >= 2 and value[0] == value[-1] == '"':
                value = value[1:-1]
                value = value.replace("\\\\", "\\").replace('\\"', '"')
            pdict[name] = value
    return key, pdict


def find_file(
    files: list[Path],
    prefix: str | None = None,
    suffix: str | None = None,
    contains: str | None = None,
    exclude: list[str] | None = None,
) -> Path | None:
    """Find a file matching criteria, falling back to an unfiltered search if needed."""
    if exclude is None:
        exclude = []

    match = _match_file(files, prefix, suffix, contains, exclude)
    if match:
        return match

    if exclude:
        return _match_file(files, prefix, suffix, contains, [])

    return None


def _match_file(
    files: list[Path],
    prefix: str | None,
    suffix: str | None,
    contains: str | None,
    exclude: list[str],
) -> Path | None:
    """Return the first file matching all criteria, or ``None``."""
    for file in files:
        if any(excl.lower() in file.name.lower() for excl in exclude):
            continue
        if prefix and not file.name.startswith(prefix):
            continue
        if suffix and not file.name.endswith(suffix):
            continue
        if contains and contains.lower() not in file.name.lower():
            continue
        return file
    return None


def find_apksigner() -> str | None:
    """Locate the newest ``apksigner`` binary under Android SDK build-tools."""
    sdk_root = Path("/usr/local/lib/android/sdk")
    build_tools_dir = sdk_root / "build-tools"

    if not build_tools_dir.exists():
        logging.error("No build-tools found at: %s", build_tools_dir)
        return None

    versions = sorted(build_tools_dir.iterdir(), reverse=True)
    for version_dir in versions:
        apksigner_path = version_dir / "apksigner"
        if apksigner_path.exists() and apksigner_path.is_file():
            return str(apksigner_path)

    logging.error("No apksigner found in build-tools")
    return None


def run_process(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    command: list[str],
    cwd: Path | None = None,
    capture: bool = False,
    stream: bool = False,  # pylint: disable=unused-argument
    silent: bool = False,
    check: bool = True,
    shell: bool = False,
) -> str | None:
    """Execute *command* as a subprocess, optionally capturing or streaming output."""
    with subprocess.Popen(
        command,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=shell,
    ) as process:
        output_lines: list[str] = []

        try:
            for line in iter(process.stdout.readline, ""):
                if line:
                    if not silent:
                        print(line.rstrip(), flush=True)
                    if capture:
                        output_lines.append(line)
            process.stdout.close()
            return_code = process.wait()

            if check and return_code != 0:
                raise subprocess.CalledProcessError(return_code, command)

            return "".join(output_lines).strip() if capture else None

        except FileNotFoundError:
            print(f"Command not found: {command[0]}", flush=True)
            sys.exit(1)
        except subprocess.CalledProcessError:
            raise
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"Error while running command: {exc}", flush=True)
            sys.exit(1)


def normalize_version(version: str) -> list[int]:
    """Convert a version string to a list of integers for comparison."""
    parts = version.split(".")
    normalized = []
    for part in parts:
        match = re.match(r"(\d+)", part)
        normalized.append(int(match.group(1)) if match else 0)

    build_match = re.search(r"build\s+(\d+)", version, re.IGNORECASE)
    if build_match:
        normalized.append(int(build_match.group(1)))

    paren_match = re.search(r"\((\d+)\)$", version)
    if paren_match:
        normalized.append(int(paren_match.group(1)))

    return normalized


def get_highest_version(versions: list[str]) -> str | None:
    """Return the version string with the highest numeric value."""
    if not versions:
        return None
    return max(versions, key=normalize_version)


def get_supported_version(
    package_name: str, cli: str, patches: str,
) -> Optional[str]:
    """Query the CLI for supported versions and return the highest one."""
    cmd = _build_list_versions_cmd(cli, patches, package_name)
    output = run_process(cmd, capture=True, silent=True, check=False)

    if not output:
        logging.warning("No output returned from list-versions command")
        return None

    lines = output.splitlines()
    logging.info("CLI raw output lines: %s", lines)

    first_line = lines[0].strip().lower()
    if any(kw in first_line for kw in ("usage:", "unmatched argument", "error")):
        logging.warning("CLI returned error/usage output, cannot determine version")
        return None

    if len(lines) <= 2:
        logging.warning("Output has no version lines")
        return None

    versions = _parse_version_lines(lines[2:])

    if not versions:
        logging.warning("No supported versions found")
        return None

    logging.info("CLI parsed versions: %s", versions)
    return get_highest_version(versions)


def _build_list_versions_cmd(
    cli: str, patches: str, package_name: str,
) -> list[str]:
    """Build the ``java -jar`` command for listing supported versions."""
    cli_name = Path(cli).name.lower()
    is_morphe = "morphe" in cli_name
    is_revanced_v6_plus = any(
        f"revanced-cli-{v}" in cli_name for v in ("6", "7", "8")
    )

    if is_morphe:
        return [
            "java", "-jar", cli,
            "list-versions", "-f", package_name, patches,
        ]
    if is_revanced_v6_plus:
        return [
            "java", "-jar", cli,
            "list-versions", "-p", patches, "-b", "-f", package_name,
        ]
    return [
        "java", "-jar", cli,
        "list-versions", "-f", package_name, patches,
    ]


def _parse_version_lines(lines: list[str]) -> list[str]:
    """Extract version strings from CLI output lines."""
    versions: list[str] = []
    for line in lines:
        line = line.strip()
        if not line or "Any" in line:
            continue
        parts = line.split()
        if not parts or not parts[0][0].isdigit():
            continue
        version = parts[0]
        if len(parts) >= 3 and parts[1].lower() == "build":
            version = f"{parts[0]} build {parts[2]}"
        versions.append(version)
    return versions


def extract_filename(response, fallback_url: str | None = None) -> str:
    """Derive a filename from response headers or URL path."""
    cd_header = response.headers.get("content-disposition")
    if cd_header:
        _, params = parse_header(cd_header)
        filename = params.get("filename") or params.get("filename*")
        if filename:
            return unquote(filename)

    parsed = urlparse(response.url)
    query_params = parse_qs(parsed.query)
    rcd = query_params.get("response-content-disposition")
    if rcd:
        _, params = parse_header(unquote(rcd[0]))
        filename = params.get("filename") or params.get("filename*")
        if filename:
            return unquote(filename)

    path = urlparse(fallback_url or response.url).path
    return unquote(Path(path).name)


def detect_github_release(user: str, repo: str, tag: str) -> dict:
    """Fetch a GitHub release by tag (or ``latest`` / ``dev`` / ``prerelease``)."""
    repo_obj = gh.get_repo(f"{user}/{repo}")

    if tag == "latest":
        release = repo_obj.get_latest_release()
        logging.info("Fetched latest release: %s", release.tag_name)
        return release.raw_data

    if tag in ("", "dev", "prerelease"):
        return _resolve_special_release(repo_obj, user, repo, tag)

    try:
        release = repo_obj.get_release(tag)
        logging.info("Fetched release: %s", release.tag_name)
        return release.raw_data
    except Exception:
        logging.error("Error fetching release %s for %s/%s", tag, user, repo)
        raise


def _resolve_special_release(repo_obj, user: str, repo: str, tag: str) -> dict:
    """Handle ``""``, ``"dev"``, and ``"prerelease"`` tags."""
    releases = list(repo_obj.get_releases())
    if not releases:
        raise ValueError(f"No releases found for {user}/{repo}")

    if tag == "":
        release = max(releases, key=lambda r: r.created_at)
    elif tag == "dev":
        devs = [r for r in releases if "dev" in r.tag_name.lower()]
        if not devs:
            raise ValueError(f"No dev release found for {user}/{repo}")
        release = max(devs, key=lambda r: r.created_at)
    else:
        pres = [r for r in releases if r.prerelease]
        if not pres:
            raise ValueError(f"No prerelease found for {user}/{repo}")
        release = max(pres, key=lambda r: r.created_at)

    logging.info("Fetched release: %s", release.tag_name)
    return release.raw_data


def detect_source_type(cli_file: Path, patches_file: Path) -> str:
    """Detect if we're using Morphe or ReVanced based on downloaded files."""
    if (
        cli_file
        and "morphe" in cli_file.name.lower()
        and patches_file
        and patches_file.suffix == ".mpp"
    ):
        return "morphe"
    if (
        cli_file
        and "revanced" in cli_file.name.lower()
        and patches_file
        and patches_file.suffix in (".jar", ".rvp")
    ):
        return "revanced"
    return "unknown"
