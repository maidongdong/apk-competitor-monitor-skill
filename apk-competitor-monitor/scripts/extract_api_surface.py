#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


HTTP_METHOD_RE = re.compile(r"@(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|HTTP)\s*\(\s*\"([^\"]*)\"")
RETROFIT_PARAM_RE = re.compile(r"@(Headers|Header|Query|QueryMap|Path|Body|Field|FieldMap|Part|PartMap|Url)\s*(?:\(\s*\"?([A-Za-z0-9_.:-]*)\"?\s*\))?")
URL_RE = re.compile(r"\"(https?://[^\"]+)\"")
BASE_URL_RE = re.compile(r"(?:baseUrl|BASE_URL|API_URL|SERVER_URL|ENDPOINT|HOST_NAME)\s*[=(]")
OKHTTP_RE = re.compile(r"(Request\.Builder|HttpUrl|\.newCall\s*\(|\.enqueue\s*\(|addInterceptor|addNetworkInterceptor|\.url\s*\(|\.addQueryParameter|\.addPathSegment)")
VOLLEY_RE = re.compile(r"(StringRequest|JsonObjectRequest|JsonArrayRequest|ImageRequest|RequestQueue|Volley\.newRequestQueue)")
WEBVIEW_RE = re.compile(r"(loadUrl\s*\(|loadData\s*\(|evaluateJavascript\s*\(|addJavascriptInterface|WebViewClient|WebChromeClient)")
AUTH_RE = re.compile(r"(api[_-]?key|auth[_-]?token|bearer|authorization|x-api-key|client[_-]?secret|access[_-]?token)", re.I)
CLASS_RE = re.compile(r"\b(?:public\s+)?(?:final\s+|abstract\s+)?class\s+([A-Za-z0-9_$]+)|\binterface\s+([A-Za-z0-9_$]+)")
METHOD_RE = re.compile(r"(?:public|private|protected|static|final|suspend|\s)+[\w<>\[\].?,\s]+?\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\([^;{}]*\)\s*(?:throws [^{]+)?\{?")
DEFAULT_EXCLUDE_PREFIXES = [
    "android.",
    "androidx.",
    "com.google.",
    "com.facebook.",
    "com.tencent.",
    "com.baidu.",
    "com.bytedance.",
    "com.kwad.",
    "com.qq.",
    "okhttp3.",
    "okio.",
    "retrofit2.",
    "org.chromium.",
    "org.json.",
    "kotlin.",
    "kotlinx.",
]


def line_number(text, offset):
    return text.count("\n", 0, offset) + 1


def infer_class_name(path, source_root, text):
    match = CLASS_RE.search(text)
    name = match.group(1) or match.group(2) if match else None
    rel = path.relative_to(source_root).with_suffix("")
    guessed = ".".join(rel.parts)
    if not name:
        return guessed
    return ".".join([*rel.parts[:-1], name])


def nearest_method(text, offset):
    window = text[max(0, offset - 3500):offset]
    matches = list(METHOD_RE.finditer(window))
    if not matches:
        return None
    return matches[-1].group(1)


def add_hit(hits, kind, path, source_root, text, match, value=None, extra=None):
    rel = str(path.relative_to(source_root))
    item = {
        "kind": kind,
        "file": rel,
        "line": line_number(text, match.start()),
        "class": infer_class_name(path, source_root, text),
        "method": nearest_method(text, match.start()),
        "value": value if value is not None else match.group(0)[:220],
    }
    if extra:
        item.update(extra)
    hits.append(item)


def scan_file(path, source_root):
    text = path.read_text("utf-8", errors="ignore")
    hits = []
    for match in HTTP_METHOD_RE.finditer(text):
        add_hit(hits, "retrofit_endpoint", path, source_root, text, match, match.group(2), {"http_method": match.group(1)})
    for match in RETROFIT_PARAM_RE.finditer(text):
        add_hit(hits, "retrofit_parameter", path, source_root, text, match, match.group(2) or match.group(1), {"annotation": match.group(1)})
    for match in URL_RE.finditer(text):
        add_hit(hits, "hardcoded_url", path, source_root, text, match, match.group(1))
    for regex, kind in [
        (BASE_URL_RE, "base_url_config"),
        (OKHTTP_RE, "okhttp_usage"),
        (VOLLEY_RE, "volley_usage"),
        (WEBVIEW_RE, "webview_usage"),
        (AUTH_RE, "auth_signal"),
    ]:
        for match in regex.finditer(text):
            add_hit(hits, kind, path, source_root, text, match)
    return hits


def should_scan(class_name, include_prefixes, exclude_prefixes):
    if include_prefixes and not any(class_name.startswith(prefix) for prefix in include_prefixes):
        return False
    return not any(class_name.startswith(prefix) for prefix in exclude_prefixes)


def summarize(hits):
    by_kind = {}
    by_class = {}
    by_endpoint = {}
    for hit in hits:
        by_kind[hit["kind"]] = by_kind.get(hit["kind"], 0) + 1
        by_class[hit["class"]] = by_class.get(hit["class"], 0) + 1
        if hit["kind"] == "retrofit_endpoint":
            key = f"{hit.get('http_method', '')} {hit.get('value', '')}".strip()
            by_endpoint[key] = by_endpoint.get(key, 0) + 1
    return {
        "by_kind": dict(sorted(by_kind.items(), key=lambda item: (-item[1], item[0]))),
        "top_classes": [
            {"class": key, "count": value}
            for key, value in sorted(by_class.items(), key=lambda item: (-item[1], item[0]))[:80]
        ],
        "retrofit_endpoints": [
            {"endpoint": key, "count": value}
            for key, value in sorted(by_endpoint.items(), key=lambda item: item[0])[:300]
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir")
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--include-prefix", action="append", default=[])
    parser.add_argument("--exclude-prefix", action="append", default=[])
    args = parser.parse_args()

    source_root = Path(args.source_dir).expanduser().resolve()
    hits = []
    excluded = 0
    exclude_prefixes = [*DEFAULT_EXCLUDE_PREFIXES, *args.exclude_prefix]
    for path in source_root.rglob("*"):
        if path.suffix not in {".java", ".kt"}:
            continue
        try:
            text = path.read_text("utf-8", errors="ignore")
            class_name = infer_class_name(path, source_root, text)
            if not should_scan(class_name, args.include_prefix, exclude_prefixes):
                excluded += 1
                continue
            hits.extend(scan_file(path, source_root))
        except Exception:
            continue
        if len(hits) >= args.limit:
            hits = hits[: args.limit]
            break

    report = {
        "source_dir": str(source_root),
        "hit_count": len(hits),
        "filters": {
            "include_prefixes": args.include_prefix,
            "exclude_prefixes": exclude_prefixes,
            "excluded_files": excluded,
        },
        "summary": summarize(hits),
        "hits": hits,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"out": str(out), "hit_count": len(hits), "summary": report["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
