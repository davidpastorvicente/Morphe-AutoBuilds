# Copilot Instructions

## Architecture

Morphe-AutoBuilds is a Python pipeline that **downloads base APKs → patches them with Morphe/ReVanced tools → signs and publishes per-app GitHub releases**. It runs on GitHub Actions (Ubuntu, Python 3.11).

### Data flow

1. **`patch-config.json`** lists `{app_name, source, arch}` entries → workflow builds a matrix job per app (arch is resolved internally by Python, not the matrix).
2. Each job runs `python -m src` (entry point: `src/__main__.py`), which:
   - Reads `patch-config.json` to determine target architectures via `resolve_arch(app_name, source)`.
   - Downloads CLI + patches from a **source** definition (`sources/<source>.json`).
   - Resolves the target APK version and downloads the base APK from the first working platform (`apps/apkmirror/`, `apps/apkpure/`, etc.).
   - Patches, merges bundles if needed, strips architectures, signs with `keystore/public.jks`.
3. Workflow creates/updates a GitHub release tagged `<app_name>-v<version>`.

### Key modules

| Module | Role |
|---|---|
| `src/__init__.py` | Shared `session` (curl_cffi), `gh` (PyGithub), logging config |
| `src/__main__.py` | Build orchestration: `resolve_arch`, version resolution, patching, signing |
| `src/downloader.py` | Downloads CLI/patches from sources, delegates APK resolution to platform modules |
| `src/apkmirror.py` | APKMirror scraper — the most complex module (variant/arch/DPI matching) |
| `src/apkpure.py`, `src/aptoide.py`, `src/uptodown.py` | Alternative platform scrapers |
| `src/utils.py` | Process execution, version parsing, GitHub release helpers |
| `src/release.py` | Version extraction from filenames (used by workflows) |

### Configuration files

- **`patch-config.json`** — build matrix: `app_name`, `source`, and `arch` (list). This is the single source of truth for what gets built and at which architectures.
- **`sources/<name>.json`** — GitHub repos for CLI + patches (e.g., `morphe.json` points to `MorpheApp/morphe-cli`).
- **`apps/<platform>/<app>.json`** — per-platform scraper config (org, package name, DPI, optional pinned version). No `arch` field — arch is passed at runtime from `patch-config.json`.
- **`patches/<app>-<source>.txt`** — patch include (`+`) / exclude (`-`) rules, one per line.

## Code Style

- Write concise code with minimal comments. Only comment when something genuinely needs clarification.
- All Python code must pass `pylint src/ --disable=import-error` with no warnings (currently 10.00/10).
- Use lazy `%` formatting in logging calls: `logging.info(x=%s, x)` — never f-strings.
- Module-level constants are `UPPER_CASE`. Local/function-scope variables are `snake_case`.
- Add docstrings to all public functions. Private helpers (prefixed `_`) need docstrings only if non-obvious.
- Use `sys.exit()` instead of importing `exit` from `sys`.
- Always pass `encoding=utf-8` to `open()` for text files.
- Keep functions under pylint complexity thresholds (15 locals, 12 branches, 50 statements). Extract helpers when functions grow.

## Lint

```bash
pip install pylint
pylint src/ --disable=import-error
```

## Running Locally

```bash
pip install -r requirements.txt
export APP_NAME=youtube SOURCE=morphe GITHUB_TOKEN=ghp_...
python -m src
```

To override the architecture (bypasses `patch-config.json`): `export ARCH=arm64-v8a`.

## Git Conventions

- Never add a "Co-authored-by: Copilot" trailer to commit messages.
- Use conventional commit prefixes: `feat:`, `fix:`, `refactor:`, `chore:`.

## Platform Scraper Pattern

All platform modules (`apkmirror`, `apkpure`, `aptoide`, `uptodown`) export the same interface:

```python
def get_latest_version(app_name: str, config: dict) -> str | None: ...
def get_download_link(version: str, app_name: str, config: dict) -> str | None: ...
```

`downloader.py` calls these dynamically via `importlib.import_module(f"src.{platform}")`. When adding a new platform, create `src/<platform>.py` with these two functions and add app configs under `apps/<platform>/`.

## Workflows

- **`patch.yml`** — scheduled every 3 days. Matrix has only `app_name` and `source`; arch is read from `patch-config.json` by Python internally. Skips apps whose release tag already exists.
- **`manual-patch.yml`** — manual dispatch with inputs for app, source, version, arch, and replace-in-release flag.
- Both workflows use inline Python heredocs (`python - <<'PY'`) and import from `src.release` and `src.__main__` — changes to those modules' public API will break CI.
- Public API used by workflows: `resolve_build_inputs(source)`, `resolve_download_target(app_name, cli, patches, arch)`, `resolve_arch(app_name, source)`.
