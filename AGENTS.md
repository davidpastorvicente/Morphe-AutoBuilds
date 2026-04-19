# AGENTS.md

## Repo Shape
- This repo builds patched Android APKs. The main entrypoint is `python -m src`, implemented in `src/__main__.py`.
- Build and release automation is workflow-driven. The only GitHub Actions workflows for that flow are `.github/workflows/patch.yml` and `.github/workflows/manual-patch.yml`.
- `patch-config.json` is the scheduled build matrix. Each entry is keyed by `(app_name, source)` and can define `arch` plus optional patch `include` and `exclude` lists.
- `apps/<app>.json` is the single app definition. Common fields live at the top level (`displayName`, `package`, optional `version`); platform-specific settings are nested under keys such as `apkmirror`, `apkpure`, `uptodown`, and `aptoide`.
- `sources/<source>.json` supports two formats: a release-source list whose first object carries metadata (`name`), or a bundle definition object with `bundle_url`.
- `src/__init__.py` owns the shared HTTP session (`curl_cffi`) and GitHub client. Reuse that wiring instead of creating ad hoc request or GitHub setup.

## Runtime Contract
- `python -m src` is environment-variable driven.
- Required env vars: `APP_NAME`, `SOURCE`.
- Optional env vars: `ARCH` (comma-separated override), `TOOLS_DIR` (pre-downloaded CLI/patches), `VERSION` (version hint/override), `GITHUB_TOKEN`.
- `main()` resolves architectures from `patch-config.json` unless `ARCH` is set.
- `run_build()` writes signed APKs named like `{app_name}-{arch}-{source_name}-v{version}.apk`; workflows rely on `*.apk` outputs.

## Workflow Contracts
- Keep workflow assumptions aligned with the Python functions they import directly: `resolve_cli_and_patches()`, `resolve_app_version()`, `resolve_arch()`, and the `python -m src` entrypoint.
- `patch.yml` downloads CLI and patch artifacts once per source into `tools/<source>/`, uploads them, then builds with `TOOLS_DIR`. Do not break `_load_prebuilt_tools()` or `resolve_cli_and_patches()` without updating the workflow.
- Scheduled builds skip work only by checking whether release tag `<app_name>-v<version>` already exists. Preserve that tag format unless the workflow changes in the same edit.
- Manual builds operate on a single app/source/arch combination and may overwrite APK assets in an existing release.
- `manual-patch.yml` still contains legacy cleanup logic for non-existent per-platform config directories (`apps/apkmirror`, `apps/apkpure`, `apps/uptodown`). If you edit that workflow, verify it carefully.

## Code Conventions That Matter Here
- Prefer lazy logging (`logging.info("x=%s", value)`) over f-strings in logging calls.
- Use `encoding="utf-8"` for text file reads and writes.
- When adding a new download platform, implement `src/<platform>.py` with `get_latest_version()` and `get_download_link()`, then wire it through `apps/<app>.json`. `downloader.py` imports platform modules dynamically.
- Preserve the shared session/client pattern in `src/__init__.py` unless you are intentionally changing repo-wide networking behavior.

## Validation
- Primary verification is a real build path, not a test suite. There is currently no `tests/` directory.
- Verified commands:
  - Install deps: `pip install -r requirements.txt`
  - Run a local build: `APP_NAME=youtube SOURCE=morphe GITHUB_TOKEN=... python -m src`
  - Override architectures locally: `ARCH=arm64-v8a python -m src`
  - Reuse pre-downloaded tools: `TOOLS_DIR=tools/morphe python -m src`
  - Pin a version hint: `VERSION=1.2.3 python -m src`
  - Lint: `pylint src/`
- If you change version resolution, source parsing, tool detection, output naming, or workflow-facing functions, verify both local `python -m src` behavior and the inline Python used by the workflows.

## Runtime Requirements
- Local builds need Python 3.11+, Java, `zip`, and Android `apksigner`.
- `apksigner` is discovered only under `/usr/local/lib/android/sdk/build-tools/<version>/apksigner`.
- Signing uses the checked-in keystore `keystore/public.jks`; do not change signing assumptions casually because build and release behavior depend on them.
