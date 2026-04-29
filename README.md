# APK Competitor Monitor Skill

A Codex skill for monitoring Android competitor apps from APK sources, comparing versions, and generating product/UI change reports.

This repository now also includes a Codex plugin manifest and a lightweight stdio MCP server so the same workflow can be consumed in more agent environments than a standalone `SKILL.md`.

This project is source-available for non-commercial use under the PolyForm Noncommercial License 1.0.0. It is not open source under the OSI definition and may not be used for commercial purposes without separate permission.

## What It Does

- Downloads and compares Android APK versions.
- Extracts static evidence from DEX strings, resources, manifests, URLs, events, APIs, and image assets.
- Checks local reverse-engineering dependencies and reports actionable setup gaps.
- Optionally decompiles with jadx plus Vineflower/Fernflower for source-level cross-checks.
- Extracts Retrofit, OkHttp, Volley, WebView, auth, URL, and base-URL signals from decompiled sources.
- Links screen classes, click/navigation/lifecycle signals, and API evidence into feature-flow candidates.
- Runs deep UI analysis with `apktool` and optional `jadx`.
- Produces page-level layout/resource diffs.
- Generates static UI reconstruction SVGs, including old/new side-by-side previews for changed layouts.
- Generates a local Web report and lightweight searchable archive.
- Optionally exports PDF when a local Chrome/Playwright engine is available.

## Install As A Skill In Codex

Ask Codex to install this skill from GitHub:

```text
Please install this Codex skill:
https://github.com/maidongdong/apk-competitor-monitor-skill/tree/main/apk-competitor-monitor
```

After installation, restart Codex so the new skill is picked up.

## Install As A Plugin / MCP Bundle

This repository now exposes:

- plugin manifest: [`.codex-plugin/plugin.json`](./.codex-plugin/plugin.json)
- MCP config: [`.mcp.json`](./.mcp.json)
- stdio MCP server: [`mcp_server.py`](./mcp_server.py)

The plugin keeps the existing skill workflow and adds MCP tools for the most reusable actions:

- `get_skill_overview`
- `validate_project_config`
- `monitor_wandoujia`
- `check_re_dependencies`
- `decompile_with_engines`
- `analyze_apk_diff`
- `extract_api_surface`
- `diff_api_surface`
- `trace_feature_flow`
- `deep_ui_analysis`
- `product_ui_analysis`
- `build_deep_ui_web_data`
- `render_static_ui_previews`
- `generate_apk_report_bundle`
- `export_simple_archive`
- `export_report_pdf`
- `web_probe_admin`
- `web_generate_report`
- `web_run_weekly`
- `weekly_generate_unified_report`
- `publish_build_site`
- `publish_deploy_site`
- `notify_wecom_weekly_report`
- `run_full_weekly_pipeline`

To use it as a local Codex plugin, point your plugin installer at this repository root so Codex can read `.codex-plugin/plugin.json`.

To use it as a generic MCP server, run:

```bash
python3 mcp_server.py
```

and connect over stdio using the MCP config in [`.mcp.json`](./.mcp.json).

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

For MCP tool clients, the minimum useful inputs are:

- `monitor_wandoujia`
  - `app_url`
  - optional `state`
  - optional `out_root`
- `validate_project_config`
  - `workspace_root`
  - `project_config`
- `check_re_dependencies`
  - no input
- `decompile_with_engines`
  - `apk`
  - `out_dir`
  - optional `engine`, `deobf`, `include_res`, `timeout_seconds`
- `analyze_apk_diff`
  - `old_label`
  - `old_apk`
  - `new_label`
  - `new_apk`
- `extract_api_surface`
  - `source_dir`
  - `output`
  - optional `include_prefixes`, `exclude_prefixes`
- `trace_feature_flow`
  - `source_dir`
  - `api_surface`
  - `output`
  - optional `api_diff`, `layout_data`, `include_prefixes`, `exclude_prefixes`
- `diff_api_surface`
  - `old_api_surface`
  - `new_api_surface`
  - `output`
- `deep_ui_analysis`
  - `old_label`
  - `old_apk`
  - `new_label`
  - `new_apk`
  - optional `output`, `out_root`, `force`, `skip_jadx`
- `product_ui_analysis`
  - `old_label`
  - `old_apk`
  - `new_label`
  - `new_apk`
  - optional `output`
- `build_deep_ui_web_data`
  - `ui_layout_diff`
  - optional `out`
- `render_static_ui_previews`
  - `apktool_dir`
  - `layout_data`
  - `out_dir`
  - `out_json`
  - optional `old_apktool_dir`, `ui_layout_diff`, `limit`
- `generate_apk_report_bundle`
  - `diff`
  - `product`
  - `layout`
  - `preview`
  - `old_apk`
  - `new_apk`
  - `report_dir`
  - `old_version`
  - `new_version`
  - optional `app_name`, `package`, `old_date`, `new_date`, `template_dir`, `api_surface`, `feature_flow`
- `export_simple_archive`
  - `report_dir`
  - optional `zip_name`
- `export_report_pdf`
  - `report_dir`
  - optional `out`, `port`

For workspace orchestration tools, provide a monitoring project root that contains:

- `artifacts/web-monitor/scripts/*.mjs`
- `artifacts/web-monitor/config.json`
- `reports/`
- optional `publish/` and WeCom secret files

The workspace-oriented tools are:

- `web_probe_admin`
  - `workspace_root`
  - optional `route_ids`, `playwright_channel`, `network_idle_timeout_ms`, `settle_ms`
- `web_generate_report`
  - `workspace_root`
  - optional `web_probe_summary`, `web_baseline`, `web_report_dir`, `web_update_baseline`
- `web_run_weekly`
  - `workspace_root`
  - optional probe/report overrides above
- `weekly_generate_unified_report`
  - `workspace_root`
  - optional `apk_report_dir`, `web_report_dir`, `weekly_report_dir`
- `publish_build_site`
  - `workspace_root`
  - optional `weekly_report_dir`, `publish_dir`
- `publish_deploy_site`
  - `workspace_root`
  - optional `publish_dir`, `publish_url`
- `notify_wecom_weekly_report`
  - `workspace_root`
  - optional `weekly_report_dir`, `publish_url`, `wecom_webhook_url`, `dry_run`

## One-Click Weekly Orchestration

The MCP server also exposes:

- `run_full_weekly_pipeline`

Minimum inputs:

- `workspace_root`
- `app_url`

Or:

- `workspace_root`
- `project_config`

This orchestration tool performs:

1. APK version check against the workspace state file
2. APK diff/report generation when a new version exists
3. Source-level API surface extraction and feature-flow tracing when jadx sources are available
4. Web/admin probe + report
5. Unified weekly report generation
6. Static publish deploy
7. WeCom notification

Useful optional controls:

- `apk_state`
- `apk_reports_root`
- `preview_limit`
- `run_web`
- `route_ids`
- `web_report_dir`
- `run_weekly_report`
- `weekly_report_dir`
- `publish`
- `publish_dir`
- `publish_url`
- `notify`
- `notify_dry_run`
- `wecom_webhook_url`

When there is no newer APK, the orchestration tool reuses the previous `apk.report_dir` or the last report recorded in the APK state so the unified weekly report can still point to the prior APK detail report instead of silently dropping APK context.

## Project Config For Reuse

APK source remains Wandoujia-based by design, but other runtime settings are now meant to be project-configurable.

Use [apk-competitor-monitor/examples/config.example.json](/Users/dong/Documents/Cursor/竞品分析工具/apk-competitor-monitor-skill/apk-competitor-monitor/examples/config.example.json) as the starting point. The intended reusable fields are:

- `project_id`
- `app.name`
- `app.package`
- `source.app_url`
- `apk.state_file`
- `apk.report_root`
- `apk.report_dir`
- `apk.preview_limit`
- `web.enabled`
- `web.route_ids`
- `web.report_dir`
- `weekly.enabled`
- `weekly.report_dir`
- `publish.enabled`
- `publish.dir`
- `publish.url`
- `notify.enabled`
- `notify.dry_run`
- `notify.wecom_webhook_url`
- `reproducibility.lock_report_template`
- `reproducibility.record_run_metadata`
- `reproducibility.require_project_config`

When `run_full_weekly_pipeline` receives both direct arguments and `project_config`, direct arguments win.

For 今日水印相机, start from [apk-competitor-monitor/examples/today-watermark-camera.config.example.json](./apk-competitor-monitor/examples/today-watermark-camera.config.example.json). It fixes the Wandoujia page, app package, report state paths, and static preview limit so different agents begin from the same monitoring contract.

Before a scheduled run, call `validate_project_config`. APK detail reports generated by the full pipeline embed `runMetadata` and write `run-metadata.json`; the HTML coverage page shows the config fingerprint, template fingerprint, direct override keys, and reproducibility flags. See [docs/reproducible-runs.md](./docs/reproducible-runs.md).

## Onboarding A New Web/Admin Competitor

For a new Web/admin target, start from:

- [apk-competitor-monitor/examples/web-monitor.config.example.json](/Users/dong/Documents/Cursor/竞品分析工具/apk-competitor-monitor-skill/apk-competitor-monitor/examples/web-monitor.config.example.json)
- [docs/web-monitor-onboarding.md](/Users/dong/Documents/Cursor/竞品分析工具/apk-competitor-monitor-skill/docs/web-monitor-onboarding.md)

Those files explain:

- how to define `targets` and `routes`
- how to write stable `baselineSpec` entries
- how to reduce noise with `ignoreTextPatterns`
- how to apply `privacyRedaction`
- how to choose routes that are PM-meaningful instead of operationally noisy

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
- The bundled MCP server is intentionally lightweight: it wraps the existing local scripts and returns JSON/text results over stdio instead of re-implementing the whole reporting pipeline in the server itself.
- Runtime screenshots require a separate device/emulator capture flow with `adb`, uiautomator2, Appium, or an equivalent tool.
- Do not commit APK files, generated reports, state files, or competitor artifacts to this repository.
- Make sure your use of third-party APKs and reverse engineering complies with applicable law and the terms that apply to the APK source.

## License

Licensed under the PolyForm Noncommercial License 1.0.0. See `LICENSE`.

Required Notice: Copyright (c) 2026 Dong.
