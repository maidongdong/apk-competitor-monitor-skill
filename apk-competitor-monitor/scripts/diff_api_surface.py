#!/usr/bin/env python3
import argparse
import collections
import json
from pathlib import Path


def load_json(path):
    return json.loads(Path(path).read_text("utf-8"))


def hit_key(hit):
    return (
        hit.get("kind") or "",
        hit.get("class") or "",
        hit.get("method") or "",
        hit.get("value") or "",
        hit.get("http_method") or "",
        hit.get("annotation") or "",
    )


def short_hit(hit):
    keep = ["kind", "class", "method", "value", "http_method", "annotation", "file", "line"]
    return {key: hit.get(key) for key in keep if hit.get(key) is not None}


def classify_module(values):
    text = " ".join(str(value) for value in values if value).lower()
    modules = [
        ("安全模式", ["safemode", "safe_mode", "safe mode", "safe"]),
        ("拼图/图片编辑", ["puzzle", "jigsaw", "insertbelow", "insert_down", "insertmedia", "textedit"]),
        ("团队/工作组", ["team", "group", "workgroup", "work_group", "workspace"]),
        ("会员/VIP", ["vip", "member", "pay", "subscribe", "payment", "benefit"]),
        ("微信绑定/验证", ["wechat", "wx", "verify", "captcha", "bind", "auth"]),
        ("定位/位置", ["location", "gps", "poi", "amap", "gaode", "map"]),
        ("上传/同步", ["upload", "sync", "cloud", "queue"]),
        ("WebView/H5", ["webview", "h5", "loadurl", "javascript"]),
        ("广告商业化", ["ad", "ads", "splash", "bidding", "union"]),
        ("拍摄/相机", ["camera", "video", "watermark", "photo"]),
    ]
    for name, words in modules:
        if any(word in text for word in words):
            return name
    return "未归类功能"


def summarize(items):
    by_kind = collections.Counter(item.get("kind") for item in items)
    by_module = collections.Counter(
        classify_module([item.get("class"), item.get("method"), item.get("value"), item.get("file")])
        for item in items
    )
    by_class = collections.Counter(item.get("class") for item in items)
    return {
        "by_kind": dict(by_kind.most_common()),
        "by_module": dict(by_module.most_common()),
        "top_classes": [{"class": key, "count": value} for key, value in by_class.most_common(40) if key],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("old_api_surface")
    parser.add_argument("new_api_surface")
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    old = load_json(args.old_api_surface)
    new = load_json(args.new_api_surface)
    old_by_key = {hit_key(hit): hit for hit in old.get("hits", [])}
    new_by_key = {hit_key(hit): hit for hit in new.get("hits", [])}
    added_keys = sorted(set(new_by_key) - set(old_by_key))
    removed_keys = sorted(set(old_by_key) - set(new_by_key))
    common_keys = sorted(set(old_by_key) & set(new_by_key))

    added = [short_hit(new_by_key[key]) for key in added_keys[: args.limit]]
    removed = [short_hit(old_by_key[key]) for key in removed_keys[: args.limit]]
    changed_classes = sorted(
        set(new_by_key[key].get("class") for key in added_keys)
        | set(old_by_key[key].get("class") for key in removed_keys)
    )
    changed_values = sorted(
        set(str(new_by_key[key].get("value")) for key in added_keys)
        | set(str(old_by_key[key].get("value")) for key in removed_keys)
    )

    report = {
        "old": {
            "path": str(Path(args.old_api_surface)),
            "hit_count": old.get("hit_count", 0),
        },
        "new": {
            "path": str(Path(args.new_api_surface)),
            "hit_count": new.get("hit_count", 0),
        },
        "summary": {
            "hits_added": len(added_keys),
            "hits_removed": len(removed_keys),
            "hits_unchanged": len(common_keys),
            "net_hit_delta": new.get("hit_count", 0) - old.get("hit_count", 0),
            "added": summarize(added),
            "removed": summarize(removed),
        },
        "added": added,
        "removed": removed,
        "changed_classes": [cls for cls in changed_classes if cls],
        "changed_values": changed_values[: args.limit],
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"out": str(out), "summary": report["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
