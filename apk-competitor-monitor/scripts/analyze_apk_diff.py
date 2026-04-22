import collections
import hashlib
import json
import re
import struct
import sys
import zipfile
from pathlib import Path


URL_RE = re.compile(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")
DOMAIN_RE = re.compile(r"(?<![A-Za-z0-9_-])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?![A-Za-z0-9_-])")
API_RE = re.compile(r"/(?:api|v\d|[A-Za-z0-9_-]{2,})(?:/[A-Za-z0-9._~:@!$&'()*+,;=%-]{1,}){1,}")
EVENT_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+){2,}$")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def uleb128(data, off):
    result = 0
    shift = 0
    while True:
        b = data[off]
        off += 1
        result |= (b & 0x7F) << shift
        if b < 0x80:
            return result, off
        shift += 7


def dex_strings(data):
    if data[:3] != b"dex":
        return []
    try:
        string_ids_size, string_ids_off = struct.unpack_from("<II", data, 0x38)
    except Exception:
        return []
    out = []
    for i in range(string_ids_size):
        try:
            (string_off,) = struct.unpack_from("<I", data, string_ids_off + i * 4)
            _, p = uleb128(data, string_off)
            end = data.find(b"\x00", p)
            if end < 0:
                continue
            s = data[p:end].decode("utf-8", "replace")
            if s and len(s) <= 800:
                out.append(s)
        except Exception:
            pass
    return out


def parse_string_pool(data, off):
    try:
        typ, header_size, size = struct.unpack_from("<HHI", data, off)
        if typ != 0x0001 or size <= header_size or off + size > len(data):
            return []
        string_count, _, flags, strings_start, _ = struct.unpack_from("<IIIII", data, off + 8)
        utf8 = bool(flags & 0x00000100)
        if string_count > 300000:
            return []
        pos = off + header_size
        offsets = [struct.unpack_from("<I", data, pos + i * 4)[0] for i in range(string_count)]
        base = off + strings_start
        out = []
        for rel in offsets:
            p = base + rel
            if p >= off + size:
                continue
            try:
                if utf8:
                    _, p = uleb128(data, p)
                    byte_len, p = uleb128(data, p)
                    s = data[p : p + byte_len].decode("utf-8", "replace")
                else:
                    char_len = struct.unpack_from("<H", data, p)[0]
                    p += 2
                    if char_len & 0x8000:
                        lo = struct.unpack_from("<H", data, p)[0]
                        p += 2
                        char_len = ((char_len & 0x7FFF) << 16) | lo
                    s = data[p : p + char_len * 2].decode("utf-16le", "replace")
                if s:
                    out.append(s)
            except Exception:
                pass
        return out
    except Exception:
        return []


def parse_manifest(data):
    strings = []
    off = 8
    while off + 8 <= len(data):
        typ, _, size = struct.unpack_from("<HHI", data, off)
        if typ == 0x0001:
            strings = parse_string_pool(data, off)
            break
        if size <= 0:
            break
        off += size

    def get(idx):
        return strings[idx] if 0 <= idx < len(strings) else None

    found = collections.defaultdict(list)
    app_attrs = {}
    package = None
    version_name = None
    version_code = None
    min_sdk = None
    target_sdk = None
    off = 8
    while off + 8 <= len(data):
        typ, _, size = struct.unpack_from("<HHI", data, off)
        if size <= 0 or off + size > len(data):
            break
        if typ == 0x0102:
            name_idx = struct.unpack_from("<I", data, off + 20)[0]
            tag = get(name_idx) or f"#{name_idx}"
            attr_start, attr_size, attr_count = struct.unpack_from("<HHH", data, off + 24)
            attrs = {}
            # attributeStart is relative to ResXMLTree_attrExt, which begins
            # after the 16-byte ResXMLTree_node header.
            ap = off + 16 + attr_start
            for i in range(attr_count):
                try:
                    _, attr_name_idx, raw_idx, _, _, dtype, data_val = struct.unpack_from(
                        "<IIIHBBI", data, ap + i * attr_size
                    )
                    attr_name = get(attr_name_idx) or str(attr_name_idx)
                    val = get(raw_idx) if raw_idx != 0xFFFFFFFF else None
                    if val is None:
                        if dtype == 0x03:
                            val = get(data_val)
                        elif dtype == 0x12:
                            val = str(bool(data_val))
                        elif dtype in (0x10, 0x11):
                            val = str(data_val)
                        else:
                            val = hex(data_val)
                    attrs[attr_name] = val
                except Exception:
                    pass
            if tag == "manifest":
                package = attrs.get("package")
                version_name = attrs.get("versionName")
                version_code = attrs.get("versionCode")
            elif tag == "uses-sdk":
                min_sdk = attrs.get("minSdkVersion")
                target_sdk = attrs.get("targetSdkVersion")
            elif tag == "application":
                app_attrs = attrs
            elif tag == "uses-permission" and attrs.get("name"):
                found["permissions"].append(attrs["name"])
            elif tag in ("activity", "activity-alias") and attrs.get("name"):
                found["activities"].append(attrs["name"])
            elif tag == "service" and attrs.get("name"):
                found["services"].append(attrs["name"])
            elif tag == "receiver" and attrs.get("name"):
                found["receivers"].append(attrs["name"])
            elif tag == "provider":
                found["providers"].append(attrs.get("name") or attrs.get("authorities") or "")
            elif tag == "data":
                for key in ("scheme", "host", "path", "pathPrefix", "pathPattern"):
                    if attrs.get(key):
                        found[key + "s"].append(attrs[key])
            elif tag == "action" and attrs.get("name"):
                found["actions"].append(attrs["name"])
            elif tag == "category" and attrs.get("name"):
                found["categories"].append(attrs["name"])
            elif tag == "meta-data" and attrs.get("name"):
                found["metadata"].append(attrs["name"])
        off += size
    result = {k: sorted(set(v)) for k, v in found.items()}
    result.update(
        {
            "package": package,
            "version_name": version_name,
            "version_code": version_code,
            "min_sdk": min_sdk,
            "target_sdk": target_sdk,
            "application_attrs": app_attrs,
            "strings": strings,
        }
    )
    return result


def arsc_strings(data):
    seen = set()
    out = []

    def walk(off, end, depth=0):
        if depth > 5:
            return
        while off + 8 <= end:
            try:
                typ, header_size, size = struct.unpack_from("<HHI", data, off)
            except Exception:
                break
            if size < 8 or off + size > end:
                off += 4
                continue
            if typ == 0x0001:
                for s in parse_string_pool(data, off):
                    if s not in seen:
                        seen.add(s)
                        out.append(s)
            if header_size < size:
                walk(off + header_size, off + size, depth + 1)
            off += size

    walk(0, len(data))
    return out


def analyze(label, path):
    zf = zipfile.ZipFile(path)
    infos = {i.filename: i for i in zf.infolist() if not i.is_dir()}
    files = {name: {"size": info.file_size, "crc": format(info.CRC, "08x")} for name, info in infos.items()}
    dex = []
    dex_names = []
    for name in infos:
        if re.fullmatch(r"classes\d*\.dex", name):
            dex_names.append(name)
            dex.extend(dex_strings(zf.read(name)))
    res_strings = arsc_strings(zf.read("resources.arsc")) if "resources.arsc" in infos else []
    manifest = parse_manifest(zf.read("AndroidManifest.xml")) if "AndroidManifest.xml" in infos else {}
    all_strings = set(dex) | set(res_strings) | set(manifest.get("strings", []))
    urls = sorted(set(u.rstrip(".,);]'\"") for s in all_strings for u in URL_RE.findall(s)))
    domains = sorted(set(d.lower() for s in all_strings for d in DOMAIN_RE.findall(s)))
    apis = sorted(set(a for s in all_strings for a in API_RE.findall(s) if len(a) < 180))
    events = sorted(set(s for s in all_strings if 8 <= len(s) <= 80 and EVENT_RE.match(s)))
    package_names = []
    for s in dex:
        if s.startswith("L") and ";" in s and "/" in s:
            body = s[1 : s.find(";")]
            parts = body.split("/")[:4]
            if len(parts) >= 2:
                package_names.append(".".join(parts))
    versions = {}
    for name in infos:
        if name.startswith("META-INF/") and name.endswith(".version"):
            try:
                versions[name[9:-8]] = zf.read(name).decode("utf-8", "replace").strip()
            except Exception:
                pass
    return {
        "label": label,
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": sha256(path),
        "file_count": len(files),
        "files": files,
        "dex_files": sorted(dex_names),
        "dex_string_count": len(dex),
        "resource_string_count": len(res_strings),
        "manifest": manifest,
        "urls": urls,
        "domains": domains,
        "apis": apis,
        "events": events,
        "package_counts": collections.Counter(package_names).most_common(160),
        "versions": versions,
        "native_libs": sorted(n for n in files if n.startswith("lib/") and n.endswith(".so")),
        "assets": sorted(n for n in files if n.startswith("assets/")),
        "res_files": sorted(n for n in files if n.startswith("res/")),
    }


def set_diff(old, new):
    return {"added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new))}


def path_summary(paths):
    c = collections.Counter()
    for name in paths:
        if name.startswith("res/"):
            c["res"] += 1
        elif name.startswith("assets/"):
            c["assets"] += 1
        elif name.startswith("lib/"):
            c["native_lib"] += 1
        elif name.startswith("META-INF/"):
            c["meta_inf"] += 1
        elif name.endswith(".dex"):
            c["dex"] += 1
        else:
            c[name.split("/")[0]] += 1
    return dict(c.most_common())


def interesting(items, limit=200):
    words = [
        "watermark",
        "camera",
        "team",
        "vip",
        "pay",
        "payment",
        "subscribe",
        "ad",
        "ads",
        "member",
        "enterprise",
        "ai",
        "ocr",
        "location",
        "route",
        "attendance",
        "workgroup",
        "album",
        "sync",
        "wechat",
        "dingtalk",
        "amap",
        "baidu",
        "tencent",
        "alipay",
        "huawei",
        "oppo",
        "vivo",
        "xiaomi",
        "push",
        "umeng",
        "bugly",
        "sensors",
        "firebase",
        "bytedance",
        "ksad",
        "gdt",
        "union",
    ]
    out = []
    for item in items:
        low = item.lower()
        if any(word in low for word in words):
            out.append(item)
    return out[:limit]


def main():
    if len(sys.argv) != 5:
        raise SystemExit("usage: analyze_apk_diff.py OLD_LABEL OLD_APK NEW_LABEL NEW_APK")
    old_label, old_apk, new_label, new_apk = sys.argv[1], Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
    out_dir = Path("artifacts/apk-monitor")
    old = analyze(old_label, old_apk)
    new = analyze(new_label, new_apk)
    added = [n for n in new["files"] if n not in old["files"]]
    removed = [n for n in old["files"] if n not in new["files"]]
    changed = [n for n in new["files"] if n in old["files"] and new["files"][n] != old["files"][n]]
    manifest_keys = [
        "permissions",
        "activities",
        "services",
        "receivers",
        "providers",
        "schemes",
        "hosts",
        "paths",
        "pathPrefixs",
        "pathPatterns",
        "actions",
        "categories",
        "metadata",
    ]
    diff = {
        "versions": {"old": old_label, "new": new_label},
        "files": {
            "added_count": len(added),
            "removed_count": len(removed),
            "changed_count": len(changed),
            "added_summary": path_summary(added),
            "removed_summary": path_summary(removed),
            "changed_summary": path_summary(changed),
            "added": added[:1000],
            "removed": removed[:1000],
            "changed": changed[:1000],
        },
        "manifest": {k: set_diff(old["manifest"].get(k, []), new["manifest"].get(k, [])) for k in manifest_keys},
        "urls": set_diff(old["urls"], new["urls"]),
        "domains": set_diff(old["domains"], new["domains"]),
        "apis": set_diff(old["apis"], new["apis"]),
        "events": set_diff(old["events"], new["events"]),
        "native_libs": set_diff(old["native_libs"], new["native_libs"]),
        "assets": set_diff(old["assets"], new["assets"]),
        "res_files": set_diff(old["res_files"], new["res_files"]),
        "versions_meta": set_diff([f"{k}={v}" for k, v in old["versions"].items()], [f"{k}={v}" for k, v in new["versions"].items()]),
        "package_counts_old": old["package_counts"][:120],
        "package_counts_new": new["package_counts"][:120],
        "old_summary": {k: old[k] for k in ["label", "path", "size", "sha256", "file_count", "dex_files", "dex_string_count", "resource_string_count"]},
        "new_summary": {k: new[k] for k in ["label", "path", "size", "sha256", "file_count", "dex_files", "dex_string_count", "resource_string_count"]},
        "old_manifest_summary": {k: v for k, v in old["manifest"].items() if k != "strings"},
        "new_manifest_summary": {k: v for k, v in new["manifest"].items() if k != "strings"},
    }
    diff["notable"] = {
        "added_urls": interesting(diff["urls"]["added"]),
        "removed_urls": interesting(diff["urls"]["removed"]),
        "added_apis": interesting(diff["apis"]["added"]),
        "removed_apis": interesting(diff["apis"]["removed"]),
        "added_events": interesting(diff["events"]["added"]),
        "removed_events": interesting(diff["events"]["removed"]),
        "added_files": interesting(added),
        "removed_files": interesting(removed),
        "changed_files": interesting(changed),
    }
    out_path = out_dir / f"diff-{old_label}-to-{new_label}.json"
    out_path.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "out": str(out_path),
        "old": diff["old_summary"],
        "new": diff["new_summary"],
        "old_manifest_counts": {k: len(old["manifest"].get(k, [])) for k in manifest_keys},
        "new_manifest_counts": {k: len(new["manifest"].get(k, [])) for k in manifest_keys},
        "file_diff": {k: diff["files"][k] for k in ["added_count", "removed_count", "changed_count", "added_summary", "removed_summary", "changed_summary"]},
        "url_diff": {k: len(v) for k, v in diff["urls"].items()},
        "domain_diff": {k: len(v) for k, v in diff["domains"].items()},
        "api_diff": {k: len(v) for k, v in diff["apis"].items()},
        "event_diff": {k: len(v) for k, v in diff["events"].items()},
        "native_lib_diff": {k: len(v) for k, v in diff["native_libs"].items()},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
