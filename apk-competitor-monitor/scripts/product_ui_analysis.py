import argparse
import collections
import json
import re
import struct
import zipfile
from importlib.machinery import SourceFileLoader
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
apkdiff = SourceFileLoader("apkdiff", str(SCRIPT_DIR / "analyze_apk_diff.py")).load_module()


CATEGORIES = {
    "安全模式": ["safemode", "safe_mode", "safe mode", "安全模式"],
    "团队照片标签/台账": ["photo_label", "/group/photo/label", "photolabel", "ledger", "台账", "标签"],
    "微信绑定/验证": ["wechat", "wx", "微信", "vericode", "verify", "bind"],
    "会员/VIP": ["vip", "member", "benefit", "expire", "会员", "权益"],
    "定位/位置锁定": ["location", "poi", "gps", "gaode", "amap", "tencent", "radius", "位置", "定位"],
    "工作组/桌面组件": ["workgroup", "work_group", "desktopwidget", "widget", "团队", "工作组"],
    "拼图/图片编辑": ["puzzle", "insert", "textedit", "add_pic", "add_note", "拼图"],
    "广告商业化": ["ad", "ads", "adx", "bidding", "topon", "union", "splash"],
    "崩溃/性能监控": ["bugly", "rmonitor", "oom", "hprof", "asan", "crash", "heapdump"],
    "视频/RTC/拍摄底层": ["rtc", "bytertc", "realx", "camera", "video", "h265", "ffmpeg", "bae"],
    "AI/智能助手": ["ai", "agent", "assistant", "智能"],
    "上传/同步": ["upload", "sync", "cloud", "queue", "同步", "上传"],
}


def collect(apk_path):
    zf = zipfile.ZipFile(apk_path)
    dex_strings = []
    for info in zf.infolist():
        if re.fullmatch(r"classes\d*\.dex", info.filename):
            dex_strings.extend(apkdiff.dex_strings(zf.read(info.filename)))
    res_strings = apkdiff.arsc_strings(zf.read("resources.arsc"))
    manifest = apkdiff.parse_manifest(zf.read("AndroidManifest.xml"))
    files = {i.filename: {"size": i.file_size, "crc": i.CRC} for i in zf.infolist() if not i.is_dir()}
    return {
        "dex": set(dex_strings),
        "res": set(res_strings),
        "manifest": manifest,
        "files": files,
        "urls": set(u.rstrip(".,);]'\"") for s in set(dex_strings) | set(res_strings) for u in apkdiff.URL_RE.findall(s)),
        "apis": set(a for s in set(dex_strings) | set(res_strings) for a in apkdiff.API_RE.findall(s) if len(a) < 180),
        "events": set(s for s in set(dex_strings) | set(res_strings) if 8 <= len(s) <= 80 and apkdiff.EVENT_RE.match(s)),
    }


def classify(items, limit=120):
    result = {name: [] for name in CATEGORIES}
    for item in sorted(items):
        if len(item) > 300:
            continue
        low = item.lower()
        for name, words in CATEGORIES.items():
            if any(word in low for word in words):
                if len(result[name]) < limit:
                    result[name].append(item)
    return {k: v for k, v in result.items() if v}


def summarize_file_changes(old_files, new_files):
    added = sorted(set(new_files) - set(old_files))
    removed = sorted(set(old_files) - set(new_files))
    changed = sorted(k for k in set(old_files) & set(new_files) if old_files[k] != new_files[k])
    def bucket(paths):
        c = collections.Counter()
        for p in paths:
            if p.startswith("res/"):
                c["res/" + p.split("/")[1].split("-")[0]] += 1
            elif p.startswith("assets/"):
                c["assets"] += 1
            elif p.startswith("lib/"):
                c["native_lib"] += 1
            elif p.endswith(".dex"):
                c["dex"] += 1
            elif p.startswith("META-INF/"):
                c["meta_inf"] += 1
            else:
                c[p.split("/")[0]] += 1
        return c.most_common(50)
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "added_bucket": bucket(added),
        "removed_bucket": bucket(removed),
        "changed_bucket": bucket(changed),
    }


def image_size_from_zip(zf, name):
    data = zf.read(name)
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return "png", struct.unpack(">II", data[16:24])
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            i += 2
            if marker in (0xD8, 0xD9):
                continue
            if i + 2 > len(data):
                break
            seg_len = struct.unpack(">H", data[i : i + 2])[0]
            if marker in range(0xC0, 0xC4) and i + 7 < len(data):
                h, w = struct.unpack(">HH", data[i + 3 : i + 7])
                return "jpg", (w, h)
            i += seg_len
    return None, None


def image_changes(old_apk, new_apk, old_files, new_files):
    zold, znew = zipfile.ZipFile(old_apk), zipfile.ZipFile(new_apk)
    image_ext = (".png", ".jpg", ".jpeg", ".webp")
    added = sorted(p for p in set(new_files) - set(old_files) if p.lower().endswith(image_ext))
    removed = sorted(p for p in set(old_files) - set(new_files) if p.lower().endswith(image_ext))
    changed = sorted(p for p in set(old_files) & set(new_files) if p.lower().endswith(image_ext) and old_files[p] != new_files[p])
    def sample(zf, paths):
        out = []
        for p in paths[:80]:
            kind, size = image_size_from_zip(zf, p)
            out.append({"path": p, "format": kind, "size": size})
        return out
    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "added_sample": sample(znew, added),
        "removed_sample": sample(zold, removed),
        "changed_sample": sample(znew, changed),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("old_label")
    parser.add_argument("old_apk")
    parser.add_argument("new_label")
    parser.add_argument("new_apk")
    parser.add_argument("--output")
    args = parser.parse_args()

    old_apk = Path(args.old_apk)
    new_apk = Path(args.new_apk)
    old = collect(old_apk)
    new = collect(new_apk)
    diffs = {
        "resource_strings_added": sorted(new["res"] - old["res"]),
        "resource_strings_removed": sorted(old["res"] - new["res"]),
        "dex_strings_added": sorted(new["dex"] - old["dex"]),
        "dex_strings_removed": sorted(old["dex"] - new["dex"]),
        "urls_added": sorted(new["urls"] - old["urls"]),
        "urls_removed": sorted(old["urls"] - new["urls"]),
        "apis_added": sorted(new["apis"] - old["apis"]),
        "apis_removed": sorted(old["apis"] - new["apis"]),
        "events_added": sorted(new["events"] - old["events"]),
        "events_removed": sorted(old["events"] - new["events"]),
    }
    report = {
        "scope": {
            "old": args.old_label,
            "new": args.new_label,
            "old_apk": str(old_apk),
            "new_apk": str(new_apk),
        },
        "counts": {k: len(v) for k, v in diffs.items()},
        "files": {
            k: v
            for k, v in summarize_file_changes(old["files"], new["files"]).items()
            if k.endswith("_bucket")
        },
        "images": image_changes(old_apk, new_apk, old["files"], new["files"]),
        "manifest": {
            "permissions_added": sorted(set(new["manifest"].get("permissions", [])) - set(old["manifest"].get("permissions", []))),
            "permissions_removed": sorted(set(old["manifest"].get("permissions", [])) - set(new["manifest"].get("permissions", []))),
            "activities_added": sorted(set(new["manifest"].get("activities", [])) - set(old["manifest"].get("activities", []))),
            "activities_removed": sorted(set(old["manifest"].get("activities", [])) - set(new["manifest"].get("activities", []))),
        },
        "classified": {
            "resource_strings_added": classify(diffs["resource_strings_added"]),
            "resource_strings_removed": classify(diffs["resource_strings_removed"]),
            "dex_strings_added": classify(diffs["dex_strings_added"]),
            "dex_strings_removed": classify(diffs["dex_strings_removed"]),
            "apis_added": classify(diffs["apis_added"]),
            "apis_removed": classify(diffs["apis_removed"]),
            "events_added": classify(diffs["events_added"]),
            "events_removed": classify(diffs["events_removed"]),
            "urls_added": classify(diffs["urls_added"]),
            "urls_removed": classify(diffs["urls_removed"]),
        },
        "samples": {
            k: [x for x in v if len(x) <= 160][:120]
            for k, v in diffs.items()
        },
    }
    out = Path(args.output) if args.output else Path(f"product-ui-analysis-{args.old_label}-to-{args.new_label}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "out": str(out),
        "counts": report["counts"],
        "manifest": report["manifest"],
        "file_buckets": {
            "added": report["files"]["added_bucket"][:20],
            "removed": report["files"]["removed_bucket"][:20],
            "changed": report["files"]["changed_bucket"][:20],
        },
        "images": {k: report["images"][k] for k in ["added_count", "removed_count", "changed_count"]},
        "classified_categories": {
            section: {cat: len(items) for cat, items in cats.items()}
            for section, cats in report["classified"].items()
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
