#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parent
SKILL_DIR = WORKSPACE / "apk-competitor-monitor"
SCRIPTS_DIR = SKILL_DIR / "scripts"
PROTOCOL_VERSION = "2024-11-05"


def send(message):
    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def read_message():
    headers = {}
    while True:
      line = sys.stdin.buffer.readline()
      if not line:
          return None
      if line in (b"\r\n", b"\n"):
          break
      text = line.decode("utf-8").strip()
      if ":" in text:
          key, value = text.split(":", 1)
          headers[key.lower()] = value.strip()
    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        return None
    body = sys.stdin.buffer.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def make_text_result(text):
    return {"content": [{"type": "text", "text": text}]}


def run_script(script_name, args):
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name), *args]
    completed = subprocess.run(
        cmd,
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        check=True,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    payload = {"command": cmd, "stdout": stdout, "stderr": stderr}
    if stdout:
        try:
            payload["json"] = json.loads(stdout)
        except json.JSONDecodeError:
            payload["json"] = None
    return payload


def read_json_file(path):
    return json.loads(Path(path).read_text("utf-8"))


def nested_get(data, path, default=None):
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def first_value(*values):
    for value in values:
        if value is not None:
            return value
    return None


def resolve_workspace_root(arguments):
    workspace_root = arguments.get("workspace_root")
    if not workspace_root:
        raise KeyError("workspace_root is required for this tool")
    root = Path(workspace_root).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"workspace_root does not exist: {root}")
    return root


def load_project_config(workspace_root, arguments):
    config_path = arguments.get("project_config")
    if not config_path:
        return {}
    path = Path(config_path).expanduser()
    if not path.is_absolute():
        path = workspace_root / path
    if not path.exists():
        raise FileNotFoundError(f"project_config does not exist: {path}")
    return read_json_file(path)


def run_node_script(workspace_root, script_relative_path, args=None, env=None, use_cert_wrapper=False):
    args = args or []
    script_path = workspace_root / script_relative_path
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script: {script_path}")
    merged_env = os.environ.copy()
    if env:
        merged_env.update({key: str(value) for key, value in env.items()})
    if use_cert_wrapper:
        cert_path = merged_env.get("NODE_EXTRA_CA_CERTS", "/etc/ssl/cert.pem")
        cmd = ["/usr/bin/env", f"NODE_EXTRA_CA_CERTS={cert_path}", "node", str(script_path), *args]
    else:
        cmd = ["node", str(script_path), *args]
    completed = subprocess.run(
        cmd,
        cwd=workspace_root,
        capture_output=True,
        text=True,
        check=True,
        env=merged_env,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    payload = {"command": cmd, "stdout": stdout, "stderr": stderr}
    if stdout:
        try:
            payload["json"] = json.loads(stdout)
        except json.JSONDecodeError:
            payload["json"] = None
    return payload


def handle_tool_call(name, arguments):
    arguments = arguments or {}
    if name == "get_skill_overview":
        overview = {
            "name": "apk-competitor-monitor",
            "mode": "plugin+mcp",
            "requirements": {
                "required": ["Python 3.9+"],
                "recommended": ["OpenJDK", "apktool", "jadx"],
                "optional": ["Chrome/Chromium or Playwright for PDF export"],
            },
            "entrypoints": [
                "monitor_wandoujia",
                "analyze_apk_diff",
                "deep_ui_analysis",
                "product_ui_analysis",
                "build_deep_ui_web_data",
                "render_static_ui_previews",
                "generate_apk_report_bundle",
                "export_simple_archive",
                "export_report_pdf",
                "web_probe_admin",
                "web_generate_report",
                "web_run_weekly",
                "weekly_generate_unified_report",
                "publish_build_site",
                "publish_deploy_site",
                "notify_wecom_weekly_report",
            ],
            "notes": [
                "Static UI reconstruction is not a runtime screenshot.",
                "For APK source monitoring, provide a Wandoujia app page URL and optional state path.",
                "For one-off diffing, provide old/new APK file paths and version labels.",
                "Web/admin and unified weekly tools expect a compatible monitoring workspace_root with artifacts/web-monitor/scripts/*.mjs present.",
            ],
        }
        return make_text_result(json.dumps(overview, ensure_ascii=False, indent=2))

    if name == "monitor_wandoujia":
        app_url = arguments["app_url"]
        state = arguments.get("state", "artifacts/apk-monitor/state.json")
        out_root = arguments.get("out_root", "reports")
        result = run_script(
            "monitor_wandoujia.py",
            ["--app-url", app_url, "--state", state, "--out-root", out_root, "--workspace", str(WORKSPACE)],
        )
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "analyze_apk_diff":
        result = run_script(
            "analyze_apk_diff.py",
            [
                arguments["old_label"],
                arguments["old_apk"],
                arguments["new_label"],
                arguments["new_apk"],
            ],
        )
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "deep_ui_analysis":
        output = arguments.get(
            "output",
            f"artifacts/apk-monitor/ui-layout-diff-{arguments['old_label']}-to-{arguments['new_label']}.json",
        )
        script_args = [
            arguments["old_label"],
            arguments["old_apk"],
            arguments["new_label"],
            arguments["new_apk"],
            "--output",
            output,
        ]
        out_root = arguments.get("out_root")
        if out_root:
            script_args.extend(["--out-root", out_root])
        if arguments.get("force"):
            script_args.append("--force")
        if arguments.get("skip_jadx"):
            script_args.append("--skip-jadx")
        result = run_script("deep_ui_analysis.py", script_args)
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "product_ui_analysis":
        output = arguments.get(
            "output",
            f"product-ui-analysis-{arguments['old_label']}-to-{arguments['new_label']}.json",
        )
        result = run_script(
            "product_ui_analysis.py",
            [
                arguments["old_label"],
                arguments["old_apk"],
                arguments["new_label"],
                arguments["new_apk"],
                "--output",
                output,
            ],
        )
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "build_deep_ui_web_data":
        out = arguments.get("out", "web-report/ui-layout-data.json")
        result = run_script(
            "build_deep_ui_web_data.py",
            [
                arguments["ui_layout_diff"],
                "--out",
                out,
            ],
        )
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "render_static_ui_previews":
        script_args = [
            "--apktool-dir",
            arguments["apktool_dir"],
            "--layout-data",
            arguments["layout_data"],
            "--out-dir",
            arguments["out_dir"],
            "--out-json",
            arguments["out_json"],
        ]
        if arguments.get("old_apktool_dir"):
            script_args.extend(["--old-apktool-dir", arguments["old_apktool_dir"]])
        if arguments.get("ui_layout_diff"):
            script_args.extend(["--ui-layout-diff", arguments["ui_layout_diff"]])
        if arguments.get("limit") is not None:
            script_args.extend(["--limit", str(arguments["limit"])])
        result = run_script("render_static_ui_previews.py", script_args)
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "generate_apk_report_bundle":
        script_args = [
            "--diff",
            arguments["diff"],
            "--product",
            arguments["product"],
            "--layout",
            arguments["layout"],
            "--preview",
            arguments["preview"],
            "--old-apk",
            arguments["old_apk"],
            "--new-apk",
            arguments["new_apk"],
            "--report-dir",
            arguments["report_dir"],
            "--old-version",
            arguments["old_version"],
            "--new-version",
            arguments["new_version"],
            "--template-dir",
            arguments.get("template_dir", str(SKILL_DIR / "assets" / "web-report-template")),
        ]
        for key, flag in [("app_name", "--app-name"), ("package", "--package"), ("old_date", "--old-date"), ("new_date", "--new-date")]:
            if arguments.get(key):
                script_args.extend([flag, arguments[key]])
        result = run_script("generate_apk_report_bundle.py", script_args)
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "export_simple_archive":
        script_args = [arguments["report_dir"]]
        if arguments.get("zip_name"):
            script_args.extend(["--zip-name", arguments["zip_name"]])
        result = run_script("export_simple_archive.py", script_args)
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "export_report_pdf":
        script_args = [arguments["report_dir"]]
        if arguments.get("out"):
            script_args.extend(["--out", arguments["out"]])
        if arguments.get("port"):
            script_args.extend(["--port", str(arguments["port"])])
        result = run_script("export_report_pdf.py", script_args)
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "web_probe_admin":
        workspace_root = resolve_workspace_root(arguments)
        env = {}
        if arguments.get("route_ids"):
            env["WEB_ROUTE_IDS"] = ",".join(arguments["route_ids"])
        if arguments.get("playwright_channel"):
            env["PLAYWRIGHT_CHANNEL"] = arguments["playwright_channel"]
        if arguments.get("network_idle_timeout_ms") is not None:
            env["WEB_NETWORK_IDLE_TIMEOUT_MS"] = arguments["network_idle_timeout_ms"]
        if arguments.get("settle_ms") is not None:
            env["WEB_SETTLE_MS"] = arguments["settle_ms"]
        result = run_node_script(workspace_root, "artifacts/web-monitor/scripts/probe_admin.mjs", env=env)
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "web_generate_report":
        workspace_root = resolve_workspace_root(arguments)
        env = {}
        if arguments.get("web_probe_summary"):
            env["WEB_PROBE_SUMMARY"] = arguments["web_probe_summary"]
        if arguments.get("web_baseline"):
            env["WEB_BASELINE"] = arguments["web_baseline"]
        if arguments.get("web_report_dir"):
            env["WEB_REPORT_DIR"] = arguments["web_report_dir"]
        if arguments.get("web_update_baseline") is not None:
            env["WEB_UPDATE_BASELINE"] = "1" if arguments["web_update_baseline"] else "0"
        result = run_node_script(workspace_root, "artifacts/web-monitor/scripts/generate_web_report.mjs", env=env)
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "web_run_weekly":
        workspace_root = resolve_workspace_root(arguments)
        probe_env = {}
        if arguments.get("route_ids"):
            probe_env["WEB_ROUTE_IDS"] = ",".join(arguments["route_ids"])
        if arguments.get("playwright_channel"):
            probe_env["PLAYWRIGHT_CHANNEL"] = arguments["playwright_channel"]
        if arguments.get("network_idle_timeout_ms") is not None:
            probe_env["WEB_NETWORK_IDLE_TIMEOUT_MS"] = arguments["network_idle_timeout_ms"]
        if arguments.get("settle_ms") is not None:
            probe_env["WEB_SETTLE_MS"] = arguments["settle_ms"]
        report_env = {}
        if arguments.get("web_probe_summary"):
            report_env["WEB_PROBE_SUMMARY"] = arguments["web_probe_summary"]
        if arguments.get("web_baseline"):
            report_env["WEB_BASELINE"] = arguments["web_baseline"]
        if arguments.get("web_report_dir"):
            report_env["WEB_REPORT_DIR"] = arguments["web_report_dir"]
        if arguments.get("web_update_baseline") is not None:
            report_env["WEB_UPDATE_BASELINE"] = "1" if arguments["web_update_baseline"] else "0"
        probe_result = run_node_script(workspace_root, "artifacts/web-monitor/scripts/probe_admin.mjs", env=probe_env)
        report_result = run_node_script(workspace_root, "artifacts/web-monitor/scripts/generate_web_report.mjs", env=report_env)
        return make_text_result(json.dumps({"probe": probe_result, "report": report_result}, ensure_ascii=False, indent=2))

    if name == "weekly_generate_unified_report":
        workspace_root = resolve_workspace_root(arguments)
        env = {}
        if arguments.get("apk_report_dir"):
            env["APK_REPORT_DIR"] = arguments["apk_report_dir"]
        if arguments.get("web_report_dir"):
            env["WEB_REPORT_DIR"] = arguments["web_report_dir"]
        if arguments.get("weekly_report_dir"):
            env["WEEKLY_REPORT_DIR"] = arguments["weekly_report_dir"]
        result = run_node_script(workspace_root, "artifacts/web-monitor/scripts/generate_weekly_report.mjs", env=env)
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "publish_build_site":
        workspace_root = resolve_workspace_root(arguments)
        env = {}
        if arguments.get("weekly_report_dir"):
            env["WEEKLY_REPORT_DIR"] = arguments["weekly_report_dir"]
        if arguments.get("publish_dir"):
            env["PUBLISH_DIR"] = arguments["publish_dir"]
        result = run_node_script(workspace_root, "artifacts/web-monitor/scripts/build_publish_site.mjs", env=env)
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "publish_deploy_site":
        workspace_root = resolve_workspace_root(arguments)
        env = {}
        if arguments.get("publish_dir"):
            env["PUBLISH_DIR"] = arguments["publish_dir"]
        if arguments.get("publish_url"):
            env["PUBLISH_URL"] = arguments["publish_url"]
        result = run_node_script(
            workspace_root,
            "artifacts/web-monitor/scripts/deploy_publish_site.mjs",
            env=env,
            use_cert_wrapper=True,
        )
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "notify_wecom_weekly_report":
        workspace_root = resolve_workspace_root(arguments)
        env = {}
        if arguments.get("weekly_report_dir"):
            env["WEEKLY_REPORT_DIR"] = arguments["weekly_report_dir"]
        if arguments.get("publish_url"):
            env["PUBLISH_URL"] = arguments["publish_url"]
        if arguments.get("wecom_webhook_url"):
            env["WECOM_WEBHOOK_URL"] = arguments["wecom_webhook_url"]
        if arguments.get("dry_run"):
            env["WECOM_DRY_RUN"] = "1"
        result = run_node_script(
            workspace_root,
            "artifacts/web-monitor/scripts/send_wecom_weekly_report.mjs",
            env=env,
            use_cert_wrapper=True,
        )
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    if name == "run_full_weekly_pipeline":
        workspace_root = resolve_workspace_root(arguments)
        project_config = load_project_config(workspace_root, arguments)
        app_url = first_value(arguments.get("app_url"), nested_get(project_config, ["source", "app_url"]))
        if not app_url:
            raise KeyError("app_url is required, either directly or via project_config.source.app_url")
        state_rel = first_value(arguments.get("apk_state"), nested_get(project_config, ["apk", "state_file"]), "artifacts/apk-monitor/state.json")
        reports_rel = first_value(arguments.get("apk_reports_root"), nested_get(project_config, ["apk", "report_root"]), "reports")
        state_path = workspace_root / state_rel
        before_state = read_json_file(state_path) if state_path.exists() else {}

        apk_check = run_script(
            "monitor_wandoujia.py",
            ["--app-url", app_url, "--state", state_rel, "--out-root", reports_rel, "--workspace", str(workspace_root)],
        )
        apk_check_json = apk_check.get("json") or {}
        after_state = read_json_file(state_path) if state_path.exists() else {}
        apk_status = apk_check_json.get("status")
        apk_report_dir = first_value(
            arguments.get("apk_report_dir"),
            nested_get(project_config, ["apk", "report_dir"]),
            after_state.get("last_report_dir"),
            before_state.get("last_report_dir"),
        )
        apk_pipeline = {"check": apk_check_json, "report_dir": apk_report_dir}

        if apk_status == "new_version_analyzed":
            old_code = str(apk_check_json.get("old"))
            new_code = str(apk_check_json.get("new"))
            report_root = Path(apk_check_json["report_dir"])
            old_apk = report_root / "apks" / f"{old_code}.apk"
            new_apk = report_root / "apks" / f"{new_code}.apk"
            diff_path = workspace_root / "artifacts" / "apk-monitor" / f"diff-{old_code}-to-{new_code}.json"
            layout_diff_path = workspace_root / "artifacts" / "apk-monitor" / f"ui-layout-diff-{old_code}-to-{new_code}.json"
            product_path = report_root / "product-ui-analysis.json"
            layout_data_path = report_root / "ui-layout-data.json"
            preview_data_path = report_root / "ui-preview-data.json"
            preview_dir = report_root / "static-ui-previews"
            template_dir = SKILL_DIR / "assets" / "web-report-template"
            app_name = nested_get(project_config, ["app", "name"], latest_meta.get("title", "Competitor App"))
            package_name = nested_get(project_config, ["app", "package"], latest_meta.get("package", ""))
            preview_limit = first_value(arguments.get("preview_limit"), nested_get(project_config, ["apk", "preview_limit"]), 50)

            apk_pipeline["product"] = run_script(
                "product_ui_analysis.py",
                [old_code, str(old_apk), new_code, str(new_apk), "--output", str(product_path)],
            ).get("json")
            apk_pipeline["layout_diff"] = run_script(
                "deep_ui_analysis.py",
                [old_code, str(old_apk), new_code, str(new_apk), "--output", str(layout_diff_path)],
            ).get("json")
            apk_pipeline["layout_data"] = run_script(
                "build_deep_ui_web_data.py",
                [str(layout_diff_path), "--out", str(layout_data_path)],
            ).get("json")
            apk_pipeline["previews"] = run_script(
                "render_static_ui_previews.py",
                [
                    "--apktool-dir",
                    str(workspace_root / "artifacts" / "apk-monitor" / "decompiled" / new_code / "apktool"),
                    "--old-apktool-dir",
                    str(workspace_root / "artifacts" / "apk-monitor" / "decompiled" / old_code / "apktool"),
                    "--layout-data",
                    str(layout_data_path),
                    "--ui-layout-diff",
                    str(layout_diff_path),
                    "--out-dir",
                    str(preview_dir),
                    "--out-json",
                    str(preview_data_path),
                    "--limit",
                    str(preview_limit),
                ],
            ).get("json")
            latest_meta = after_state.get("latest", {})
            previous_meta = after_state.get("previous", before_state.get("latest", {}))
            apk_pipeline["report_bundle"] = run_script(
                "generate_apk_report_bundle.py",
                [
                    "--diff",
                    str(diff_path),
                    "--product",
                    str(product_path),
                    "--layout",
                    str(layout_data_path),
                    "--preview",
                    str(preview_data_path),
                    "--old-apk",
                    str(old_apk),
                    "--new-apk",
                    str(new_apk),
                    "--report-dir",
                    str(report_root),
                    "--old-version",
                    old_code,
                    "--new-version",
                    new_code,
                    "--app-name",
                    app_name,
                    "--package",
                    package_name,
                    "--old-date",
                    previous_meta.get("update_time", ""),
                    "--new-date",
                    latest_meta.get("update_time", ""),
                    "--template-dir",
                    str(template_dir),
                ],
            ).get("json")
            apk_pipeline["archive"] = run_script("export_simple_archive.py", [str(report_root)]).get("json")
            apk_pipeline["pdf"] = run_script("export_report_pdf.py", [str(report_root)]).get("json")
            apk_report_dir = str(report_root)
            apk_pipeline["report_dir"] = apk_report_dir

        web_pipeline = None
        run_web = first_value(arguments.get("run_web"), nested_get(project_config, ["web", "enabled"]), True)
        if run_web:
            web_env_probe = {}
            route_ids = first_value(arguments.get("route_ids"), nested_get(project_config, ["web", "route_ids"]))
            if route_ids:
                web_env_probe["WEB_ROUTE_IDS"] = ",".join(route_ids)
            web_probe = run_node_script(workspace_root, "artifacts/web-monitor/scripts/probe_admin.mjs", env=web_env_probe)
            web_report_env = {}
            web_report_dir = first_value(arguments.get("web_report_dir"), nested_get(project_config, ["web", "report_dir"]))
            if web_report_dir:
                web_report_env["WEB_REPORT_DIR"] = web_report_dir
            web_report = run_node_script(workspace_root, "artifacts/web-monitor/scripts/generate_web_report.mjs", env=web_report_env)
            web_pipeline = {"probe": web_probe.get("json"), "report": web_report.get("json")}

        weekly_pipeline = None
        run_weekly = first_value(arguments.get("run_weekly_report"), nested_get(project_config, ["weekly", "enabled"]), True)
        if run_weekly:
            env = {}
            if apk_report_dir:
                env["APK_REPORT_DIR"] = apk_report_dir
            web_report_dir = first_value(arguments.get("web_report_dir"), nested_get(project_config, ["web", "report_dir"]))
            weekly_report_dir = first_value(arguments.get("weekly_report_dir"), nested_get(project_config, ["weekly", "report_dir"]))
            if web_report_dir:
                env["WEB_REPORT_DIR"] = web_report_dir
            if weekly_report_dir:
                env["WEEKLY_REPORT_DIR"] = weekly_report_dir
            weekly_result = run_node_script(workspace_root, "artifacts/web-monitor/scripts/generate_weekly_report.mjs", env=env)
            weekly_pipeline = weekly_result.get("json")

        publish_pipeline = None
        do_publish = first_value(arguments.get("publish"), nested_get(project_config, ["publish", "enabled"]), True)
        if do_publish:
            env = {}
            publish_dir = first_value(arguments.get("publish_dir"), nested_get(project_config, ["publish", "dir"]))
            publish_url = first_value(arguments.get("publish_url"), nested_get(project_config, ["publish", "url"]))
            if publish_dir:
                env["PUBLISH_DIR"] = publish_dir
            if publish_url:
                env["PUBLISH_URL"] = publish_url
            publish_result = run_node_script(
                workspace_root,
                "artifacts/web-monitor/scripts/deploy_publish_site.mjs",
                env=env,
                use_cert_wrapper=True,
            )
            publish_pipeline = publish_result.get("json")

        notify_pipeline = None
        do_notify = first_value(arguments.get("notify"), nested_get(project_config, ["notify", "enabled"]), True)
        if do_notify:
            env = {}
            weekly_report_dir = first_value(arguments.get("weekly_report_dir"), nested_get(project_config, ["weekly", "report_dir"]))
            publish_url = first_value(arguments.get("publish_url"), nested_get(project_config, ["publish", "url"]))
            wecom_webhook_url = first_value(arguments.get("wecom_webhook_url"), nested_get(project_config, ["notify", "wecom_webhook_url"]))
            notify_dry_run = first_value(arguments.get("notify_dry_run"), nested_get(project_config, ["notify", "dry_run"]), False)
            if weekly_report_dir:
                env["WEEKLY_REPORT_DIR"] = weekly_report_dir
            if publish_url:
                env["PUBLISH_URL"] = publish_url
            if wecom_webhook_url:
                env["WECOM_WEBHOOK_URL"] = wecom_webhook_url
            if notify_dry_run:
                env["WECOM_DRY_RUN"] = "1"
            notify_result = run_node_script(
                workspace_root,
                "artifacts/web-monitor/scripts/send_wecom_weekly_report.mjs",
                env=env,
                use_cert_wrapper=True,
            )
            notify_pipeline = notify_result.get("json")

        result = {
            "project": {
                "project_id": nested_get(project_config, ["project_id"]),
                "app_name": nested_get(project_config, ["app", "name"]),
                "app_url": app_url,
            },
            "apk": apk_pipeline,
            "web": web_pipeline,
            "weekly": weekly_pipeline,
            "publish": publish_pipeline,
            "notify": notify_pipeline,
        }
        return make_text_result(json.dumps(result, ensure_ascii=False, indent=2))

    raise KeyError(f"Unknown tool: {name}")


TOOLS = [
    {
        "name": "get_skill_overview",
        "description": "Return requirements, supported workflows, and expected inputs for the APK competitor monitor plugin.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "monitor_wandoujia",
        "description": "Check a Wandoujia app page, compare against stored state, and analyze a newly discovered APK version when one exists.",
        "inputSchema": {
            "type": "object",
            "required": ["app_url"],
            "properties": {
                "app_url": {"type": "string", "description": "Wandoujia app page URL, for example https://www.wandoujia.com/apps/7912851"},
                "state": {"type": "string", "description": "State JSON path relative to the plugin workspace"},
                "out_root": {"type": "string", "description": "Report output root relative to the plugin workspace"}
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "analyze_apk_diff",
        "description": "Run static APK diff on an old/new APK pair and write the machine-readable diff JSON.",
        "inputSchema": {
            "type": "object",
            "required": ["old_label", "old_apk", "new_label", "new_apk"],
            "properties": {
                "old_label": {"type": "string"},
                "old_apk": {"type": "string"},
                "new_label": {"type": "string"},
                "new_apk": {"type": "string"}
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "deep_ui_analysis",
        "description": "Decode APK resources with apktool and optional jadx, then produce a layout/resource diff report.",
        "inputSchema": {
            "type": "object",
            "required": ["old_label", "old_apk", "new_label", "new_apk"],
            "properties": {
                "old_label": {"type": "string"},
                "old_apk": {"type": "string"},
                "new_label": {"type": "string"},
                "new_apk": {"type": "string"},
                "output": {"type": "string"},
                "out_root": {"type": "string"},
                "force": {"type": "boolean"},
                "skip_jadx": {"type": "boolean"}
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "product_ui_analysis",
        "description": "Classify static APK diff evidence into PM-oriented product modules and write a structured report JSON.",
        "inputSchema": {
            "type": "object",
            "required": ["old_label", "old_apk", "new_label", "new_apk"],
            "properties": {
                "old_label": {"type": "string"},
                "old_apk": {"type": "string"},
                "new_label": {"type": "string"},
                "new_apk": {"type": "string"},
                "output": {"type": "string"}
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "build_deep_ui_web_data",
        "description": "Convert raw ui-layout-diff JSON into report-friendly layout cards and resource summaries.",
        "inputSchema": {
            "type": "object",
            "required": ["ui_layout_diff"],
            "properties": {
                "ui_layout_diff": {"type": "string"},
                "out": {"type": "string"}
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "render_static_ui_previews",
        "description": "Generate static SVG previews from apktool-decoded layouts, including old/new side-by-side changed-page previews when available.",
        "inputSchema": {
            "type": "object",
            "required": ["apktool_dir", "layout_data", "out_dir", "out_json"],
            "properties": {
                "apktool_dir": {"type": "string"},
                "old_apktool_dir": {"type": "string"},
                "layout_data": {"type": "string"},
                "out_dir": {"type": "string"},
                "out_json": {"type": "string"},
                "ui_layout_diff": {"type": "string"},
                "limit": {"type": "integer"}
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "generate_apk_report_bundle",
        "description": "Assemble APK diff outputs plus the bundled web-report template into a PM-facing APK report directory.",
        "inputSchema": {
            "type": "object",
            "required": ["diff", "product", "layout", "preview", "old_apk", "new_apk", "report_dir", "old_version", "new_version"],
            "properties": {
                "diff": {"type": "string"},
                "product": {"type": "string"},
                "layout": {"type": "string"},
                "preview": {"type": "string"},
                "old_apk": {"type": "string"},
                "new_apk": {"type": "string"},
                "report_dir": {"type": "string"},
                "old_version": {"type": "string"},
                "new_version": {"type": "string"},
                "app_name": {"type": "string"},
                "package": {"type": "string"},
                "old_date": {"type": "string"},
                "new_date": {"type": "string"},
                "template_dir": {"type": "string"}
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "export_simple_archive",
        "description": "Write README, archive manifest, and a zipped searchable report archive for a generated report directory.",
        "inputSchema": {
            "type": "object",
            "required": ["report_dir"],
            "properties": {
                "report_dir": {"type": "string"},
                "zip_name": {"type": "string"}
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "export_report_pdf",
        "description": "Export a report directory to PDF using local Chrome/Chromium first, then Python Playwright when available.",
        "inputSchema": {
            "type": "object",
            "required": ["report_dir"],
            "properties": {
                "report_dir": {"type": "string"},
                "out": {"type": "string"},
                "port": {"type": "string"}
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "web_probe_admin",
        "description": "Probe configured admin routes inside a monitoring workspace and write fresh local Web/admin snapshots plus probe-summary.json.",
        "inputSchema": {
            "type": "object",
            "required": ["workspace_root"],
            "properties": {
                "workspace_root": {"type": "string"},
                "route_ids": {"type": "array", "items": {"type": "string"}},
                "playwright_channel": {"type": "string"},
                "network_idle_timeout_ms": {"type": "integer"},
                "settle_ms": {"type": "integer"}
            },
            "additionalProperties": False
        }
    },
    {
        "name": "web_generate_report",
        "description": "Generate the PM-facing Web/admin report and archive from a probe summary, with optional baseline update.",
        "inputSchema": {
            "type": "object",
            "required": ["workspace_root"],
            "properties": {
                "workspace_root": {"type": "string"},
                "web_probe_summary": {"type": "string"},
                "web_baseline": {"type": "string"},
                "web_report_dir": {"type": "string"},
                "web_update_baseline": {"type": "boolean"}
            },
            "additionalProperties": False
        }
    },
    {
        "name": "web_run_weekly",
        "description": "Run the full Web/admin weekly cycle inside a monitoring workspace by executing probe and report in sequence.",
        "inputSchema": {
            "type": "object",
            "required": ["workspace_root"],
            "properties": {
                "workspace_root": {"type": "string"},
                "route_ids": {"type": "array", "items": {"type": "string"}},
                "playwright_channel": {"type": "string"},
                "network_idle_timeout_ms": {"type": "integer"},
                "settle_ms": {"type": "integer"},
                "web_probe_summary": {"type": "string"},
                "web_baseline": {"type": "string"},
                "web_report_dir": {"type": "string"},
                "web_update_baseline": {"type": "boolean"}
            },
            "additionalProperties": False
        }
    },
    {
        "name": "weekly_generate_unified_report",
        "description": "Generate the unified PM weekly report that links APK detail and Web/admin detail reports.",
        "inputSchema": {
            "type": "object",
            "required": ["workspace_root"],
            "properties": {
                "workspace_root": {"type": "string"},
                "apk_report_dir": {"type": "string"},
                "web_report_dir": {"type": "string"},
                "weekly_report_dir": {"type": "string"}
            },
            "additionalProperties": False
        }
    },
    {
        "name": "publish_build_site",
        "description": "Build the static publish directory from the latest unified weekly report without deploying it.",
        "inputSchema": {
            "type": "object",
            "required": ["workspace_root"],
            "properties": {
                "workspace_root": {"type": "string"},
                "weekly_report_dir": {"type": "string"},
                "publish_dir": {"type": "string"}
            },
            "additionalProperties": False
        }
    },
    {
        "name": "publish_deploy_site",
        "description": "Build and deploy the static weekly report site from a monitoring workspace, including git commit/push of the publish repo.",
        "inputSchema": {
            "type": "object",
            "required": ["workspace_root"],
            "properties": {
                "workspace_root": {"type": "string"},
                "publish_dir": {"type": "string"},
                "publish_url": {"type": "string"}
            },
            "additionalProperties": False
        }
    },
    {
        "name": "notify_wecom_weekly_report",
        "description": "Send or dry-run the Enterprise WeChat weekly report notification from a monitoring workspace.",
        "inputSchema": {
            "type": "object",
            "required": ["workspace_root"],
            "properties": {
                "workspace_root": {"type": "string"},
                "weekly_report_dir": {"type": "string"},
                "publish_url": {"type": "string"},
                "wecom_webhook_url": {"type": "string"},
                "dry_run": {"type": "boolean"}
            },
            "additionalProperties": False
        }
    },
    {
        "name": "run_full_weekly_pipeline",
        "description": "Run the end-to-end weekly competitor pipeline: APK version check and report generation, Web/admin monitoring, unified weekly report, static publish, and WeCom notification.",
        "inputSchema": {
            "type": "object",
            "required": ["workspace_root"],
            "properties": {
                "workspace_root": {"type": "string"},
                "app_url": {"type": "string"},
                "project_config": {"type": "string"},
                "apk_state": {"type": "string"},
                "apk_reports_root": {"type": "string"},
                "apk_report_dir": {"type": "string"},
                "preview_limit": {"type": "integer"},
                "run_web": {"type": "boolean"},
                "route_ids": {"type": "array", "items": {"type": "string"}},
                "web_report_dir": {"type": "string"},
                "run_weekly_report": {"type": "boolean"},
                "weekly_report_dir": {"type": "string"},
                "publish": {"type": "boolean"},
                "publish_dir": {"type": "string"},
                "publish_url": {"type": "string"},
                "notify": {"type": "boolean"},
                "notify_dry_run": {"type": "boolean"},
                "wecom_webhook_url": {"type": "string"}
            },
            "additionalProperties": False
        }
    },
]


RESOURCES = [
    {
        "uri": "file://README.md",
        "name": "Repository README",
        "description": "Top-level installation and usage guide for the APK competitor monitor plugin.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "file://apk-competitor-monitor/SKILL.md",
        "name": "Skill Workflow",
        "description": "Detailed skill workflow and reporting rules.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "file://apk-competitor-monitor/examples/config.example.json",
        "name": "Project Config Example",
        "description": "Reusable project configuration example for running the weekly pipeline with a Wandoujia APK source and project-specific Web/publish/notify settings.",
        "mimeType": "application/json",
    },
    {
        "uri": "file://apk-competitor-monitor/examples/web-monitor.config.example.json",
        "name": "Web Monitor Config Example",
        "description": "Example artifacts/web-monitor/config.json for onboarding a new competitor Web/admin target.",
        "mimeType": "application/json",
    },
    {
        "uri": "file://docs/web-monitor-onboarding.md",
        "name": "Web Monitor Onboarding Guide",
        "description": "Guide for configuring new competitor Web/admin monitoring routes, baselines, and redaction rules.",
        "mimeType": "text/markdown",
    },
]


def read_resource(uri):
    if uri == "file://README.md":
        path = WORKSPACE / "README.md"
    elif uri == "file://apk-competitor-monitor/SKILL.md":
        path = SKILL_DIR / "SKILL.md"
    elif uri == "file://apk-competitor-monitor/examples/config.example.json":
        path = SKILL_DIR / "examples" / "config.example.json"
    elif uri == "file://apk-competitor-monitor/examples/web-monitor.config.example.json":
        path = SKILL_DIR / "examples" / "web-monitor.config.example.json"
    elif uri == "file://docs/web-monitor-onboarding.md":
        path = WORKSPACE / "docs" / "web-monitor-onboarding.md"
    else:
        raise KeyError(f"Unknown resource: {uri}")
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": "application/json" if path.suffix == ".json" else "text/markdown",
                "text": path.read_text("utf-8"),
            }
        ]
    }


def handle_request(message):
    method = message.get("method")
    msg_id = message.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {
                    "name": "apk-competitor-monitor",
                    "version": "0.2.0",
                },
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                },
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = message.get("params", {})
        result = handle_tool_call(params.get("name"), params.get("arguments"))
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"resources": RESOURCES}}

    if method == "resources/read":
        params = message.get("params", {})
        result = read_resource(params.get("uri"))
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {
            "code": -32601,
            "message": f"Method not found: {method}",
        },
    }


def main():
    while True:
        message = read_message()
        if message is None:
            break
        try:
            response = handle_request(message)
        except subprocess.CalledProcessError as exc:
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {
                    "code": -32001,
                    "message": "Tool execution failed",
                    "data": {
                        "returncode": exc.returncode,
                        "stdout": exc.stdout,
                        "stderr": exc.stderr,
                    },
                },
            }
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {
                    "code": -32000,
                    "message": str(exc),
                },
            }
        if response is not None:
            send(response)


if __name__ == "__main__":
    main()
