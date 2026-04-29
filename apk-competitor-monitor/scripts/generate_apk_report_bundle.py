#!/usr/bin/env python3
import argparse
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path


def load_json(path):
    return json.loads(Path(path).read_text("utf-8"))


def mb(size):
    return f"{size / 1024 / 1024:.2f}MB"


def sample(items, limit=24):
    return list(items or [])[:limit]


def ensure_template(template_dir, report_dir):
    template_dir = Path(template_dir)
    for name in ["index.html", "app.js", "styles.css"]:
        src = template_dir / name
        if src.exists():
            shutil.copy2(src, report_dir / name)


def copy_zip_entry(apk, entry, out_dir, prefix):
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = entry.replace("/", "__")
    out = out_dir / f"{prefix}__{safe_name}"
    with zipfile.ZipFile(apk) as zf:
        out.write_bytes(zf.read(entry))
        size = zf.getinfo(entry).file_size
    return {"apkPath": entry, "url": str(out.relative_to(out_dir.parents[0])), "size": size}


def classify_top_modules(product):
    categories = {}
    for section, section_data in (product.get("classified") or {}).items():
        if not isinstance(section_data, dict):
            continue
        for category, items in section_data.items():
            categories.setdefault(category, 0)
            categories[category] += len(items or [])
    return sorted(categories.items(), key=lambda item: item[1], reverse=True)


def top_feature(layout, product):
    categories = classify_top_modules(product)
    top_category = categories[0][0] if categories else "其他模块"
    top_changed = sample((layout.get("layouts") or {}).get("changed", []), 1)
    top_layout = top_changed[0] if top_changed else {}
    classes = top_layout.get("classes", [])
    evidence = []
    evidence.extend(sample((layout.get("resources") or {}).get("valuesAdded", []), 8))
    evidence.extend(sample((layout.get("resources") or {}).get("filesChanged", []), 8))
    evidence.extend(sample((product.get("samples") or {}).get("events_added", []), 8))
    evidence.extend(sample((product.get("samples") or {}).get("apis_added", []), 6))
    pages = [top_layout.get("category")] if top_layout.get("category") else [top_category]
    ui = [top_layout.get("name")] if top_layout.get("name") else []
    summary = [
        f"静态证据主要集中在 {top_category}。",
        f"页面级 layout 变化 {layout.get('summary', {}).get('layoutsChanged', 0)} 处，资源值变化 {layout.get('summary', {}).get('resourceValuesChanged', 0)} 处。",
        "建议结合账号态、灰度开关和真机路径做人工验证。",
    ]
    impact = (
        f"{top_category} 相关 UI/资源存在静态变化，可能影响页面结构、视觉样式或交互提示。"
        if top_category != "其他模块"
        else "检测到一批静态 UI/资源变化，建议结合运行态验证判断实际产品影响。"
    )
    return {
        "id": f"{top_category}-static-change".replace("/", "-"),
        "title": f"{top_category} 静态变化",
        "type": "静态分析",
        "confidence": "中",
        "impact": impact,
        "pages": pages,
        "evidence": sample(evidence, 24),
        "summary": summary,
        "ui": ui,
        "classes": classes,
    }


def build_static_features(layout, product, limit=6):
    layout_categories = (layout.get("summary") or {}).get("categories") or {}
    classified = product.get("classified") or {}
    product_scores = dict(classify_top_modules(product))
    categories = set(layout_categories) | set(product_scores)

    ranked = []
    for category in categories:
        if category == "其他 UI":
            continue
        score = layout_categories.get(category, 0) * 4 + min(product_scores.get(category, 0), 80)
        if score > 0:
            ranked.append((category, score))
    ranked.sort(key=lambda item: (-item[1], item[0]))

    features = []
    layout_items = []
    for group in ["added", "changed", "removed"]:
        for item in (layout.get("layouts") or {}).get(group, []):
            layout_items.append((group, item))

    for category, _ in ranked[:limit]:
        category_layouts = [item for _, item in layout_items if item.get("category") == category]
        evidence_groups = {"added": [], "removed": [], "changed": []}
        for section_data in classified.values():
            if isinstance(section_data, dict):
                for item in section_data.get(category, [])[:8]:
                    evidence_groups["changed"].append(item)
        for group, item in layout_items:
            if item.get("category") == category and item.get("name"):
                target = "added" if group == "added" else "removed" if group == "removed" else "changed"
                evidence_groups[target].append(item.get("name"))
        evidence = evidence_groups["added"] + evidence_groups["changed"] + evidence_groups["removed"]
        classes = []
        ui = []
        for item in category_layouts[:8]:
            ui.append(item.get("name"))
            classes.extend(item.get("classes", [])[:4])
        features.append(
            {
                "id": f"{category}-static-change".replace("/", "-"),
                "title": f"{category} 静态变化",
                "type": "静态分析",
                "confidence": "中",
                "impact": f"{category} 相关资源、页面或代码信号存在变化，可能影响入口、编辑能力、提示文案或页面结构。",
                "pages": [category],
                "evidence": sample(evidence, 24),
                "evidenceGroups": {key: sample(value, 16) for key, value in evidence_groups.items()},
                "summary": [
                    f"{category} 命中 layout 分类 {layout_categories.get(category, 0)} 项，产品信号 {product_scores.get(category, 0)} 条。",
                    "该模块变化来自资源、layout、DEX/API/event 等静态信号，需要真机验证用户可见路径。",
                ],
                "ui": sample([name for name in ui if name], 12),
                "classes": sample(sorted(set(classes)), 16),
            }
        )
    return features


def build_obfuscation(layout):
    classes = []
    for group in ["added", "changed", "removed"]:
        for item in (layout.get("layouts") or {}).get(group, []):
            classes.extend(item.get("classes", []))
    unique = sorted(set(classes))
    suspicious = [cls for cls in unique if "defpackage" in cls or cls.split(".")[-1].isalnum() and len(cls.split(".")[-1]) <= 3]
    ratio = (len(suspicious) / len(unique)) if unique else 0
    impact = "高" if ratio >= 0.6 else "中" if ratio >= 0.25 else "低"
    aliases = []
    for item in sample((layout.get("layouts") or {}).get("changed", []) + (layout.get("layouts") or {}).get("added", []), 8):
        if item.get("classes"):
            aliases.append(
                {
                    "alias": f"{(item.get('category') or 'Layout').replace('/', '')}Candidate",
                    "evidence": sample([item.get("name")] + item.get("classes", []) + item.get("changeSummary", []), 4),
                }
            )
    return {
        "impact": impact,
        "summary": "结论优先依赖 layout/resource/UI key 等静态证据；短类名或 defpackage 类仅作为弱线索。",
        "candidateSemanticAliases": aliases,
    }


def load_optional_json(path):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return load_json(p)


def summarize_api_surface(api_surface):
    if not api_surface:
        return {"status": "missing"}
    summary = api_surface.get("summary", {})
    return {
        "status": "ok",
        "hitCount": api_surface.get("hit_count", 0),
        "byKind": summary.get("by_kind", {}),
        "topClasses": sample(summary.get("top_classes", []), 20),
        "retrofitEndpoints": sample(summary.get("retrofit_endpoints", []), 50),
    }


def summarize_api_diff(api_diff):
    if not api_diff:
        return {"status": "missing"}
    summary = api_diff.get("summary") or {}
    return {
        "status": "ok",
        "hitsAdded": summary.get("hits_added", 0),
        "hitsRemoved": summary.get("hits_removed", 0),
        "netHitDelta": summary.get("net_hit_delta", 0),
        "addedByKind": (summary.get("added") or {}).get("by_kind", {}),
        "addedByModule": (summary.get("added") or {}).get("by_module", {}),
        "removedByKind": (summary.get("removed") or {}).get("by_kind", {}),
        "removedByModule": (summary.get("removed") or {}).get("by_module", {}),
        "topAdded": sample(api_diff.get("added", []), 40),
        "topRemoved": sample(api_diff.get("removed", []), 40),
    }


def top_flow_feature(feature_flow):
    if not feature_flow:
        return None
    flows = feature_flow.get("flows") or []
    if not flows:
        return None
    flow = flows[0]
    screen = flow.get("screen", {})
    api_hits = flow.get("api_hits", [])
    evidence = []
    evidence.extend(screen.get("layouts", []))
    evidence.extend(screen.get("related_symbols", [])[:10])
    evidence.extend([f"{hit.get('kind')}: {hit.get('value')}" for hit in flow.get("change_hits", [])[:10]])
    evidence.extend([f"changed_layout: {name}" for name in flow.get("changed_layouts", [])[:10]])
    evidence.extend([f"{hit.get('kind')}: {hit.get('value')}" for hit in api_hits[:10]])
    module = flow.get("module") or "未归类功能"
    return {
        "id": f"{module}-feature-flow".replace("/", "-"),
        "title": f"{module} 调用链变化候选",
        "type": "源码调用链",
        "confidence": flow.get("confidence", "中"),
        "impact": f"{module} 相关页面与网络/API 信号存在静态关联，建议优先做真机路径验证。",
        "pages": [screen.get("class")] if screen.get("class") else [module],
        "evidence": sample(evidence, 24),
        "summary": [
            f"命中页面/入口：{screen.get('class', 'unknown')}",
            f"归因原因：{', '.join(flow.get('reasons', [])) or '静态关联'}",
            f"本次变化命中：API/网络 {len(flow.get('change_hits', []))} 项，layout {len(flow.get('changed_layouts', []))} 项。",
            "该结论来自反编译源码和 API 线索，仍需运行态验证。",
        ],
        "ui": screen.get("layouts", []),
        "classes": [screen.get("class")] if screen.get("class") else [],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diff", required=True)
    parser.add_argument("--product", required=True)
    parser.add_argument("--layout", required=True)
    parser.add_argument("--preview", required=True)
    parser.add_argument("--old-apk", required=True)
    parser.add_argument("--new-apk", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--old-version", required=True)
    parser.add_argument("--new-version", required=True)
    parser.add_argument("--app-name", default="Competitor App")
    parser.add_argument("--package", default="")
    parser.add_argument("--old-date", default="")
    parser.add_argument("--new-date", default="")
    parser.add_argument("--template-dir", required=True)
    parser.add_argument("--api-surface")
    parser.add_argument("--api-surface-diff")
    parser.add_argument("--feature-flow")
    parser.add_argument("--run-metadata")
    args = parser.parse_args()

    diff = load_json(args.diff)
    product = load_json(args.product)
    layout = load_json(args.layout)
    preview = load_json(args.preview)
    api_surface = load_optional_json(args.api_surface)
    api_diff = load_optional_json(args.api_surface_diff)
    feature_flow = load_optional_json(args.feature_flow)
    run_metadata = load_optional_json(args.run_metadata) or {}
    old_apk = Path(args.old_apk)
    new_apk = Path(args.new_apk)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    ensure_template(args.template_dir, report_dir)

    static_dir = report_dir / "static-ui"
    image_info = product.get("images", {})
    removed_assets = [
        copy_zip_entry(old_apk, item["path"], static_dir / "old", "old")
        for item in image_info.get("removed_sample", [])
        if item.get("path")
    ]
    changed_assets = [
        copy_zip_entry(new_apk, item["path"], static_dir / "new", "new")
        for item in image_info.get("changed_sample", [])
        if item.get("path")
    ]
    added_assets = [
        copy_zip_entry(new_apk, item["path"], static_dir / "added", "new")
        for item in image_info.get("added_sample", [])
        if item.get("path")
    ]

    flow_feature = top_flow_feature(feature_flow)
    static_features = build_static_features(layout, product)
    if not static_features:
        static_features = [top_feature(layout, product)]
    features = ([flow_feature] if flow_feature else []) + static_features
    layout_summary = layout.get("summary", {})
    product_counts = product.get("counts", {})
    api_summary = summarize_api_surface(api_surface)
    api_diff_summary = summarize_api_diff(api_diff)

    summary_text = (
        f"本次 v{args.old_version} 到 v{args.new_version} 发现静态 APK/UI 变化，"
        f"重点集中在 {features[0]['pages'][0]}，需要结合运行态验证确认真实用户可见影响。"
    )

    report = {
        "app": args.app_name,
        "package": args.package,
        "oldVersion": f"v{args.old_version}",
        "newVersion": f"v{args.new_version}",
        "oldDate": args.old_date,
        "newDate": args.new_date,
        "generatedAt": datetime.now().strftime("%Y-%m-%d"),
        "runMetadata": run_metadata,
        "summaryText": summary_text,
        "summary": {
            "features": len(features),
            "uiChanges": layout_summary.get("layoutsChanged", 0),
            "infraChanges": 1,
            "resourceStringsAdded": product_counts.get("resource_strings_added", 0),
            "eventsAdded": product_counts.get("events_added", 0),
            "apisAdded": product_counts.get("apis_added", 0),
            "imagesAdded": image_info.get("added_count", 0),
            "imagesRemoved": image_info.get("removed_count", 0),
            "apkOldSize": mb(diff["old_summary"]["size"]),
            "apkNewSize": mb(diff["new_summary"]["size"]),
        },
        "features": features,
        "infra": [
            {
                "title": "Manifest/SDK/底层差异",
                "type": "底层变化",
                "confidence": "中",
                "summary": "静态差异已纳入原始证据统计；是否属于功能发布、重构还是构建产物变化，需要结合后续版本继续观察。",
                "evidence": sample(
                    diff.get("notable", {}).get("changed_files", [])
                    + diff.get("notable", {}).get("added_apis", [])
                    + diff.get("notable", {}).get("added_events", []),
                    18,
                ),
            }
        ],
        "pmInsights": [
            summary_text,
            "静态结论优先回答变化位置、重要性、证据链和建议验证动作。",
            "运行态、灰度配置、WebView/H5 和账号态仍属于静态分析盲区。",
        ],
        "coverage": {
            "decompilation": {
                "apktool": "ok",
                "jadx_old": layout_summary.get("mappingOldStatus") or "unknown",
                "jadx_new": layout_summary.get("mappingNewStatus") or "unknown",
            },
            "apiSurface": {
                "status": api_summary.get("status"),
                "hitCount": api_summary.get("hitCount", 0),
                "byKind": api_summary.get("byKind", {}),
            },
            "apiSurfaceDiff": {
                "status": api_diff_summary.get("status"),
                "hitsAdded": api_diff_summary.get("hitsAdded", 0),
                "hitsRemoved": api_diff_summary.get("hitsRemoved", 0),
                "netHitDelta": api_diff_summary.get("netHitDelta", 0),
                "addedByModule": api_diff_summary.get("addedByModule", {}),
                "removedByModule": api_diff_summary.get("removedByModule", {}),
            },
            "featureFlow": (feature_flow or {}).get("summary", {"status": "missing"}),
            "layoutCoverage": layout_summary,
            "unexplainedSignals": {
                "resource_strings_removed": product_counts.get("resource_strings_removed", 0),
                "dex_strings_added": product_counts.get("dex_strings_added", 0),
                "dex_strings_removed": product_counts.get("dex_strings_removed", 0),
            },
            "blindSpots": ["灰度开关", "服务端配置", "WebView/H5", "加密字符串", "运行账号状态"],
        },
        "obfuscation": build_obfuscation(layout),
        "raw": {
            "counts": {
                "files_added": diff["files"]["added_count"],
                "files_removed": diff["files"]["removed_count"],
                "files_changed": diff["files"]["changed_count"],
                "resource_strings_added": product_counts.get("resource_strings_added", 0),
                "resource_strings_removed": product_counts.get("resource_strings_removed", 0),
                "dex_strings_added": product_counts.get("dex_strings_added", 0),
                "dex_strings_removed": product_counts.get("dex_strings_removed", 0),
                "apis_added": product_counts.get("apis_added", 0),
                "apis_removed": product_counts.get("apis_removed", 0),
                "events_added": product_counts.get("events_added", 0),
                "events_removed": product_counts.get("events_removed", 0),
                "urls_added": product_counts.get("urls_added", 0),
                "urls_removed": product_counts.get("urls_removed", 0),
                "layouts_changed": layout_summary.get("layoutsChanged", 0),
                "resource_files_added": layout_summary.get("resourceFilesAdded", 0),
                "resource_files_removed": layout_summary.get("resourceFilesRemoved", 0),
                "resource_files_changed": layout_summary.get("resourceFilesChanged", 0),
                "static_previews": len(preview.get("previews", [])),
                "api_surface_hits": api_summary.get("hitCount", 0),
                "api_surface_hits_added": api_diff_summary.get("hitsAdded", 0),
                "api_surface_hits_removed": api_diff_summary.get("hitsRemoved", 0),
                "feature_flows": (feature_flow or {}).get("summary", {}).get("flows", 0),
                "diff_aware_feature_flows": (feature_flow or {}).get("summary", {}).get("diff_aware_flows", 0),
            },
            "manifest": product.get("manifest", {}),
            "apiSurface": api_summary,
            "apiSurfaceDiff": api_diff_summary,
            "featureFlow": {
                "summary": (feature_flow or {}).get("summary", {}),
                "topFlows": sample((feature_flow or {}).get("flows", []), 30),
            },
            "images": image_info,
            "urlsAdded": sample(product.get("samples", {}).get("urls_added", []), 80),
            "urlsRemoved": sample(product.get("samples", {}).get("urls_removed", []), 80),
            "domainsAdded": sample(diff.get("domains", {}).get("added", []), 80),
            "domainsRemoved": sample(diff.get("domains", {}).get("removed", []), 80),
            "files": diff.get("files", {}),
        },
    }

    static_ui = {
        "note": "静态 UI 还原来自 APK 资源、DEX 字符串和 apktool layout diff，不代表真实运行截图。",
        "counts": {
            "addedImages": image_info.get("added_count", 0),
            "removedImages": image_info.get("removed_count", 0),
            "changedImages": image_info.get("changed_count", 0),
        },
        "uiPages": [
            {
                "id": features[0]["id"],
                "title": features[0]["title"],
                "type": features[0]["type"],
                "confidence": features[0]["confidence"],
                "pages": features[0]["pages"],
                "uiKeys": sample(features[0]["evidence"], 24),
                "apiEvidence": sample(product.get("samples", {}).get("apis_added", []), 18),
                "interpretation": features[0]["summary"],
                "assetsHint": features[0]["ui"],
            }
        ],
        "assets": {
            "addedImages": added_assets,
            "removedImages": removed_assets,
            "changedNewImages": changed_assets,
        },
    }

    (report_dir / "report-data.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    (report_dir / "static-ui-data.json").write_text(json.dumps(static_ui, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                "report": str(report_dir / "report-data.json"),
                "static_ui": str(report_dir / "static-ui-data.json"),
                "report_dir": str(report_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
