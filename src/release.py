"""GitHub release helpers: version extraction."""

import re
from pathlib import Path


def extract_version(file_path: str) -> str:
    """Pull a semver-like version string from a file name."""
    if not file_path:
        return "unknown"
    base_name = Path(file_path).stem
    match = re.search(
        r"(\d+\.\d+\.\d+(-[a-z]+\.\d+)?(-release\d*)?)", base_name
    )
    return match.group(1) if match else "unknown"
