#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


SCREEN_RE = re.compile(r"\b(class|interface)\s+([A-Za-z0-9_$]*(?:Activity|Fragment|Dialog|BottomSheet)[A-Za-z0-9_$]*)")
LIFECYCLE_RE = re.compile(r"\b(onCreate|onResume|onStart|onViewCreated|onCreateView|onActivityCreated)\s*\(")
CLICK_RE = re.compile(r"(setOnClickListener|onClick\s*\(|android:onClick|OnClickListener)")
NAV_RE = re.compile(r"(findNavController|NavController|navigate\s*\(|FragmentTransaction|beginTransaction|replace\s*\(|add\s*\()")
VIEWMODEL_RE = re.compile(r"\b([A-Za-z0-9_$]*(?:ViewModel|Presenter|Repository|Repo|UseCase|Manager|Service|Api)[A-Za-z0-9_$]*)\b")
LAYOUT_RE = re.compile(r"R\.layout\.([A-Za-z0-9_]+)|([A-Z][A-Za-z0-9]*(?:Activity|Fragment|Dialog|BottomSheet|Item|Layout)?Binding)")
DEFAULT_EXCLUDE_PREFIXES = [
    "android.",
    "androidx.",
    "com.google.",
    "com.facebook.",
    "com.tencent.",
    "com.baidu.",
    "com.bytedance.",
    "com.kwad.",
    "okhttp3.",
    "retrofit2.",
    "kotlin.",
    "kotlinx.",
]


def load_json(path):
    return json.loads(Path(path).read_text("utf-8"))


def binding_to_layout(name):
    base = re.sub(r"Binding$", "", name or "")
    words = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z]|$)", base)
    return "_".join(word.lower() for word in words if word)


def infer_class_name(path, source_root):
    return ".".join(path.relative_to(source_root).with_suffix("").parts)


def should_scan(class_name, include_prefixes, exclude_prefixes):
    if include_prefixes and not any(class_name.startswith(prefix) for prefix in include_prefixes):
        return False
    return not any(class_name.startswith(prefix) for prefix in exclude_prefixes)


def collect_screen_signals(source_root, include_prefixes, exclude_prefixes):
    screens = []
    class_index = {}
    for path in source_root.rglob("*"):
        if path.suffix not in {".java", ".kt"}:
            continue
        text = path.read_text("utf-8", errors="ignore")
        cls = infer_class_name(path, source_root)
        if not should_scan(cls, include_prefixes, exclude_prefixes):
            continue
        class_index[cls.split(".")[-1]] = cls
        if not SCREEN_RE.search(text) and not any(token in path.stem for token in ["Activity", "Fragment", "Dialog", "BottomSheet"]):
            continue
        layouts = set()
        for match in LAYOUT_RE.finditer(text):
            if match.group(1):
                layouts.add(match.group(1))
            elif match.group(2):
                layout = binding_to_layout(match.group(2))
                if layout:
                    layouts.add(layout)
        related = sorted(set(VIEWMODEL_RE.findall(text)))
        screens.append(
            {
                "class": cls,
                "file": str(path.relative_to(source_root)),
                "layouts": sorted(layouts),
                "has_lifecycle": bool(LIFECYCLE_RE.search(text)),
                "has_click_handler": bool(CLICK_RE.search(text)),
                "has_navigation": bool(NAV_RE.search(text)),
                "related_symbols": related[:80],
            }
        )
    return screens, class_index


def classify_module(values):
    text = " ".join(values).lower()
    categories = [
        ("会员/VIP", ["vip", "member", "pay", "subscribe", "payment", "benefit"]),
        ("团队/工作组", ["team", "group", "workgroup", "work_group"]),
        ("定位/位置", ["location", "gps", "poi", "amap", "gaode", "map"]),
        ("上传/同步", ["upload", "sync", "cloud", "queue"]),
        ("登录/账号", ["login", "auth", "token", "verify", "wechat", "bind"]),
        ("广告商业化", ["ad", "ads", "splash", "bidding", "union"]),
        ("WebView/H5", ["webview", "h5", "loadurl", "javascript"]),
        ("拍摄/图片编辑", ["camera", "photo", "puzzle", "edit", "watermark"]),
    ]
    for name, words in categories:
        if any(word in text for word in words):
            return name
    return "未归类功能"


def score_flow(screen, api_hits):
    score = 0
    reasons = []
    if screen.get("has_click_handler"):
        score += 2
        reasons.append("交互入口")
    if screen.get("has_navigation"):
        score += 1
        reasons.append("导航/弹窗")
    if screen.get("layouts"):
        score += 1
        reasons.append("layout 绑定")
    api_kinds = {hit.get("kind") for hit in api_hits}
    if "retrofit_endpoint" in api_kinds:
        score += 3
        reasons.append("Retrofit API")
    if "okhttp_usage" in api_kinds or "hardcoded_url" in api_kinds:
        score += 2
        reasons.append("网络请求")
    if "webview_usage" in api_kinds:
        score += 2
        reasons.append("WebView/H5")
    if "auth_signal" in api_kinds:
        score += 1
        reasons.append("鉴权信号")
    return score, reasons


def load_change_evidence(api_diff):
    if not api_diff:
        return {"classes": set(), "values": set(), "hits": []}
    hits = (api_diff.get("added") or []) + (api_diff.get("removed") or [])
    return {
        "classes": set(api_diff.get("changed_classes") or []),
        "values": set(str(value) for value in api_diff.get("changed_values") or []),
        "hits": hits,
    }


def flow_change_hits(screen, api_hits, change_evidence):
    classes = change_evidence["classes"]
    values = change_evidence["values"]
    hits = []
    related = {screen.get("class")}
    related.update(screen.get("related_symbols", []))
    related.update(hit.get("class") for hit in api_hits)
    for cls in related:
        if cls and cls in classes:
            hits.append({"kind": "changed_class", "value": cls})
    for hit in api_hits:
        value = str(hit.get("value"))
        if value in values:
            hits.append({"kind": hit.get("kind"), "value": value, "class": hit.get("class"), "method": hit.get("method")})
    return hits[:40]


def build_flows(screens, api_surface, api_diff=None, changed_layouts=None):
    hits = api_surface.get("hits") or []
    hits_by_class = {}
    for hit in hits:
        hits_by_class.setdefault(hit.get("class", ""), []).append(hit)
    change_evidence = load_change_evidence(api_diff)
    changed_layouts = set(changed_layouts or [])

    flows = []
    for screen in screens:
        related_classes = {screen["class"]}
        screen_tail = screen["class"].split(".")[-1]
        for symbol in screen.get("related_symbols", []):
            related_classes.add(symbol)
        matched_hits = []
        for cls, cls_hits in hits_by_class.items():
            tail = cls.split(".")[-1]
            if cls in related_classes or tail in related_classes or screen_tail in cls:
                matched_hits.extend(cls_hits[:30])
        score, reasons = score_flow(screen, matched_hits)
        change_hits = flow_change_hits(screen, matched_hits, change_evidence)
        layout_hits = sorted(set(screen.get("layouts", [])) & changed_layouts)
        if change_hits:
            score += 4
            reasons.append("命中本次 API/网络差异")
        if layout_hits:
            score += 3
            reasons.append("命中本次 layout 差异")
        values = [screen["class"], *screen.get("layouts", []), *screen.get("related_symbols", [])]
        values.extend(hit.get("value", "") for hit in matched_hits[:20])
        flows.append(
            {
                "screen": screen,
                "module": classify_module(values),
                "score": score,
                "confidence": "高" if score >= 6 else "中" if score >= 3 else "低",
                "reasons": reasons,
                "change_hits": change_hits,
                "changed_layouts": layout_hits,
                "api_hits": matched_hits[:40],
            }
        )
    return sorted(flows, key=lambda item: (not item["change_hits"] and not item["changed_layouts"], -item["score"], item["screen"]["class"]))[:200]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir")
    parser.add_argument("--api-surface", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--api-diff")
    parser.add_argument("--layout-data")
    parser.add_argument("--include-prefix", action="append", default=[])
    parser.add_argument("--exclude-prefix", action="append", default=[])
    args = parser.parse_args()

    source_root = Path(args.source_dir).expanduser().resolve()
    api_surface = load_json(args.api_surface)
    api_diff = load_json(args.api_diff) if args.api_diff else None
    layout_data = load_json(args.layout_data) if args.layout_data else None
    changed_layouts = []
    if layout_data:
        for group in ["added", "changed", "removed"]:
            for item in (layout_data.get("layouts") or {}).get(group, []):
                name = item.get("name") or ""
                if "/" in name:
                    name = name.split("/", 1)[1]
                if name:
                    changed_layouts.append(name)
    exclude_prefixes = [*DEFAULT_EXCLUDE_PREFIXES, *args.exclude_prefix]
    screens, _ = collect_screen_signals(source_root, args.include_prefix, exclude_prefixes)
    flows = build_flows(screens, api_surface, api_diff=api_diff, changed_layouts=changed_layouts)
    report = {
        "source_dir": str(source_root),
        "api_surface": str(Path(args.api_surface)),
        "api_diff": str(Path(args.api_diff)) if args.api_diff else None,
        "layout_data": str(Path(args.layout_data)) if args.layout_data else None,
        "filters": {
            "include_prefixes": args.include_prefix,
            "exclude_prefixes": exclude_prefixes,
        },
        "summary": {
            "screens": len(screens),
            "flows": len(flows),
            "diff_aware_flows": sum(1 for flow in flows if flow.get("change_hits") or flow.get("changed_layouts")),
            "high_confidence": sum(1 for flow in flows if flow["confidence"] == "高"),
            "medium_confidence": sum(1 for flow in flows if flow["confidence"] == "中"),
        },
        "flows": flows,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"out": str(out), "summary": report["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
