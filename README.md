<div align="center">

# 🔧 Morphe AutoBuilds

[![Auto Build](https://img.shields.io/github/actions/workflow/status/davidpastorvicente/Morphe-AutoBuilds/patch.yml?label=Auto%20Build&style=for-the-badge&color=2ea44f)](https://github.com/davidpastorvicente/Morphe-AutoBuilds/actions/workflows/patch.yml)
[![Latest Release](https://img.shields.io/github/v/release/davidpastorvicente/Morphe-AutoBuilds?style=for-the-badge&label=Latest%20Release&color=0366d6)](https://github.com/davidpastorvicente/Morphe-AutoBuilds/releases/latest)
[![Python Version](https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/github/license/davidpastorvicente/Morphe-AutoBuilds?style=for-the-badge&color=orange)](LICENSE)

<p align="center">
  <strong>Automated Morphe / ReVanced APK Builder</strong><br>
  Multi-source · Multi-architecture · GitHub Actions Powered
</p>

<p align="center">
A Python-based pipeline that automatically fetches the latest Morphe/ReVanced tools, downloads base APKs from multiple sources, applies patches, and publishes ready-to-install APKs as GitHub releases — for <strong>non-rooted Android devices</strong>.
</p>

[![View Releases](https://img.shields.io/badge/View%20Releases-0A0A0A?style=flat&logo=github&logoColor=white)](https://github.com/davidpastorvicente/Morphe-AutoBuilds/releases)
[![Report Bug](https://img.shields.io/badge/Report%20Bug-0A0A0A?style=flat&logo=github&logoColor=white)](https://github.com/davidpastorvicente/Morphe-AutoBuilds/issues)
[![Request Feature](https://img.shields.io/badge/Request%20Feature-0A0A0A?style=flat&logo=github&logoColor=white)](https://github.com/davidpastorvicente/Morphe-AutoBuilds/issues)

</div>

---

## ⚡ Quick Downloads

> Builds run automatically every 3 days. Each app gets its own release tagged `<app>-v<version>`.

| App | Source | Architecture | Release |
|:----|:-------|:------------:|:--------|
| **YouTube** | morphe | universal | [Download](https://github.com/davidpastorvicente/Morphe-AutoBuilds/releases/tag/youtube-v0.0.0) |
| **YouTube Music** | morphe | arm64-v8a | [Download](https://github.com/davidpastorvicente/Morphe-AutoBuilds/releases/tag/youtube-music-v0.0.0) |
| **Instagram** | piko | arm64-v8a | [Download](https://github.com/davidpastorvicente/Morphe-AutoBuilds/releases/tag/instagram-v0.0.0) |
| **X (Twitter)** | piko | universal | [Download](https://github.com/davidpastorvicente/Morphe-AutoBuilds/releases/tag/x-v0.0.0) |
| **Google Photos** | rookie | arm64-v8a | [Download](https://github.com/davidpastorvicente/Morphe-AutoBuilds/releases/tag/google-photos-v0.0.0) |

> Replace `v0.0.0` with the actual version or browse the [Releases](https://github.com/davidpastorvicente/Morphe-AutoBuilds/releases) page.

---

## ✨ Key Features

- **Fully Automated** — runs every 3 days via GitHub Actions, zero manual intervention required.
- **Multi-source** — tries APKMirror → APKPure → Uptodown → Aptoide in order; falls back automatically.
- **Architecture-specific builds** — configurable per app (`arm64-v8a`, `armeabi-v7a`, `universal`).
- **Granular patch control** — simple `+`/`-` rules in `patches/` files.
- **Auto-signed** — all APKs signed with a consistent keystore, install-ready.
- **Per-app releases** — each app gets its own GitHub release tag (`youtube-v19.x.x`).

---

## 🛠️ Repository Structure

```text
Morphe-AutoBuilds/
├── .github/workflows/
│   ├── patch.yml           # Scheduled build (every 3 days)
│   └── manual-patch.yml    # Manual trigger with override options
├── apps/                   # Per-app, per-platform scraper configs
│   ├── apkmirror/          # APKMirror definitions
│   ├── apkpure/            # APKPure definitions
│   ├── aptoide/            # Aptoide definitions
│   └── uptodown/           # Uptodown definitions
├── patches/                # Patch include/exclude rules per app+source
├── sources/                # Patch tool source definitions (GitHub releases)
├── src/                    # Python pipeline source
├── keystore/               # Signing keystore
├── patch-config.json       # Build matrix: which apps, sources, and arches to build
└── requirements.txt        # Python dependencies
```

---

## ⚙️ Configuration Guide

### 1. Build Matrix (`patch-config.json`)

Controls which apps are built, which patch source to use, and which CPU architectures to target.

```json
{
  "patch_list": [
    { "app_name": "youtube", "source": "morphe", "arch": ["universal"] },
    { "app_name": "youtube-music", "source": "morphe", "arch": ["arm64-v8a"] },
    { "app_name": "instagram", "source": "piko", "arch": ["arm64-v8a", "armeabi-v7a"] }
  ]
}
```

- `app_name` — must match a config file under `apps/<platform>/<app_name>.json`
- `source` — must match a file under `sources/<source>.json`
- `arch` — list of architectures to build; each entry produces a separate APK

### 2. Platform App Config (`apps/<platform>/<app>.json`)

Tells the scraper how to find and download the base APK. Example — `apps/apkmirror/youtube.json`:

```json
{
    "org": "google-inc",
    "name": "youtube",
    "type": "APK",
    "dpi": "nodpi",
    "package": "com.google.android.youtube"
}
```

Optionally add `"version": "x.x.x"` to pin a specific version instead of fetching the latest.

### 3. Patch Rules (`patches/<app>-<source>.txt`)

Use `+` to force-include and `-` to exclude a patch, one per line:

```text
+ premium-heading
+ hide-infocard-suggestions
- custom-branding
```

### 4. Source Definitions (`sources/<source>.json`)

Points to the GitHub repos hosting the CLI and patches. Example — `sources/morphe.json`:

```json
[
  { "name": "morphe" },
  { "user": "MorpheApp", "repo": "morphe-cli", "tag": "latest" },
  { "user": "MorpheApp", "repo": "morphe-patches", "tag": "latest" }
]
```

---

## 🚀 Running Locally

**Prerequisites:** Python 3.11+, Java, `zip`, `apksigner`

```bash
git clone https://github.com/davidpastorvicente/Morphe-AutoBuilds.git
cd Morphe-AutoBuilds
pip install -r requirements.txt

export APP_NAME="youtube"
export SOURCE="morphe"
export GITHUB_TOKEN="ghp_..."
python -m src
```

Override architecture (optional — otherwise read from `patch-config.json`):

```bash
export ARCH="arm64-v8a"
python -m src
```

---

## 🔄 Workflows

### Scheduled Build (`patch.yml`)

- Runs every 3 days at 06:00 UTC (also triggerable manually).
- Builds a matrix job per app in `patch-config.json`.
- Skips apps whose release tag already exists.
- Creates a GitHub release tagged `<app_name>-v<version>`.

### Manual Build (`manual-patch.yml`)

Triggered via the GitHub Actions UI with the following inputs:

| Input | Description |
|:------|:------------|
| `app_name` | App to build |
| `source` | Patch source to use |
| `version` | Pin a specific version (leave blank for latest) |
| `architecture` | Target arch (`universal`, `arm64-v8a`, `armeabi-v7a`) |
| `replace_in_release` | Overwrite existing release assets |

---

## ⚠️ Disclaimer

This project is an automated build tool. Builds are **not** officially affiliated with Morphe, ReVanced, or any patch team. Provided for educational and convenience purposes only. Use at your own risk.

---

<div align="center">

**Made with 💜 — contributions welcome via Pull Request**

</div>
