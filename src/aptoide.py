"""Aptoide download source: version lookup and APK download link resolution."""

import base64
from typing import Any

from src import session

_BASE_URL = "https://ws75.aptoide.com/api/7/"


def get_latest_version(_app_name: str, config: dict[str, Any]) -> str:
    """Return the latest version string for *config['package']* from Aptoide."""
    package = config["package"]
    q_param = _get_q_param(config.get("arch", "universal"))
    url = f"{_BASE_URL}apps/search?query={package}&limit=1&trusted=true{q_param}"
    res = session.get(url).json()
    if res["datalist"]["list"]:
        return res["datalist"]["list"][0]["file"]["vername"]
    raise ValueError(f"No version found for {package}")


def get_download_link(version: str, _app_name: str, config: dict[str, Any]) -> str:
    """Resolve a direct download URL for *version* on Aptoide."""
    package = config["package"]
    q_param = _get_q_param(config.get("arch", "universal"))

    if version.lower() == "latest":
        url = (
            f"{_BASE_URL}apps/search?query={package}"
            f"&limit=1&trusted=true{q_param}"
        )
        res = session.get(url).json()
        return res["datalist"]["list"][0]["file"]["path"]

    url_versions = (
        f"{_BASE_URL}listAppVersions?package_name={package}"
        f"&limit=50{q_param}"
    )
    res_v = session.get(url_versions).json()
    vercode = None
    for app in res_v["datalist"]["list"]:
        if app["file"]["vername"] == version:
            vercode = app["file"]["vercode"]
            break
    if not vercode:
        raise ValueError(f"Version {version} not found for {package}")

    url_meta = (
        f"{_BASE_URL}getAppMeta?package_name={package}"
        f"&vercode={vercode}{q_param}"
    )
    res_meta = session.get(url_meta).json()
    return res_meta["data"]["file"]["path"]


def _get_q_param(arch: str) -> str:
    """Build the base64-encoded ``q`` query parameter for architecture filtering."""
    if arch == "universal":
        return ""
    cpu_map = {
        "arm64-v8a": "arm64-v8a,armeabi-v7a,armeabi",
        "armeabi-v7a": "armeabi-v7a,armeabi",
    }
    cpu = cpu_map.get(arch, "")
    if cpu:
        q_str = f"myCPU={cpu}&leanback=0"
        encoded = base64.b64encode(q_str.encode("utf-8")).decode("utf-8")
        return f"&q={encoded}"
    return ""
