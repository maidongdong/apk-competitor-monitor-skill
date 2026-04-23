---
name: apk-competitor-monitor
description: Use this skill to monitor Android competitor apps from APK sources such as Wandoujia, compare APK versions, infer feature/UI changes, extract static UI evidence, and generate a local Web report with evidence chains.
metadata:
  short-description: Monitor Android competitor APK changes
---

# APK Competitor Monitor

Use this skill when the user wants to monitor an Android competitor app, compare APK versions, analyze feature/UI changes, or generate a Web report from APK static analysis.

## Core Workflow

1. Identify the target app page and package.
   - For Wandoujia pages, parse `data-app-vcode`, `data-app-vname`, `data-app-vid`, `data-pn`, and download links.
   - Record source URL, versionName, versionCode, update time, APK MD5, and local path.

2. Download APKs.
   - Prefer comparing the newest version against the previously monitored version.
   - If there is no previous monitored version, compare against a user-selected older version or the nearest history version.

3. Run static APK diff.
   - Use `scripts/analyze_apk_diff.py OLD_LABEL OLD_APK NEW_LABEL NEW_APK`.
   - This extracts file diffs, DEX strings, URLs, API/class path signals, resource strings, Manifest components, native libraries, events, and SDK hints.

4. Run product/UI analysis.
   - Use `scripts/product_ui_analysis.py` or adapt it for the workspace paths.
   - Classify evidence into product modules such as safe mode, team photo labels, WeChat binding, VIP, location lock, workgroup widget, puzzle editor, ads, crash monitoring, video/RTC, AI, and upload/sync.

5. Extract static UI evidence.
   - Extract added/removed/changed image resources from APK zip entries.
   - Generate `static-ui-data.json` with UI keys, page/fragment/activity hints, API evidence, and extracted image thumbnails.
   - Be explicit that this is static UI reconstruction, not runtime screenshots.

6. Run deep UI reconstruction when dependencies are available.
   - Check `apktool --version` and `jadx --version`.
   - Run `scripts/deep_ui_analysis.py OLD_LABEL OLD_APK NEW_LABEL NEW_APK --output ui-layout-diff.json`.
   - This decodes resources with apktool into `artifacts/apk-monitor/decompiled/<version>/apktool/`.
   - It parses layout XML, string/color/style values, drawable/mipmap/resource file changes, and optionally scans jadx output for Activity/Fragment/Dialog to layout mapping.
   - If jadx fails, continue with apktool layout/resource diff and mark the mapping status as failed/missing.
   - Run `scripts/build_deep_ui_web_data.py ui-layout-diff.json --out REPORT_DIR/ui-layout-data.json`.
   - Run `scripts/render_static_ui_previews.py --apktool-dir NEW_APKTOOL_DIR --old-apktool-dir OLD_APKTOOL_DIR --layout-data REPORT_DIR/ui-layout-data.json --out-dir REPORT_DIR/static-ui-previews --out-json REPORT_DIR/ui-preview-data.json` to produce second-layer static UI preview SVGs.
   - For maximum static reconstruction, pass `--ui-layout-diff ui-layout-diff.json --limit 50` so previews include added/changed pages, old/new side-by-side previews for changed layouts, inferred states, RecyclerView item/layout hints, and change summaries.

7. Generate the Web report.
   - Copy `assets/web-report-template/` into the report directory.
   - Write `report-data.json` and `static-ui-data.json`.
   - If deep UI data exists, also write `ui-layout-data.json`, `ui-preview-data.json`, and `static-ui-previews/*.svg`.
   - Preview cards should show change kind, old/new side-by-side static previews when available, inferred states, RecyclerView item hints, associated Activity/Fragment/Dialog classes, and the underlying evidence.
   - The report should include a PM insight page, feature changes, page-level layout diff, static UI reconstruction, decompilation coverage, SDK/native changes, and raw evidence counts.
   - The PM insight page should lead with prioritized product conclusions, affected modules, suggested manual validation tasks, and evidence badges rather than raw reverse-engineering names.
   - The coverage page should make static-analysis limits explicit: explained product conclusions, page-level UI coverage, unexplained layout/resource signals, and blind spots such as gray rollout, server config, WebView/H5, encrypted strings, and runtime account states.
   - Include obfuscation impact assessment when JADX/layout mappings exist: count suspicious short/defpackage class names, explain impact level, and generate candidate semantic aliases from linked layout names, UI text, resource ids, and product category.

8. Export a PDF archive.
   - After the Web report is generated, run `scripts/export_report_pdf.py REPORT_DIR --out REPORT_DIR/report.pdf`.
   - The exporter prefers local Chrome/Chromium, then Python Playwright.
   - If no PDF engine exists, leave `PDF_EXPORT_NOT_AVAILABLE.txt` in the report directory and mention the missing dependency.

9. Export the lightweight archive format.
   - Run `scripts/export_simple_archive.py REPORT_DIR`.
   - This writes `ARCHIVE_README.md`, `archive-manifest.json`, and a zipped Web snapshot archive.
   - Prefer this archive for long-term storage because it keeps structured JSON evidence searchable and avoids PDF rendering fragility.

10. If the user wants true screenshots, add a dynamic UI capture pass.
   - Install old/new APKs on emulator or device.
   - Use adb/uiautomator2/Appium to navigate, screenshot, dump UI tree, and generate visual diffs.
   - Treat runtime screenshots as higher-confidence evidence than static UI reconstruction.

## Reporting Rules

- Lead with user-facing product conclusions, not raw reverse-engineering details.
- Help product managers answer four questions first: what changed, how important it is, what evidence supports it, and what should be manually verified next.
- Every feature/UI conclusion needs an evidence chain: API/class path, resource key, event key, Manifest component, image asset, or URL.
- Mark confidence:
  - High: multiple independent signals agree, such as Activity + UI key + API + event.
  - Medium: code/API + UI key, but no runtime screenshot.
  - Low: isolated string/resource signal.
- Separate static findings from runtime-confirmed screenshots.
- Do not claim a UI is visible to users unless runtime capture confirms it.
- Keep an unexplained-change pool. Do not imply the APK has been fully mined when signals remain unclassified or require runtime validation.
- Treat obfuscated class names as weak evidence. Prefer semantic aliases such as `VerifyCodeErrorDialogCandidate` only when backed by layout/string/API/resource evidence, and label them as inferred candidates rather than original names.

## Useful Commands

```bash
python3 scripts/analyze_apk_diff.py OLD_LABEL old.apk NEW_LABEL new.apk
```

```bash
python3 scripts/product_ui_analysis.py
```

```bash
python3 scripts/deep_ui_analysis.py OLD_LABEL old.apk NEW_LABEL new.apk --output ui-layout-diff.json
```

```bash
python3 scripts/build_deep_ui_web_data.py ui-layout-diff.json --out report-dir/ui-layout-data.json
```

```bash
python3 scripts/render_static_ui_previews.py --apktool-dir artifacts/apk-monitor/decompiled/NEW_LABEL/apktool --old-apktool-dir artifacts/apk-monitor/decompiled/OLD_LABEL/apktool --layout-data report-dir/ui-layout-data.json --ui-layout-diff ui-layout-diff.json --out-dir report-dir/static-ui-previews --out-json report-dir/ui-preview-data.json --limit 50
```

```bash
python3 scripts/export_report_pdf.py reports/some-report-dir --out reports/some-report-dir/report.pdf
```

```bash
python3 scripts/export_simple_archive.py reports/some-report-dir
```

## Productization Notes

This skill is the lightweight workflow layer. If the workflow becomes stable and needs persistent state, UI, background jobs, emulator control, or MCP tools, promote it into a Codex plugin.
