#!/usr/bin/env python3
import argparse
import json
import zipfile
from datetime import datetime
from pathlib import Path


def load_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text("utf-8"))


def safe_count(value):
    return value if isinstance(value, int) else 0


def write_readme(report_dir, report, layout, previews):
    summary = report.get("summary", {})
    layout_summary = layout.get("summary", {}) if layout else {}
    preview_items = previews.get("previews", []) if previews else []
    features = report.get("features", [])
    infra = report.get("infra", [])
    old_version = report.get("oldVersion", "")
    new_version = report.get("newVersion", "")
    lines = [
        f"# {report.get('app', '竞品 App')} 版本监控归档",
        "",
        f"- 版本范围：{old_version} -> {new_version}",
        f"- 包名：{report.get('package', '')}",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 主报告入口：`index.html`",
        "",
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
    ]
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
