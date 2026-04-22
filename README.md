# APK Competitor Monitor Skill

A Codex skill for monitoring Android competitor apps from APK sources, comparing versions, and generating product/UI change reports.

This project is source-available for non-commercial use under the PolyForm Noncommercial License 1.0.0. It is not open source under the OSI definition and may not be used for commercial purposes without separate permission.

## What It Does

- Downloads and compares Android APK versions.
- Extracts static evidence from DEX strings, resources, manifests, URLs, events, APIs, and image assets.
- Runs deep UI analysis with `apktool` and optional `jadx`.
- Produces page-level layout/resource diffs.
- Generates static UI reconstruction SVGs, including old/new side-by-side previews for changed layouts.
- Generates a local Web report and lightweight searchable archive.
- Optionally exports PDF when a local Chrome/Playwright engine is available.

## Install In Codex

Ask Codex to install this skill from GitHub:

```text
Please install this Codex skill:
https://github.com/maidongdong/apk-competitor-monitor-skill/tree/main/apk-competitor-monitor
```

After installation, restart Codex so the new skill is picked up.

## Requirements

Required:

- Python 3.9+

Recommended for deep UI reconstruction:

- OpenJDK
- apktool
- jadx

Optional:

- Chrome/Chromium or Playwright for PDF export

## Usage Example

```text
Use the apk-competitor-monitor skill to monitor this Wandoujia app page:
https://www.wandoujia.com/apps/APP_ID

Compare the newest APK against the previous monitored APK, run deep UI diff,
generate a Web report, and export a lightweight archive.
```

For a one-off comparison, provide two APK files:

```text
Use the apk-competitor-monitor skill to compare old.apk and new.apk.
Focus on feature changes, UI changes, and static UI reconstruction.
```

## Output

Typical output includes:

- `report-data.json`
- `static-ui-data.json`
- `ui-layout-data.json`
- `ui-preview-data.json`
- `static-ui-previews/*.svg`
- `index.html`, `app.js`, `styles.css`
- `archive-manifest.json`
- zipped report archive
- optional `report.pdf`

## Important Notes

- Static UI reconstruction is not a runtime screenshot.
- Runtime screenshots require a separate device/emulator capture flow with `adb`, uiautomator2, Appium, or an equivalent tool.
- Do not commit APK files, generated reports, state files, or competitor artifacts to this repository.
- Make sure your use of third-party APKs and reverse engineering complies with applicable law and the terms that apply to the APK source.

## License

Licensed under the PolyForm Noncommercial License 1.0.0. See `LICENSE`.

Required Notice: Copyright (c) 2026 Dong.
