#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


KEYWORDS = {
    "安全模式": ["safe_mode", "safemode", "safe"],
    "团队照片标签/台账": ["photo_label", "label_group", "label_select", "photo_status"],
    "微信绑定/验证": ["wechat", "verify", "bind_new_phone", "code_error", "phone_occupied"],
    "会员/VIP": ["vip", "member"],
    "定位/位置锁定": ["location", "poi", "lock_location"],
    "工作组/桌面组件": ["work_group", "workgroup", "widget", "group_desktop"],
    "拼图/图片编辑": ["puzzle", "insert_below", "text_bottom"],
    "上传/同步": ["upload", "sync"],
}


def categorize(name):
    low = name.lower()
    for category, words in KEYWORDS.items():
        if any(word in low for word in words):
            return category
    return "其他 UI"


def short_view(view):
    attrs = view.get("attrs", {})
    keep = {}
    for key in ["id", "text", "hint", "src", "background", "style", "visibility", "clickable", "contentDescription"]:
        if key in attrs:
            keep[key] = attrs[key]
    return {
        "signature": view.get("signature"),
        "id": view.get("id"),
        "tag": view.get("tag"),
        "depth": view.get("depth"),
        "attrs": keep,
    }


def layout_key(name):
    return name.rsplit("/", 1)[-1]


def layout_classes(mapping, name):
    classes = mapping.get("layout_to_classes", {}).get(layout_key(name), [])
    return classes[:12]


def layout_card(name, detail, change, mapping):
    views = detail.get("views", [])
    return {
        "name": name,
        "category": categorize(name),
        "change": change,
        "classes": layout_classes(mapping, name),
        "root": detail.get("root"),
        "viewCount": detail.get("view_count", len(views)),
        "views": [short_view(v) for v in views[:40]],
    }


def changed_card(name, change, mapping):
    return {
        "name": name,
        "category": categorize(name),
        "change": "changed",
        "classes": layout_classes(mapping, name),
        "addedViews": [short_view(v) for v in change.get("added_views", [])[:25]],
        "removedViews": [short_view(v) for v in change.get("removed_views", [])[:25]],
        "changedViews": [
            {
                "signature": item.get("signature"),
                "old": short_view(item.get("old", {})),
                "new": short_view(item.get("new", {})),
            }
            for item in change.get("changed_views", [])[:25]
        ],
        "counts": {
            "addedViews": len(change.get("added_views", [])),
            "removedViews": len(change.get("removed_views", [])),
            "changedViews": len(change.get("changed_views", [])),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ui_layout_diff")
    parser.add_argument("--out", default="web-report/ui-layout-data.json")
    args = parser.parse_args()

    data = json.loads(Path(args.ui_layout_diff).read_text("utf-8"))
    layouts = data["layouts"]
    resources = data["resources"]
    mapping = data.get("mapping", {})
    old_mapping = mapping.get("old", {})
    new_mapping = mapping.get("new", {})
    added = [layout_card(name, detail, "added", new_mapping) for name, detail in layouts.get("added_details", {}).items()]
    removed = [layout_card(name, detail, "removed", old_mapping) for name, detail in layouts.get("removed_details", {}).items()]
    changed = [changed_card(name, detail, new_mapping) for name, detail in layouts.get("changed_details", {}).items()]
    categories = {}
    for item in added + removed + changed:
        categories[item["category"]] = categories.get(item["category"], 0) + 1
    output = {
        "source": args.ui_layout_diff,
        "old": data.get("old"),
        "new": data.get("new"),
        "summary": {
            "layoutsAdded": len(layouts.get("added", [])),
            "layoutsRemoved": len(layouts.get("removed", [])),
            "layoutsChanged": len(layouts.get("changed", [])),
            "resourceValuesAdded": len(resources["values"].get("added", [])),
            "resourceValuesRemoved": len(resources["values"].get("removed", [])),
            "resourceValuesChanged": len(resources["values"].get("changed", [])),
            "resourceFilesAdded": len(resources["files"].get("added", [])),
            "resourceFilesRemoved": len(resources["files"].get("removed", [])),
            "resourceFilesChanged": len(resources["files"].get("changed", [])),
            "categories": categories,
            "mappingOldStatus": old_mapping.get("status"),
            "mappingNewStatus": new_mapping.get("status"),
            "mappingNewClasses": len(new_mapping.get("class_to_layout", {})),
            "mappingNewLayoutLinks": len(new_mapping.get("layout_to_classes", {})),
        },
        "layouts": {
            "added": added,
            "removed": removed,
            "changed": changed,
        },
        "resources": {
            "valuesAdded": resources["values"].get("added", [])[:160],
            "valuesRemoved": resources["values"].get("removed", [])[:160],
            "valuesChanged": resources["values"].get("changed", [])[:160],
            "filesAdded": resources["files"].get("added", [])[:160],
            "filesRemoved": resources["files"].get("removed", [])[:160],
            "filesChanged": resources["files"].get("changed", [])[:160],
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "summary": output["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
