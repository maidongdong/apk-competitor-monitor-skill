#!/usr/bin/env python3
import json
import platform
import shutil
import subprocess


DEPENDENCIES = [
    {
        "name": "python3",
        "kind": "required",
        "purpose": "Run the monitor scripts and MCP server.",
        "install": "Install Python 3.9+.",
        "version_args": ["--version"],
    },
    {
        "name": "java",
        "kind": "recommended",
        "purpose": "Run apktool, jadx, and optional Vineflower/Fernflower.",
        "install": "Install OpenJDK.",
        "version_args": ["-version"],
    },
    {
        "name": "apktool",
        "kind": "recommended",
        "purpose": "Decode Android resources, layouts, manifests, and values.",
        "install": "macOS: brew install apktool. Other systems: install from https://apktool.org/.",
        "version_args": ["--version"],
    },
    {
        "name": "jadx",
        "kind": "recommended",
        "purpose": "Decompile DEX to Java for API extraction and screen ownership mapping.",
        "install": "macOS: brew install jadx. Other systems: install from https://github.com/skylot/jadx.",
        "version_args": ["--version"],
    },
    {
        "name": "d2j-dex2jar",
        "kind": "optional",
        "purpose": "Convert DEX to JAR for Fernflower/Vineflower fallback decompilation.",
        "install": "Install dex2jar and expose d2j-dex2jar or d2j-dex2jar.sh on PATH.",
        "aliases": ["d2j-dex2jar.sh"],
        "version_args": ["--version"],
    },
    {
        "name": "vineflower",
        "kind": "optional",
        "purpose": "Second Java decompiler engine for complex code and method-level comparison.",
        "install": "Install Vineflower or set VINEFLOWER_JAR_PATH / FERNFLOWER_JAR_PATH.",
        "aliases": ["fernflower"],
        "version_args": ["--version"],
    },
    {
        "name": "chrome",
        "kind": "optional",
        "purpose": "Export HTML reports to PDF.",
        "install": "Install Chrome/Chromium or Python Playwright.",
        "aliases": ["google-chrome", "chromium", "chromium-browser"],
        "version_args": ["--version"],
    },
]


def command_version(command, version_args):
    try:
        completed = subprocess.run(
            [command, *version_args],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception:
        return "", False
    text = (completed.stdout or completed.stderr or "").strip()
    first_line = text.splitlines()[0] if text else ""
    return first_line, completed.returncode == 0


def find_command(dep):
    candidates = [dep["name"], *(dep.get("aliases") or [])]
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return candidate, path
    return None, None


def main():
    results = []
    missing_required = []
    missing_recommended = []
    missing_optional = []

    for dep in DEPENDENCIES:
        command, path = find_command(dep)
        item = {
            "name": dep["name"],
            "kind": dep["kind"],
            "available": bool(path),
            "path": path,
            "purpose": dep["purpose"],
            "install": dep["install"],
        }
        if path:
            item["command"] = command
            version, version_ok = command_version(command, dep.get("version_args", ["--version"]))
            item["version"] = version
            if not version_ok and dep["name"] == "java":
                item["available"] = False
                item["diagnostic"] = version or "java command failed"
        elif dep["kind"] == "required":
            missing_required.append(dep["name"])
        elif dep["kind"] == "recommended":
            missing_recommended.append(dep["name"])
        else:
            missing_optional.append(dep["name"])
        if path and not item["available"]:
            if dep["kind"] == "required":
                missing_required.append(dep["name"])
            elif dep["kind"] == "recommended":
                missing_recommended.append(dep["name"])
            else:
                missing_optional.append(dep["name"])
        results.append(item)

    status = "ok"
    if missing_required:
        status = "blocked"
    elif missing_recommended:
        status = "partial"

    output = {
        "status": status,
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "missing": {
            "required": missing_required,
            "recommended": missing_recommended,
            "optional": missing_optional,
        },
        "dependencies": results,
        "next_actions": [
            item["install"]
            for item in results
            if not item["available"] and item["kind"] in {"required", "recommended"}
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
