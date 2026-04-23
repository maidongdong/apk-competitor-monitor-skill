#!/usr/bin/env python3
import argparse
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path


def load_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text("utf-8"))


def safe_count(value):
    return value if isinstance(value, int) else 0


def text_blob(feature):
    parts = [
        feature.get("id", ""),
        feature.get("title", ""),
        feature.get("type", ""),
        feature.get("impact", ""),
        " ".join(feature.get("pages", [])),
        " ".join(feature.get("summary", [])),
        " ".join(feature.get("evidence", [])),
        " ".join(feature.get("ui", [])),
    ]
    return " ".join(parts).lower()


def product_module(feature):
    text = text_blob(feature)
    modules = [
        ("账号安全", ["微信", "wechat", "verify", "vericode", "bind", "手机号", "账号"]),
        ("团队协作", ["团队", "workgroup", "work_group", "photo_label", "台账", "标签"]),
        ("拍照/编辑", ["拍照", "camera", "puzzle", "拼图", "编辑", "insert"]),
        ("会员商业化", ["会员", "vip", "member", "权益", "expire"]),
        ("定位/风控", ["定位", "location", "poi", "gps", "lock", "位置"]),
        ("安全/隐私", ["安全", "safe", "safemode", "隐私", "权限"]),
        ("上传同步", ["上传", "同步", "upload", "sync", "cloud"]),
    ]
    for name, words in modules:
        if any(word in text for word in words):
            return name
    return "其他模块"


def priority(feature):
    text = text_blob(feature)
    score = 0
    if "高" in str(feature.get("confidence", "")):
        score += 2
    if any(word in text for word in ["新增功能", "会员", "vip", "微信", "验证", "安全", "定位", "团队", "台账", "入口", "权限"]):
        score += 3
    if any(word in text for word in ["ui", "改版", "弹窗", "状态", "提示", "筛选", "编辑", "埋点", "接口"]):
        score += 1
    evidence_count = len(set(feature.get("evidence", []) + feature.get("ui", []) + feature.get("pages", [])))
    if evidence_count >= 12:
        score += 2
    elif evidence_count >= 6:
        score += 1
    if score >= 6:
        return "高"
    if score >= 3:
        return "中"
    return "低"


def suggested_action(feature):
    module = product_module(feature)
    if module == "账号安全":
        return "用新账号、已绑定微信账号、手机号变更场景分别验证入口和异常弹窗。"
    if module == "团队协作":
        return "加入团队后验证入口、筛选、导出和多人协作状态。"
    if module == "会员商业化":
        return "用未开通、即将过期、已过期会员态验证展示和转化入口。"
    if module == "定位/风控":
        return "切换定位权限、虚拟定位和不同 POI 场景确认变化。"
    if module == "安全/隐私":
        return "在异常启动、权限受限、拍照失败场景下验证是否触发。"
    return "安装新版做主路径走查，并在下个版本继续观察。"


def is_obfuscated_class(name):
    value = str(name or "")
    tail = value.split(".")[-1] if value else ""
    return (
        "defpackage" in value
        or re.match(r"^[a-z]{1,3}\d*$", tail, re.I)
        or re.search(r"\$[a-z]\d*$", value, re.I)
    )


def obfuscation_summary(layout):
    items = []
    for group in ("added", "changed", "removed"):
        items.extend((layout.get("layouts", {}) if layout else {}).get(group, []))
    classes = []
    aliases = []
    for item in items:
        for class_name in item.get("classes", []):
            classes.append(class_name)
            if is_obfuscated_class(class_name):
                alias = item.get("name", "").split("/")[-1]
                aliases.append((class_name, alias, item.get("category", "")))
    unique = sorted(set(classes))
    obfuscated = sorted(set(c for c in classes if is_obfuscated_class(c)))
    ratio = len(obfuscated) / len(unique) if unique else 0
    impact = "高" if ratio >= 0.6 else "中" if ratio >= 0.25 else "低"
    return {
        "impact": impact,
        "unique": len(unique),
        "obfuscated": len(obfuscated),
        "aliases": aliases[:12],
    }


def write_readme(report_dir, report, layout, previews):
    summary = report.get("summary", {})
    layout_summary = layout.get("summary", {}) if layout else {}
    preview_items = previews.get("previews", []) if previews else []
    features = report.get("features", [])
    infra = report.get("infra", [])
    old_version = report.get("oldVersion", "")
    new_version = report.get("newVersion", "")
    obfuscation = obfuscation_summary(layout or {})
    lines = [
        f"# {report.get('app', '竞品 App')} 版本监控归档",
        "",
        f"- 版本范围：{old_version} -> {new_version}",
        f"- 包名：{report.get('package', '')}",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 主报告入口：`index.html`",
        "",
        "## PM 重点变化",
        "",
    ]
    top_features = sorted(features, key=lambda item: {"高": 0, "中": 1, "低": 2}[priority(item)])
    for feature in top_features[:6]:
        lines.append(f"- **[{priority(feature)}] {feature.get('title')}**（{product_module(feature)}）：{feature.get('impact', '')}")
    lines.extend(
        [
            "",
            "## 建议人工验证",
            "",
        ]
    )
    for feature in top_features[:8]:
        lines.append(f"- {feature.get('title')}：{suggested_action(feature)}")
    lines.extend(
        [
            "",
            "## 反编译覆盖率提示",
            "",
            f"- 已形成产品结论：{len(features)} 条",
            f"- 进入功能结论的静态证据：{len(set(item for feature in features for item in feature.get('evidence', []) + feature.get('ui', []) + feature.get('pages', [])))} 条",
            f"- 页面级 layout 变化：新增 {safe_count(layout_summary.get('layoutsAdded'))}，变更 {safe_count(layout_summary.get('layoutsChanged'))}，删除 {safe_count(layout_summary.get('layoutsRemoved'))}",
            f"- 静态 UI 预览：{len(preview_items)} 张",
            f"- 混淆影响：{obfuscation['impact']}（疑似混淆类 {obfuscation['obfuscated']}/{obfuscation['unique']}）",
            "- 口径说明：原始 DEX 字符串/API/埋点数量包含混淆符号、删除项、SDK 和底层实现，不等同于产品遗漏；未解释池优先看未归类页面级 UI 和疑似预埋线索。",
            "- 仍需动态验证：服务端灰度、WebView/H5、账号态/会员态/团队态、加密字符串和运行时页面。",
            "",
            "## 混淆类语义恢复样例",
            "",
        ]
    )
    if obfuscation["aliases"]:
        for class_name, alias, category in obfuscation["aliases"]:
            lines.append(f"- `{class_name}` -> `{alias}`（证据：{category} layout 关联）")
    else:
        lines.append("- 未发现明显混淆类关联到新增/变更 layout。")
    lines.append("")
    lines.extend([
        "## 摘要",
        "",
        f"- 功能变化：{safe_count(summary.get('features'))}",
        f"- UI 变化：{safe_count(summary.get('uiChanges'))}",
        f"- 新增资源字符串：{safe_count(summary.get('resourceStringsAdded'))}",
        f"- 新增 API/类线索：{safe_count(summary.get('apisAdded'))}",
        f"- 新增埋点/UI key：{safe_count(summary.get('eventsAdded'))}",
        f"- 新增图片资源：{safe_count(summary.get('imagesAdded'))}",
        f"- 删除图片资源：{safe_count(summary.get('imagesRemoved'))}",
        "",
        "## 页面级 UI Diff",
        "",
        f"- 新增 layout：{safe_count(layout_summary.get('layoutsAdded'))}",
        f"- 删除 layout：{safe_count(layout_summary.get('layoutsRemoved'))}",
        f"- 变更 layout：{safe_count(layout_summary.get('layoutsChanged'))}",
        f"- 新增资源值：{safe_count(layout_summary.get('resourceValuesAdded'))}",
        f"- 变更资源值：{safe_count(layout_summary.get('resourceValuesChanged'))}",
        f"- 新增资源文件：{safe_count(layout_summary.get('resourceFilesAdded'))}",
        f"- JADX layout 映射：{safe_count(layout_summary.get('mappingNewLayoutLinks'))}",
        "",
        "## 静态页面预览",
        "",
        f"- 预览图数量：{len(preview_items)}",
        "- 预览说明：这些图是基于 apktool layout XML、strings、colors、drawable 引用生成的静态近似还原，不是真机运行截图。",
        "",
    ])
    for item in preview_items[:20]:
        classes = ", ".join(item.get("classes", [])[:2]) or "未映射到明确类"
        lines.append(f"- `{item.get('layout')}`：{item.get('category')}，`{item.get('svg')}`，关联类：{classes}")
    lines.extend(["", "## 主要功能结论", ""])
    for feature in features:
        lines.append(f"### {feature.get('title')}")
        lines.append("")
        lines.append(f"- 类型：{feature.get('type')}")
        lines.append(f"- 置信度：{feature.get('confidence')}")
        lines.append(f"- 影响：{feature.get('impact')}")
        for item in feature.get("summary", [])[:5]:
            lines.append(f"- {item}")
        lines.append("")
    if infra:
        lines.extend(["## 底层变化", ""])
        for item in infra:
            lines.append(f"- {item.get('title')}：{item.get('summary')}（置信度 {item.get('confidence')}）")
    lines.extend(
        [
            "",
            "## 文件说明",
            "",
            "- `index.html` / `app.js` / `styles.css`：可离线打开的 Web 报告快照。",
            "- `report-data.json`：功能、底层、证据统计主数据。",
            "- `static-ui-data.json`：静态 UI key、素材和证据链。",
            "- `ui-layout-data.json`：页面级 layout/resource diff。",
            "- `ui-preview-data.json`：静态页面预览索引。",
            "- `static-ui-previews/*.svg`：静态页面近似还原图。",
            "- `archive-manifest.json`：归档清单和计数。",
        ]
    )
    out = report_dir / "ARCHIVE_README.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def collect_files(report_dir):
    names = [
        "index.html",
        "app.js",
        "styles.css",
        "report-data.json",
        "static-ui-data.json",
        "ui-layout-data.json",
        "ui-preview-data.json",
        "ARCHIVE_README.md",
        "archive-manifest.json",
    ]
    files = [report_dir / name for name in names if (report_dir / name).exists()]
    for folder in ["static-ui", "static-ui-previews"]:
        base = report_dir / folder
        if base.exists():
            files.extend(path for path in base.rglob("*") if path.is_file())
    return files


def write_manifest(report_dir, report, layout, previews):
    files = collect_files(report_dir)
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "app": report.get("app"),
        "package": report.get("package"),
        "old_version": report.get("oldVersion"),
        "new_version": report.get("newVersion"),
        "entrypoint": "index.html",
        "summary": report.get("summary", {}),
        "layout_summary": (layout or {}).get("summary", {}),
        "preview_count": len((previews or {}).get("previews", [])),
        "files": [
            {
                "path": str(path.relative_to(report_dir)),
                "size": path.stat().st_size,
            }
            for path in sorted(files)
        ],
    }
    out = report_dir / "archive-manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def write_zip(report_dir, out_zip):
    files = collect_files(report_dir)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(files):
            zf.write(path, path.relative_to(report_dir))
    return out_zip


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir")
    parser.add_argument("--zip-name", default=None)
    args = parser.parse_args()

    report_dir = Path(args.report_dir).resolve()
    report = load_json(report_dir / "report-data.json", {})
    layout = load_json(report_dir / "ui-layout-data.json", {})
    previews = load_json(report_dir / "ui-preview-data.json", {})
    readme = write_readme(report_dir, report, layout, previews)
    manifest = write_manifest(report_dir, report, layout, previews)
    zip_name = args.zip_name or f"{report_dir.name}.zip"
    out_zip = write_zip(report_dir, report_dir / zip_name)
    print(json.dumps({"readme": str(readme), "manifest": str(manifest), "zip": str(out_zip)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
