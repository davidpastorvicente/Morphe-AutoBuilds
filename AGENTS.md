# AGENTS.md

## Repo Shape
- This repo is workflow-driven. The main entrypoint is `python -m src`, implemented in `src/__main__.py`.
- The only scheduled/manual automation lives in `.github/workflows/patch.yml` and `.github/workflows/manual-patch.yml`. Keep workflow assumptions aligned with the Python public functions they import.
- `patch-config.json` is the single source of truth for the scheduled build matrix. Each entry is keyed by `(app_name, source)` and controls `arch` plus optional patch `include`/`exclude` lists.
- `apps/<app>.json` is the single app config file. Platform-specific settings are nested under keys like `apkmirror`, `apkpure`, `uptodown`, `aptoide`; JSON keys use camelCase.
- `sources/<source>.json` defines where CLI and patch artifacts come from. The first object is metadata (`name`); later objects are GitHub release sources.

## Verified Commands
- Install deps: `pip install -r requirements.txt`
- Run a local build: `APP_NAME=youtube SOURCE=morphe GITHUB_TOKEN=... python -m src`
- Override architectures locally: `ARCH=arm64-v8a python -m src`
- Reuse pre-downloaded tools locally or in scripts: `TOOLS_DIR=tools/morphe python -m src`
- Pin a version hint locally: `VERSION=1.2.3 python -m src`
- Lint: `pylint src/`

## Runtime Requirements
- Local builds need Python 3.11+, Java, `zip`, and Android `apksigner`.
- `apksigner` is discovered only under `/usr/local/lib/android/sdk/build-tools/<version>/apksigner`.
- Signing always uses the checked-in keystore `keystore/public.jks` with the hardcoded `public` credentials from `src/__main__.py`.

## Workflow Contracts
- `patch.yml` pre-downloads CLI/patch assets once per source into `tools/<source>/`, uploads them as artifacts, then passes them to builds through `TOOLS_DIR`. Do not break `_load_prebuilt_tools()`, `resolve_cli_and_patches()`, `resolve_arch()`, or `resolve_app_version()` without updating workflows.
- Scheduled builds skip work purely by checking whether release tag `<app_name>-v<version>` already exists.
- Manual builds always run a single app/source/arch combination and can overwrite assets in an existing release.
- `manual-patch.yml` still contains cleanup logic for legacy per-platform config directories (`apps/apkmirror`, `apps/apkpure`, `apps/uptodown`) that do not exist in this repo. Treat that workflow as drift-prone and verify it after edits.

## Code Conventions That Matter Here
- Prefer lazy logging (`logging.info("x=%s", value)`) over f-strings in logging calls; the existing code follows this pattern.
- Use `encoding="utf-8"` for text file reads/writes.
- When adding a new download platform, implement `src/<platform>.py` with `get_latest_version()` and `get_download_link()`, then wire config through `apps/<app>.json`. `downloader.py` imports platform modules dynamically.

## Change Hotspots
- If you change version resolution, patch tool detection, or source config parsing, verify both local `python -m src` execution and workflow inline Python steps; the workflows import directly from `src.__main__`, `src.downloader`, and `src.release`.
- If you change naming or output paths, preserve release-tag format `<app_name>-v<version>` and signed APK naming from `run_build()`, or adjust workflow release/upload steps in the same change.
