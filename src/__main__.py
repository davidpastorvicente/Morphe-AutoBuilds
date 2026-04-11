"""Entry-point for building patched APKs."""

import json
import logging
import re
import subprocess
import sys
from os import getenv
from pathlib import Path

from src import downloader, utils


def detect_source_type(
    download_files: list[Path], source: str
) -> tuple[bool, bool]:
    """Return ``(is_morphe, is_revanced)`` for the given files/source."""
    is_morphe = False
    is_revanced = False

    for file in download_files:
        if "morphe-cli" in file.name.lower():
            is_morphe = True
            break
        if "revanced-cli" in file.name.lower():
            is_revanced = True
            break

    if not is_morphe and not is_revanced:
        for file in download_files:
            if file.suffix == ".mpp":
                is_morphe = True
                break
            if file.suffix in [".rvp", ".jar"] \
                    and "patches" in file.name.lower():
                is_revanced = True
                break

    if not is_morphe and not is_revanced:
        is_morphe = (
            "morphe" in source.lower() or "custom" in source.lower()
        )
        is_revanced = not is_morphe

    return is_morphe, is_revanced


def resolve_cli_and_patches(
    download_files: list[Path], source: str
) -> tuple[Path | None, Path | None, bool]:
    """Identify the CLI jar and patches file from *download_files*."""
    is_morphe, _ = detect_source_type(download_files, source)

    if is_morphe:
        cli = utils.find_file(
            download_files,
            contains="morphe-cli", suffix=".jar", exclude=["dev"],
        )
        if not cli:
            cli = utils.find_file(
                download_files, contains="morphe", suffix=".jar"
            )
        patches = utils.find_file(
            download_files, contains="patches", suffix=".mpp"
        )
        if not patches:
            patches = utils.find_file(download_files, suffix=".mpp")
    else:
        cli = utils.find_file(
            download_files, contains="revanced-cli", suffix=".jar"
        )
        patches = utils.find_file(
            download_files, contains="patches", suffix=".rvp"
        )
        if not patches:
            patches = utils.find_file(
                download_files, contains="patches", suffix=".jar"
            )

    return cli, patches, is_morphe


def resolve_build_inputs(
    source: str,
) -> tuple[list[Path], str, Path | None, Path | None, bool]:
    """Download all required files and detect the source type."""
    download_files, name = downloader.download_required(source)

    logging.info(
        "📦 Downloaded %d files for %s:", len(download_files), source
    )
    for file in download_files:
        logging.info("  - %s (%d bytes)", file.name, file.stat().st_size)

    cli, patches, is_morphe = resolve_cli_and_patches(
        download_files, source
    )
    logging.info(
        "🔍 Detected: %s source type",
        "Morphe" if is_morphe else "ReVanced",
    )

    return download_files, name, cli, patches, is_morphe


def resolve_download_target(
    app_name: str, cli: str, patches: str, arch: str = None
) -> tuple[str | None, str | None]:
    """Try each download platform in order and return the first hit."""
    resolve_methods = [
        downloader.resolve_apkmirror,
        downloader.resolve_apkpure,
        downloader.resolve_uptodown,
        downloader.resolve_aptoide,
    ]

    for method in resolve_methods:
        download_link, version = method(
            app_name, cli, patches, arch
        )
        if download_link:
            return download_link, version

    return None, None


# ------------------------------------------------------------------
# Helpers extracted from run_build
# ------------------------------------------------------------------

def _merge_bundle_apk(input_apk: Path) -> Path:
    """Merge a non-APK bundle into a single APK using APKEditor."""
    logging.warning("Input file is not .apk, using APKEditor to merge")
    apk_editor = downloader.download_apkeditor()
    merged_apk = input_apk.with_suffix(".apk")

    utils.run_process([
        "java", "-jar", apk_editor, "m",
        "-i", str(input_apk),
        "-o", str(merged_apk),
    ], silent=True)

    input_apk.unlink(missing_ok=True)

    if not merged_apk.exists():
        logging.error("Merged APK file not found")
        sys.exit(1)

    clean_name = re.sub(r'\(\d+\)', '', merged_apk.name)
    clean_name = re.sub(r'-\d+_', '_', clean_name)
    if clean_name != merged_apk.name:
        clean_apk = merged_apk.with_name(clean_name)
        merged_apk.rename(clean_apk)
        merged_apk = clean_apk

    logging.info("Merged APK file generated: %s", merged_apk)
    return merged_apk


def _strip_architectures(input_apk: Path, arch: str) -> None:
    """Remove unwanted native libraries from *input_apk*."""
    if arch == "arm64-v8a":
        utils.run_process([
            "zip", "--delete", str(input_apk),
            "lib/x86/*", "lib/x86_64/*", "lib/armeabi-v7a/*",
        ], silent=True, check=False)
    elif arch == "armeabi-v7a":
        utils.run_process([
            "zip", "--delete", str(input_apk),
            "lib/x86/*", "lib/x86_64/*", "lib/arm64-v8a/*",
        ], silent=True, check=False)
    else:
        utils.run_process([
            "zip", "--delete", str(input_apk),
            "lib/x86/*", "lib/x86_64/*",
        ], silent=True, check=False)


def _load_patch_config(
    app_name: str, source: str
) -> tuple[list[str], list[str]]:
    """Read the patch include/exclude file and return flag lists."""
    exclude: list[str] = []
    include: list[str] = []
    patches_path = Path("patches") / f"{app_name}-{source}.txt"
    if patches_path.exists():
        with patches_path.open('r', encoding="utf-8") as patches_file:
            for line in patches_file:
                line = line.strip()
                if line.startswith('-'):
                    exclude.extend(["-d", line[1:].strip()])
                elif line.startswith('+'):
                    include.extend(["-e", line[1:].strip()])
    return exclude, include


def _repair_apk(input_apk: Path, app_name: str, version: str) -> None:
    """Attempt to fix a potentially corrupted APK with ``zip -FF``."""
    logging.info("Checking APK for corruption...")
    try:
        fixed_apk = Path(f"{app_name}-fixed-v{version}.apk")
        subprocess.run(
            ["zip", "-FF", str(input_apk), "--out", str(fixed_apk)],
            check=False,
            capture_output=True,
        )
        if fixed_apk.exists() and fixed_apk.stat().st_size > 0:
            input_apk.unlink(missing_ok=True)
            fixed_apk.rename(input_apk)
            logging.info("APK fixed successfully")
    except OSError as exc:
        logging.warning("Could not fix APK: %s", exc)


def _run_patcher(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    cli: Path,
    patches: Path,
    input_apk: Path,
    output_apk: Path,
    is_morphe: bool,
    exclude_patches: list[str],
    include_patches: list[str],
) -> None:
    """Invoke the Morphe or ReVanced patcher."""
    if is_morphe:
        logging.info("🔧 Using Morphe patching system...")
        try:
            utils.run_process([
                "java", "-jar", str(cli),
                "patch", "--patches", str(patches),
                "--out", str(output_apk), str(input_apk),
                *exclude_patches, *include_patches,
            ], stream=True)
        except subprocess.CalledProcessError:
            logging.info("Trying alternative Morphe command format...")
            utils.run_process([
                "java", "-jar", str(cli),
                "--patches", str(patches),
                "--input", str(input_apk),
                "--output", str(output_apk),
            ], stream=True)
    else:
        logging.info("🔧 Using ReVanced patching system...")
        cli_name = Path(cli).name.lower()
        is_v6_plus = any(
            tag in cli_name
            for tag in ('revanced-cli-6', 'revanced-cli-7',
                        'revanced-cli-8')
        )
        if is_v6_plus:
            utils.run_process([
                "java", "-jar", str(cli),
                "patch", "-p", str(patches), "-b",
                "--out", str(output_apk), str(input_apk),
                *exclude_patches, *include_patches,
            ], stream=True)
        else:
            utils.run_process([
                "java", "-jar", str(cli),
                "patch", "--patches", str(patches),
                "--out", str(output_apk), str(input_apk),
                *exclude_patches, *include_patches,
            ], stream=True)


def _sign_apk(output_apk: Path, signed_apk: Path) -> None:
    """Sign *output_apk* and write the result to *signed_apk*."""
    apksigner = utils.find_apksigner()
    if not apksigner:
        sys.exit(1)

    base_cmd = [
        str(apksigner), "sign", "--verbose",
        "--ks", "keystore/public.jks",
        "--ks-pass", "pass:public",
        "--key-pass", "pass:public",
        "--ks-key-alias", "public",
        "--in", str(output_apk), "--out", str(signed_apk),
    ]
    try:
        utils.run_process(base_cmd, stream=True)
    except subprocess.CalledProcessError as exc:
        logging.warning("Standard signing failed: %s", exc)
        logging.info("Trying alternative signing method...")
        utils.run_process(
            base_cmd[:3] + ["--min-sdk-version", "21"] + base_cmd[3:],
            stream=True,
        )


# ------------------------------------------------------------------
# Main build orchestration
# ------------------------------------------------------------------

def run_build(
    app_name: str, source: str, arch: str = "universal"
) -> str:
    """Build APK for specific architecture."""
    download_files, name, cli, patches, is_morphe = \
        resolve_build_inputs(source)

    if not cli:
        logging.error("❌ CLI not found for source: %s", source)
        logging.error(
            "Available files: %s", [f.name for f in download_files]
        )
        return None
    if not patches:
        logging.error("❌ Patches not found for source: %s", source)
        logging.error(
            "Available files: %s", [f.name for f in download_files]
        )
        return None

    logging.info("✅ Using CLI: %s", cli.name)
    logging.info("✅ Using patches: %s", patches.name)

    download_link, version = resolve_download_target(
        app_name, str(cli), str(patches), arch
    )
    input_apk = None
    if download_link:
        input_apk = downloader.download_resource(download_link)

    if input_apk is None:
        logging.error("❌ Failed to download APK for %s", app_name)
        sys.exit(1)

    if input_apk.suffix != ".apk":
        input_apk = _merge_bundle_apk(input_apk)

    if arch != "universal":
        logging.info(
            "Processing APK for %s architecture...", arch
        )
    _strip_architectures(input_apk, arch)

    exclude_patches, include_patches = _load_patch_config(
        app_name, source
    )
    _repair_apk(input_apk, app_name, version)

    output_apk = Path(
        f"{app_name}-{arch}-patch-v{version}.apk"
    )
    _run_patcher(
        cli, patches, input_apk, output_apk, is_morphe,
        exclude_patches, include_patches,
    )
    input_apk.unlink(missing_ok=True)

    signed_apk = Path(
        f"{app_name}-{arch}-{name}-v{version}.apk"
    )
    _sign_apk(output_apk, signed_apk)
    output_apk.unlink(missing_ok=True)
    print(f"✅ APK built: {signed_apk.name}")

    return str(signed_apk)


def resolve_arch(app_name: str, source: str) -> list[str]:
    """Return the arch list for *app_name*/*source* from patch-config.json."""
    config_path = Path("patch-config.json")
    if config_path.exists():
        with open(config_path, encoding="utf-8") as fh:
            patch_list = json.load(fh).get("patch_list", [])
        for entry in patch_list:
            if entry["app_name"] == app_name and entry["source"] == source:
                arch = entry.get("arch", ["universal"])
                return arch if isinstance(arch, list) else [arch]
    return ["universal"]


def main():
    """CLI entry-point: read env vars and build for each arch."""
    app_name = getenv("APP_NAME")
    source = getenv("SOURCE")

    if not app_name or not source:
        logging.error(
            "APP_NAME and SOURCE environment variables must be set"
        )
        sys.exit(1)

    arch_override = getenv("ARCH")
    if arch_override:
        arches = [a.strip() for a in arch_override.split(",") if a.strip()]
    else:
        arches = resolve_arch(app_name, source)

    built_apks: list[str] = []
    for arch in arches:
        logging.info("🔨 Building %s for %s architecture...", app_name, arch)
        apk_path = run_build(app_name, source, arch)
        if apk_path:
            built_apks.append(apk_path)
            print(f"✅ Built {arch}: {Path(apk_path).name}")

    print(f"\n🎯 Built {len(built_apks)} APK(s) for {app_name}:")
    for apk in built_apks:
        print(f"  📱 {Path(apk).name}")


if __name__ == "__main__":
    main()
