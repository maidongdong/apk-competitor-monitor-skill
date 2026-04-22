#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
TOOLS_NS = "{http://schemas.android.com/tools}"
ATTRS = [
    "id",
    "text",
    "hint",
    "src",
    "background",
    "style",
    "visibility",
    "clickable",
    "contentDescription",
    "layout_width",
    "layout_height",
    "layout_margin",
    "layout_marginTop",
    "layout_marginBottom",
    "layout_marginStart",
    "layout_marginEnd",
]


def run(cmd, cwd=None, env=None):
    print("+", " ".join(map(str, cmd)))
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def local_name(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def clean_attr_name(name):
    if name.startswith(ANDROID_NS):
        return name[len(ANDROID_NS) :]
    if name.startswith(TOOLS_NS):
        return "tools:" + name[len(TOOLS_NS) :]
    return local_name(name)


def parse_values_file(path):
    values = {}
    if not path.exists():
        return values
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return values
    for child in root:
        name = child.attrib.get("name")
        if not name:
            continue
        tag = local_name(child.tag)
        if tag in {"string", "color", "style", "dimen", "bool", "integer"}:
            text = "".join(child.itertext()).strip()
            values[f"{tag}/{name}"] = text
    return values


def load_values(apktool_dir):
    values = {}
    values_dir = apktool_dir / "res" / "values"
    for filename in ["strings.xml", "colors.xml", "styles.xml", "dimens.xml", "bools.xml", "integers.xml"]:
        values.update(parse_values_file(values_dir / filename))
    return values


def resolve_ref(value, values):
    if not isinstance(value, str):
        return value
    if value.startswith("@"):
        key = value[1:]
        if key.startswith("+id/"):
            return value
        if key in values:
            return {"ref": value, "value": values[key]}
    return value


def parse_layout(path, values):
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        return {"name": path.stem, "path": str(path), "parse_error": str(exc), "views": []}
    views = []

    def walk(node, depth=0, index_path="0"):
        attrs = {}
        raw_id = None
        for key, value in node.attrib.items():
            name = clean_attr_name(key)
            if name in ATTRS or name.startswith("layout_"):
                attrs[name] = resolve_ref(value, values)
            if name == "id":
                raw_id = value
        view_id = None
        if raw_id:
            view_id = raw_id.split("/")[-1]
        signature = view_id or f"{index_path}:{local_name(node.tag)}"
        views.append(
            {
                "signature": signature,
                "id": view_id,
                "tag": local_name(node.tag),
                "depth": depth,
                "attrs": attrs,
            }
        )
        for idx, child in enumerate(list(node)):
            walk(child, depth + 1, f"{index_path}.{idx}")

    walk(root)
    return {
        "name": path.stem,
        "path": str(path),
        "root": local_name(root.tag),
        "view_count": len(views),
        "views": views,
        "hash": hashlib.sha1(json.dumps(views, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
    }


def collect_layouts(apktool_dir):
    values = load_values(apktool_dir)
    layouts = {}
    res = apktool_dir / "res"
    if not res.exists():
        return layouts
    for layout_dir in sorted(res.glob("layout*")):
        if not layout_dir.is_dir():
            continue
        for xml in sorted(layout_dir.glob("*.xml")):
            key = f"{layout_dir.name}/{xml.stem}"
            layouts[key] = parse_layout(xml, values)
    return layouts


def collect_resources(apktool_dir):
    res = apktool_dir / "res"
    values = load_values(apktool_dir)
    files = {}
    for prefix in ["drawable", "mipmap", "anim", "animator", "xml", "navigation", "menu", "color"]:
        for d in res.glob(f"{prefix}*"):
            if d.is_dir():
                for p in d.rglob("*"):
                    if p.is_file():
                        rel = str(p.relative_to(apktool_dir))
                        files[rel] = {"size": p.stat().st_size, "sha1": sha1_file(p)}
    return {"values": values, "files": files}


def diff_dict(old, new):
    old_keys = set(old)
    new_keys = set(new)
    changed = [k for k in sorted(old_keys & new_keys) if old[k] != new[k]]
    return {
        "added": sorted(new_keys - old_keys),
        "removed": sorted(old_keys - new_keys),
        "changed": changed,
    }


def diff_layout(old_layout, new_layout):
    old_views = {v["signature"]: v for v in old_layout.get("views", [])}
    new_views = {v["signature"]: v for v in new_layout.get("views", [])}
    added = [new_views[k] for k in sorted(set(new_views) - set(old_views))]
    removed = [old_views[k] for k in sorted(set(old_views) - set(new_views))]
    changed = []
    for sig in sorted(set(old_views) & set(new_views)):
        old_v = old_views[sig]
        new_v = new_views[sig]
        if old_v.get("tag") != new_v.get("tag") or old_v.get("attrs") != new_v.get("attrs"):
            changed.append({"signature": sig, "old": old_v, "new": new_v})
    return {"added_views": added, "removed_views": removed, "changed_views": changed}


def binding_to_layout(name):
    base = re.sub(r"Binding$", "", name)
    words = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z]|$)", base)
    return "_".join(w.lower() for w in words if w)


def map_jadx(jadx_dir):
    mappings = {}
    reverse = {}
    if not jadx_dir.exists():
        return {"class_to_layout": mappings, "layout_to_classes": reverse, "status": "missing"}
    layout_re = re.compile(r"R\.layout\.([A-Za-z0-9_]+)")
    binding_re = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:Activity|Fragment|Dialog|BottomSheet|Item|Layout)?Binding)\b")
    for path in jadx_dir.rglob("*"):
        if path.suffix not in {".java", ".kt"}:
            continue
        try:
            text = path.read_text("utf-8", errors="ignore")
        except Exception:
            continue
        rel = str(path.relative_to(jadx_dir))
        cls = rel.rsplit(".", 1)[0].replace("/", ".")
        layouts = set(layout_re.findall(text))
        for binding in binding_re.findall(text):
            layout = binding_to_layout(binding)
            if layout:
                layouts.add(layout)
        if layouts:
            mappings[cls] = sorted(layouts)
            for layout in layouts:
                reverse.setdefault(layout, []).append(cls)
    return {"class_to_layout": mappings, "layout_to_classes": {k: sorted(v) for k, v in reverse.items()}, "status": "ok"}


def ensure_apktool(label, apk, out_root, force=False):
    out = out_root / label / "apktool"
    if force and out.exists():
        shutil.rmtree(out)
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        frame_path = out_root / "_apktool-framework"
        frame_path.mkdir(parents=True, exist_ok=True)
        run(["apktool", "d", "-f", "-q", "-p", str(frame_path), str(apk), "-o", str(out)])
    return out


def ensure_jadx(label, apk, out_root, force=False):
    out = out_root / label / "jadx"
    if force and out.exists():
        shutil.rmtree(out)
    if not shutil.which("jadx"):
        return out, "jadx_not_found"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        app_home = out_root / "_jadx-home"
        (app_home / ".config").mkdir(parents=True, exist_ok=True)
        (app_home / ".cache").mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(app_home),
                "XDG_CONFIG_HOME": str(app_home / ".config"),
                "XDG_CACHE_HOME": str(app_home / ".cache"),
            }
        )
        java_options = env.get("JAVA_TOOL_OPTIONS", "")
        env["JAVA_TOOL_OPTIONS"] = f"{java_options} -Duser.home={app_home}".strip()
        try:
            run(["jadx", "-q", "--no-res", "--no-imports", "-d", str(out), str(apk)], env=env)
        except subprocess.CalledProcessError:
            return out, "jadx_failed"
    return out, "ok"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("old_label")
    parser.add_argument("old_apk")
    parser.add_argument("new_label")
    parser.add_argument("new_apk")
    parser.add_argument("--out-root", default="artifacts/apk-monitor/decompiled")
    parser.add_argument("--output", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-jadx", action="store_true")
    args = parser.parse_args()

    out_root = Path(args.out_root)
    old_apk = Path(args.old_apk)
    new_apk = Path(args.new_apk)
    old_apktool = ensure_apktool(args.old_label, old_apk, out_root, args.force)
    new_apktool = ensure_apktool(args.new_label, new_apk, out_root, args.force)

    old_layouts = collect_layouts(old_apktool)
    new_layouts = collect_layouts(new_apktool)
    layout_keys = diff_dict(old_layouts, new_layouts)
    layout_changes = {}
    for key in layout_keys["changed"]:
        old_l = old_layouts[key]
        new_l = new_layouts[key]
        if old_l.get("hash") != new_l.get("hash"):
            layout_changes[key] = diff_layout(old_l, new_l)

    old_res = collect_resources(old_apktool)
    new_res = collect_resources(new_apktool)
    old_jadx, old_jadx_status = (Path(), "skipped")
    new_jadx, new_jadx_status = (Path(), "skipped")
    old_map = {"status": "skipped", "class_to_layout": {}, "layout_to_classes": {}}
    new_map = {"status": "skipped", "class_to_layout": {}, "layout_to_classes": {}}
    if not args.skip_jadx:
        old_jadx, old_jadx_status = ensure_jadx(args.old_label, old_apk, out_root, args.force)
        new_jadx, new_jadx_status = ensure_jadx(args.new_label, new_apk, out_root, args.force)
        old_map = map_jadx(old_jadx)
        new_map = map_jadx(new_jadx)
        old_map["decode_status"] = old_jadx_status
        new_map["decode_status"] = new_jadx_status

    report = {
        "old": {"label": args.old_label, "apk": str(old_apk), "apktool": str(old_apktool), "layout_count": len(old_layouts)},
        "new": {"label": args.new_label, "apk": str(new_apk), "apktool": str(new_apktool), "layout_count": len(new_layouts)},
        "layouts": {
            "added": layout_keys["added"],
            "removed": layout_keys["removed"],
            "changed": [k for k in layout_keys["changed"] if k in layout_changes],
            "changed_details": layout_changes,
            "added_details": {k: new_layouts[k] for k in layout_keys["added"][:120]},
            "removed_details": {k: old_layouts[k] for k in layout_keys["removed"][:120]},
        },
        "resources": {
            "values": diff_dict(old_res["values"], new_res["values"]),
            "files": diff_dict(old_res["files"], new_res["files"]),
        },
        "mapping": {"old": old_map, "new": new_map},
    }
    output = Path(args.output) if args.output else Path(f"artifacts/apk-monitor/ui-layout-diff-{args.old_label}-to-{args.new_label}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "old_layouts": len(old_layouts),
        "new_layouts": len(new_layouts),
        "layouts_added": len(report["layouts"]["added"]),
        "layouts_removed": len(report["layouts"]["removed"]),
        "layouts_changed": len(report["layouts"]["changed"]),
        "resource_values_added": len(report["resources"]["values"]["added"]),
        "resource_values_removed": len(report["resources"]["values"]["removed"]),
        "resource_values_changed": len(report["resources"]["values"]["changed"]),
        "resource_files_added": len(report["resources"]["files"]["added"]),
        "resource_files_removed": len(report["resources"]["files"]["removed"]),
        "resource_files_changed": len(report["resources"]["files"]["changed"]),
        "jadx_old": old_map.get("status"),
        "jadx_new": new_map.get("status"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
