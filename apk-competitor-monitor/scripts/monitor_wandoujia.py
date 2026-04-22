#!/usr/bin/env python3
import argparse
import html
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


UA = "Mozilla/5.0"


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read().decode("utf-8", "replace")


def find_attr(html_text, name):
    match = re.search(rf'{re.escape(name)}="([^"]*)"', html_text)
    return html.unescape(match.group(1)) if match else None


def parse_app_page(url):
    text = fetch_text(url)
    app_id = find_attr(text, "data-app-id")
    return {
        "url": url,
        "app_id": app_id,
        "package": find_attr(text, "data-pn"),
        "version_code": int(find_attr(text, "data-app-vcode") or 0),
        "version_name": find_attr(text, "data-app-vname"),
        "version_id": find_attr(text, "data-app-vid"),
        "title": find_attr(text, "data-title"),
        "html": text,
    }


def parse_history_page(url):
    text = fetch_text(url)
    data_href = re.search(r'data-href="([^"]+\.apk[^"]*)"', text)
    if not data_href:
        raise RuntimeError(f"Could not find APK download URL in {url}")
    version_name = re.search(r"官方版本号：.*?<span><a[^>]*>(.*?)</a>", text, re.S)
    updated = re.search(r"更新时间：([^<]+)", text)
    vcode_match = re.search(r"history_v(\d+)", url)
    return {
        "url": url,
        "version_code": int(vcode_match.group(1)) if vcode_match else 0,
        "version_name": re.sub(r"^v+", "v", version_name.group(1).strip()) if version_name else None,
        "updated_at": updated.group(1).strip() if updated else None,
        "download_url": html.unescape(data_href.group(1)).replace("&amp;", "&"),
        "html": text,
    }


def latest_download_url(app_url):
    # Wandoujia redirects this endpoint to the current APK.
    return app_url.rstrip("/") + "/download/dot?ch=detail_normal_dl&pos=detail-common_download_main"


def download(url, out_path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as resp, open(out_path, "wb") as f:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)


def run(cmd, cwd):
    print("+", " ".join(map(str, cmd)))
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-url", required=True)
    parser.add_argument("--state", default="artifacts/apk-monitor/state.json")
    parser.add_argument("--out-root", default="reports")
    parser.add_argument("--workspace", default=".")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    state_path = workspace / args.state
    out_root = workspace / args.out_root
    state = json.loads(state_path.read_text("utf-8")) if state_path.exists() else {}

    latest = parse_app_page(args.app_url)
    previous_code = int(state.get("latest", {}).get("version_code") or 0)
    if previous_code and latest["version_code"] <= previous_code:
        print(json.dumps({"status": "no_new_version", "latest": latest["version_code"], "known": previous_code}, ensure_ascii=False))
        return

    if not previous_code:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"latest": {k: v for k, v in latest.items() if k != "html"}}, ensure_ascii=False, indent=2), "utf-8")
        print(json.dumps({"status": "initialized", "latest": latest["version_code"]}, ensure_ascii=False))
        return

    old = state["latest"]
    app_id = latest["app_id"] or re.search(r"/apps/(\d+)", args.app_url).group(1)
    old_history_url = f"https://www.wandoujia.com/apps/{app_id}/history_v{old['version_code']}"
    old_meta = parse_history_page(old_history_url)

    report_dir = out_root / f"{latest['package'] or app_id}-{old['version_code']}-to-{latest['version_code']}"
    apk_dir = report_dir / "apks"
    old_apk = apk_dir / f"{old['version_code']}.apk"
    new_apk = apk_dir / f"{latest['version_code']}.apk"
    download(old_meta["download_url"], old_apk)
    download(latest_download_url(args.app_url), new_apk)

    skill_dir = Path(__file__).resolve().parents[1]
    run([sys.executable, str(skill_dir / "scripts" / "analyze_apk_diff.py"), str(old["version_code"]), str(old_apk), str(latest["version_code"]), str(new_apk)], workspace)

    state["latest"] = {k: v for k, v in latest.items() if k != "html"}
    state["last_report_dir"] = str(report_dir)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"status": "new_version_analyzed", "report_dir": str(report_dir), "old": old["version_code"], "new": latest["version_code"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
