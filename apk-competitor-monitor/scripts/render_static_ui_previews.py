#!/usr/bin/env python3
import argparse
import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
APP_NS = "{http://schemas.android.com/apk/res-auto}"
TOOLS_NS = "{http://schemas.android.com/tools}"
PHONE_W = 390
PHONE_H = 980
RESOURCE_VALUES = {}
STYLE_VALUES = {}
DRAWABLES = {}
ITEM_HINTS = {}
RAW_DIFF = {}
CURRENT_ITEM_HINTS = []
CURRENT_CHANGE_KIND = ""


PRIORITY = [
    "activity_safe_mode",
    "activity_safemode_photo_preview",
    "dialog_photo_label_create",
    "fragment_photo_label_filter",
    "layout_photo_label_group",
    "fragment_bind_wechat",
    "fragment_wechat_verify",
    "dialog_wechat_mismatch",
    "layout_safe_mode_exit_dialog",
    "layout_safe_mode_tips_dialog",
    "dialog_workgroup_widget_pre_add",
    "layout_work_group_take_photo_fab",
    "layout_insert_below_bottom_sheet",
    "layout_puzzle_text_bottom_sheet",
]


def local_name(name):
    if name.startswith(ANDROID_NS):
        return name[len(ANDROID_NS) :]
    if name.startswith(APP_NS):
        return "app:" + name[len(APP_NS) :]
    if name.startswith(TOOLS_NS):
        return "tools:" + name[len(TOOLS_NS) :]
    return name.rsplit("}", 1)[-1] if "}" in name else name


def parse_values(apktool_dir):
    values = {}
    for values_dir in [apktool_dir / "res" / "values", apktool_dir / "res" / "values-zh-rCN", apktool_dir / "res" / "values-zh"]:
        if not values_dir.exists():
            continue
        for path in values_dir.glob("*.xml"):
            try:
                root = ET.parse(path).getroot()
            except Exception:
                continue
            for child in root:
                name = child.attrib.get("name")
                if not name:
                    continue
                tag = child.tag.rsplit("}", 1)[-1]
                if tag in {"string", "color", "dimen", "integer", "bool"}:
                    values[f"{tag}/{name}"] = "".join(child.itertext()).strip()
    return values


def resolve_resource_map(values):
    resolved = dict(values)
    for _ in range(4):
        changed = False
        for key, value in list(resolved.items()):
            if isinstance(value, str) and value.startswith("@"):
                ref = value[1:]
                if ref in resolved and resolved[key] != resolved[ref]:
                    resolved[key] = resolved[ref]
                    changed = True
        if not changed:
            break
    return resolved


def parse_styles(apktool_dir, values):
    styles = {}
    path = apktool_dir / "res" / "values" / "styles.xml"
    if not path.exists():
        return styles
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return styles
    for style in root:
        if style.tag.rsplit("}", 1)[-1] != "style":
            continue
        name = style.attrib.get("name")
        if not name:
            continue
        attrs = {}
        for item in style:
            item_name = local_name(item.attrib.get("name", ""))
            text = "".join(item.itertext()).strip()
            if item_name and text:
                attrs[item_name.replace("android:", "")] = resolve(text, values)
        styles[f"@style/{name}"] = attrs
        styles[f"style/{name}"] = attrs
    return styles


def parse_drawable_shapes(apktool_dir, values):
    drawables = {}
    for drawable_dir in sorted((apktool_dir / "res").glob("drawable*")):
        if not drawable_dir.is_dir():
            continue
        for path in drawable_dir.glob("*.xml"):
            try:
                root = ET.parse(path).getroot()
            except Exception:
                continue
            if root.tag.rsplit("}", 1)[-1] not in {"shape", "selector", "layer-list"}:
                continue
            shape = {"fill": None, "stroke": None, "strokeWidth": None, "radius": 8}
            nodes = list(root.iter())
            for node in nodes:
                tag = node.tag.rsplit("}", 1)[-1]
                attrs = {local_name(k): resolve(v, values) for k, v in node.attrib.items()}
                if tag == "solid" and attrs.get("color"):
                    shape["fill"] = color_from_ref(attrs.get("color"), "#ffffff")
                elif tag == "stroke":
                    shape["stroke"] = color_from_ref(attrs.get("color"), "#d7e1ea")
                    shape["strokeWidth"] = parse_dp(attrs.get("width"), 1) or 1
                elif tag == "corners":
                    shape["radius"] = parse_dp(attrs.get("radius"), shape["radius"]) or shape["radius"]
            key = f"drawable/{path.stem}"
            drawables.setdefault(key, shape)
            drawables.setdefault(f"@{key}", shape)
    return drawables


def resolve(value, values):
    if not isinstance(value, str):
        return value
    if value.startswith("@"):
        key = value[1:]
        if key.startswith("+id/") or key.startswith("id/"):
            return value
        return values.get(key, value)
    return value


def parse_dp(value, default=None):
    if not value:
        return default
    if value in {"match_parent", "wrap_content"}:
        return default
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return default
    return max(0, float(match.group(0)))


def find_layout(apktool_dir, layout_name):
    stem = layout_name.rsplit("/", 1)[-1]
    candidates = []
    for layout_dir in sorted((apktool_dir / "res").glob("layout*")):
        path = layout_dir / f"{stem}.xml"
        if path.exists():
            candidates.append(path)
    if "/" in layout_name:
        direct = apktool_dir / "res" / f"{layout_name}.xml"
        if direct.exists():
            return direct
    return candidates[0] if candidates else None


def node_from_xml(path, apktool_dir, values, include_depth=0):
    root = ET.parse(path).getroot()

    def walk(element):
        tag = element.tag.rsplit("}", 1)[-1]
        attrs = {local_name(k): resolve(v, values) for k, v in element.attrib.items()}
        style_ref = attrs.get("style")
        if style_ref in STYLE_VALUES:
            styled = dict(STYLE_VALUES[style_ref])
            styled.update(attrs)
            attrs = styled
        if tag == "include" and include_depth < 4:
            layout_ref = attrs.get("layout")
            if isinstance(layout_ref, str) and layout_ref.startswith("@layout/"):
                include_path = find_layout(apktool_dir, layout_ref.split("/", 1)[1])
                if include_path:
                    included = node_from_xml(include_path, apktool_dir, values, include_depth + 1)
                    included["attrs"].update({k: v for k, v in attrs.items() if k != "layout"})
                    return included
        return {
            "tag": tag,
            "attrs": attrs,
            "children": [walk(child) for child in list(element)],
        }

    return walk(root)


def color_from_ref(value, fallback="#ffffff"):
    if not value:
        return fallback
    value = str(value).strip()
    if re.fullmatch(r"#[0-9A-Fa-f]{6,8}", value):
        return "#" + value[-6:]
    low = value.lower()
    if "blue" in low or "highlight" in low or "0093ff" in low or "0070f4" in low:
        return "#1677ff"
    if "black" in low:
        return "#111111"
    if "white" in low:
        return "#ffffff"
    if "red" in low:
        return "#f05b57"
    if "green" in low:
        return "#23b26d"
    if "yellow" in low:
        return "#f3c34b"
    if "bg_default" in low or "f5" in low:
        return "#f3f6fa"
    return fallback


def box_style(value, fallback_fill="#ffffff", fallback_stroke="#d7e1ea", fallback_rx=8):
    if isinstance(value, str) and value in DRAWABLES:
        item = DRAWABLES[value]
        return {
            "fill": item.get("fill") or fallback_fill,
            "stroke": item.get("stroke") or fallback_stroke,
            "rx": min(22, item.get("radius") or fallback_rx),
        }
    return {
        "fill": color_from_ref(value, fallback_fill),
        "stroke": fallback_stroke,
        "rx": fallback_rx,
    }


def text_for(node):
    attrs = node["attrs"]
    for key in ["text", "hint", "app:text", "app:title", "app:rightText", "contentDescription"]:
        value = attrs.get(key)
        if value and not str(value).startswith("@"):
            return str(value).replace("\\n", " ")
    node_id = attrs.get("id", "")
    if isinstance(node_id, str) and node_id:
        return node_id.split("/")[-1]
    return ""


def text_size_for(attrs, default=13):
    return min(26, max(10, parse_dp(attrs.get("textSize"), default) or default))


def is_button_like(node, text):
    attrs = node["attrs"]
    low_id = str(attrs.get("id", "")).lower()
    low_bg = str(attrs.get("background", "")).lower()
    low_tag = node["tag"].lower()
    command_words = ["confirm", "cancel", "complete", "bind", "retry", "resend", "create", "skip", "btn", "button"]
    return (
        "button" in low_tag
        or "xheybutton" in low_tag
        or any(word in low_id for word in command_words)
        or text in {"确定", "完成", "取消", "暂不绑定", "去微信授权绑定", "重新输入", "重新获取验证码"}
        or ("radius" in low_bg and any(word in low_bg for word in ["blue", "0093ff", "border"]))
    )


def is_hidden(node):
    return node["attrs"].get("visibility") == "gone"


def view_kind(tag):
    low = tag.lower()
    if "navigationbar" in low:
        return "nav"
    if "button" in low or "xheybutton" in low or "textview" in low and any(w in low for w in ["btn", "button"]):
        return "button"
    if "edittext" in low or "spinner" in low:
        return "input"
    if "image" in low:
        return "image"
    if "recyclerview" in low:
        return "list"
    if "camera" in low or "surface" in low or "texture" in low:
        return "camera"
    if "textview" in low:
        return "text"
    if low == "view":
        return "view"
    return "container"


def visible_children(node):
    return [child for child in node["children"] if not is_hidden(child)]


def escape(value):
    return html.escape(str(value), quote=True)


class Svg:
    def __init__(self):
        self.parts = []

    def rect(self, x, y, w, h, fill="#ffffff", stroke="#d7e1ea", rx=8, dash=False):
        dash_attr = ' stroke-dasharray="5 5"' if dash else ""
        self.parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(0, w):.1f}" height="{max(0, h):.1f}" rx="{rx}" fill="{fill}" stroke="{stroke}"{dash_attr}/>'
        )

    def text(self, x, y, value, size=13, fill="#24364b", weight=500, max_chars=28):
        clean = re.sub(r"\s+", " ", str(value)).strip()
        if len(clean) > max_chars:
            clean = clean[: max_chars - 1] + "…"
        if clean:
            self.parts.append(
                f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{fill}" font-family="PingFang SC, Microsoft YaHei, Arial">{escape(clean)}</text>'
            )

    def text_block(self, x, y, value, size=13, fill="#24364b", weight=500, max_chars=28, max_lines=2):
        clean = re.sub(r"\s+", " ", str(value)).strip()
        if not clean:
            return 0
        lines = [clean[i : i + max_chars] for i in range(0, len(clean), max_chars)]
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1][:-1] + "…"
        for idx, line in enumerate(lines):
            self.text(x, y + idx * (size + 6), line, size=size, fill=fill, weight=weight, max_chars=max_chars + 1)
        return len(lines)

    def line(self, x1, y1, x2, y2, stroke="#d7e1ea"):
        self.parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}"/>')


def normalize_layout_name(name):
    return str(name).rsplit("/", 1)[-1]


def load_raw_diff(path):
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text("utf-8"))


def layout_change_kind(name, raw_diff):
    if not raw_diff:
        return "added"
    layouts = raw_diff.get("layouts", {})
    if name in set(layouts.get("added", [])):
        return "added"
    if name in set(layouts.get("removed", [])):
        return "removed"
    if name in set(layouts.get("changed", [])):
        return "changed"
    base = normalize_layout_name(name)
    for key in layouts.get("changed", []):
        if normalize_layout_name(key) == base:
            return "changed"
    return "added"


def summarize_layout_change(name, raw_diff):
    if not raw_diff:
        return []
    layouts = raw_diff.get("layouts", {})
    detail = layouts.get("changed_details", {}).get(name)
    if not detail:
        base = normalize_layout_name(name)
        for key, value in layouts.get("changed_details", {}).items():
            if normalize_layout_name(key) == base:
                detail = value
                break
    if detail:
        return [
            f"新增控件 {len(detail.get('added_views', []))}",
            f"删除控件 {len(detail.get('removed_views', []))}",
            f"属性/文案变化 {len(detail.get('changed_views', []))}",
        ]
    if name in layouts.get("added", []):
        item = layouts.get("added_details", {}).get(name, {})
        return [f"新增页面结构", f"{item.get('view_count', 0)} 个静态控件"]
    return ["新增/改动 UI 结构"]


def state_hints_for_layout(name, detail):
    text = " ".join(
        str(v)
        for view in detail.get("views", [])
        for v in list(view.get("attrs", {}).values()) + [view.get("id"), view.get("tag")]
        if v
    ).lower()
    hints = ["默认态"]
    if "empty" in text or "no_" in text or "placeholder" in text:
        hints.append("空状态/占位态")
    if "loading" in text or "progress" in text:
        hints.append("加载态")
    if "error" in text or "failed" in text:
        hints.append("错误态")
    if "vip" in text or "member" in text:
        hints.append("会员/非会员态")
    if "bind" in text or "wechat" in text:
        hints.append("绑定/未绑定态")
    if "dialog" in name or "bottom_sheet" in name:
        hints.append("弹窗展开态")
    return hints[:4]


def detail_for_layout(name, raw_diff):
    if not raw_diff:
        return {}
    layouts = raw_diff.get("layouts", {})
    base = normalize_layout_name(name)
    for group in ["added_details", "removed_details"]:
        detail = layouts.get(group, {}).get(name)
        if detail:
            return detail
        for key, value in layouts.get(group, {}).items():
            if normalize_layout_name(key) == base:
                return value
    changed = layouts.get("changed_details", {}).get(name)
    if not changed:
        for key, value in layouts.get("changed_details", {}).items():
            if normalize_layout_name(key) == base:
                changed = value
                break
    if not changed:
        return {}
    views = []
    for view in changed.get("added_views", []):
        views.append(view)
    for item in changed.get("changed_views", []):
        if isinstance(item, dict):
            views.append(item.get("new") or item.get("old") or {})
    return {"views": views}


def infer_item_hints(raw_diff):
    hints = {}
    if not raw_diff:
        return hints
    mapping = raw_diff.get("mapping", {}).get("new", {})
    class_to_layout = mapping.get("class_to_layout", {})
    layout_to_classes = mapping.get("layout_to_classes", {})
    all_layouts = {
        normalize_layout_name(x)
        for x in raw_diff.get("layouts", {}).get("added", []) + raw_diff.get("layouts", {}).get("changed", [])
    }
    for layout, classes in layout_to_classes.items():
        related = set()
        for cls in classes:
            if "DataBinderMapperImpl" in cls:
                continue
            cls_layouts = class_to_layout.get(cls, [])
            if len(cls_layouts) > 25:
                continue
            for other in cls_layouts:
                other_base = normalize_layout_name(other)
                if other_base == layout:
                    continue
                if other_base.startswith(("item_", "layout_", "view_", "cell_", "header_", "footer_")):
                    related.add(other_base)
        if related:
            hints[layout] = sorted(related)
    # Fallback by shared keywords for common list pages.
    for layout in all_layouts:
        if "photo_label" in layout:
            hints.setdefault(layout, [])
            for candidate in all_layouts:
                if candidate.startswith("item_photo_label") or candidate.startswith("layout_photo_label"):
                    if candidate != layout and candidate not in hints[layout]:
                        hints[layout].append(candidate)
        if "work_group" in layout:
            hints.setdefault(layout, [])
            for candidate in all_layouts:
                if candidate.startswith("work_group_list_item") or candidate.startswith("layout_work_group"):
                    if candidate != layout and candidate not in hints[layout]:
                        hints[layout].append(candidate)
    return {k: v[:5] for k, v in hints.items() if v}


def render_leaf(svg, node, x, y, w):
    attrs = node["attrs"]
    tag = node["tag"]
    kind = view_kind(tag)
    text = text_for(node)
    bg_style = box_style(attrs.get("background"), "#ffffff")
    bg = bg_style["fill"]
    explicit_h = parse_dp(attrs.get("layout_height"))
    if kind == "nav":
        h = max(52, explicit_h or 52)
        svg.rect(x, y, w, h, fill="#ffffff", stroke="#dce4ec", rx=0)
        title = attrs.get("app:title") or attrs.get("title") or text or "页面标题"
        svg.text(x + 48, y + 32, title, size=16, weight=700)
        svg.text(x + 18, y + 32, "‹", size=24, fill="#314256", weight=700)
        right = attrs.get("app:rightText")
        if right:
            svg.text(x + w - 78, y + 32, right, size=13, fill="#1677ff", weight=650)
        return h
    if kind == "camera":
        h = min(300, max(170, explicit_h or w * 0.75))
        svg.rect(x, y, w, h, fill="#14171b", stroke="#14171b", rx=4)
        svg.text(x + 18, y + 32, "Camera preview", size=13, fill="#c6d0dc", weight=650)
        svg.line(x + 24, y + h - 38, x + w - 24, y + 24, "#394452")
        return h
    if kind == "list":
        h = min(240, max(118, explicit_h or 172))
        svg.rect(x, y, w, h, fill="#ffffff", stroke="#dce4ec", rx=8)
        if CURRENT_ITEM_HINTS:
            svg.text(x + 14, y + 22, "列表项推断", size=12, fill="#526377", weight=700)
            for i, item_name in enumerate(CURRENT_ITEM_HINTS[:3]):
                yy = y + 36 + i * 52
                svg.rect(x + 14, yy, w - 28, 42, fill="#f7fafc", stroke="#d7e1ea", rx=8)
                svg.rect(x + 24, yy + 9, 24, 24, fill="#e9f8ef" if "photo_label" in item_name else "#eef6ff", stroke="#d7e1ea", rx=6)
                svg.text(x + 58, yy + 24, item_name, size=12, fill="#33465c", weight=650, max_chars=28)
                svg.text(x + w - 48, yy + 24, "›", size=16, fill="#98a6b5", weight=700)
            return h
        for i in range(3):
            yy = y + 18 + i * 42
            svg.rect(x + 14, yy, 34, 26, fill="#eef4fa", stroke="#dce4ec", rx=6)
            svg.rect(x + 58, yy + 2, w - 84, 8, fill="#e9eef4", stroke="#e9eef4", rx=4)
            svg.rect(x + 58, yy + 18, w - 128, 7, fill="#f2f5f8", stroke="#f2f5f8", rx=4)
        return h
    if kind == "image":
        h = min(96, max(36, explicit_h or parse_dp(attrs.get("layout_width"), 54) or 54))
        icon_w = min(w, max(h, parse_dp(attrs.get("layout_width"), h) or h))
        src = str(attrs.get("src") or attrs.get("background") or "")
        fill = "#e9f8ef" if "wechat" in src.lower() else "#eef6ff"
        stroke = "#bfe4cc" if "wechat" in src.lower() else "#bdd7f3"
        svg.rect(x, y, icon_w, h, fill=fill, stroke=stroke, rx=min(16, h / 2))
        label = attrs.get("src") or attrs.get("background") or text or "image"
        svg.text(x + 10, y + h / 2 + 4, str(label).replace("@drawable/", ""), size=10, fill="#42698d", max_chars=18)
        return h
    if kind == "input":
        h = max(40, explicit_h or 42)
        svg.rect(x, y, w, h, fill="#f5f7fa", stroke="#d6e0ea", rx=8)
        svg.text(x + 12, y + h / 2 + 5, text or tag.rsplit(".", 1)[-1], size=13, fill="#7a8795")
        svg.text(x + w - 24, y + h / 2 + 5, "⌄" if "spinner" in tag.lower() else "", size=13, fill="#7a8795")
        return h
    if kind == "button" or (kind == "text" and is_button_like(node, text)):
        h = max(38, explicit_h or 42)
        tint = attrs.get("backgroundTint")
        fill = color_from_ref(tint, bg)
        if fill == "#ffffff" and (text in {"确定", "完成", "去微信授权绑定"} or "0093ff" in str(attrs.get("background", "")).lower()):
            fill = "#1677ff"
        if "#07c160" in str(tint).lower() or "wechat" in text.lower():
            fill = "#07c160"
        stroke = "#1677ff" if fill == "#ffffff" else fill
        fg = "#ffffff" if fill != "#ffffff" else "#1677ff"
        svg.rect(x, y, w, h, fill=fill, stroke=stroke, rx=bg_style["rx"])
        svg.text(x + 14, y + h / 2 + 5, text or tag.rsplit(".", 1)[-1], size=14, fill=fg, weight=700, max_chars=20)
        return h
    if kind == "text":
        h = max(24, explicit_h or 28)
        weight = 700 if attrs.get("textStyle") == "bold" else 500
        color = color_from_ref(attrs.get("textColor"), "#29384a")
        size = text_size_for(attrs, 15 if weight == 700 else 13)
        content = text or tag.rsplit(".", 1)[-1]
        max_chars = max(12, min(38, int(w / max(size * 0.58, 7))))
        line_count = 1
        if len(content) > max_chars:
            line_count = min(3, (len(content) + max_chars - 1) // max_chars)
            h = max(h, line_count * (size + 6) + 8)
            svg.text_block(x, y + size + 4, content, size=size, fill=color, weight=weight, max_chars=max_chars, max_lines=3)
        else:
            svg.text(x, y + min(size + 7, h - 4), content, size=size, fill=color, weight=weight, max_chars=max_chars)
        return h
    if kind == "view":
        h = max(8, explicit_h or 18)
        if h <= 2:
            svg.line(x, y + 0.5, x + w, y + 0.5, color_from_ref(attrs.get("background"), "#d7e1ea"))
        else:
            svg.rect(x, y, w, h, fill=bg, stroke=bg, rx=4)
        return h
    h = max(34, explicit_h or 42)
    svg.rect(x, y, w, h, fill=bg, stroke="#e0e7ef", rx=8, dash=True)
    if text:
        svg.text(x + 10, y + 23, text, size=12, fill="#627287")
    return h


def render_node(svg, node, x, y, w, depth=0):
    if is_hidden(node):
        return 0
    children = visible_children(node)
    tag = node["tag"]
    attrs = node["attrs"]
    low = tag.lower()
    margin_top = parse_dp(attrs.get("layout_marginTop"), 0) or 0
    y += min(margin_top, 24)
    if not children or view_kind(tag) in {"nav", "camera", "list"}:
        return min(render_leaf(svg, node, x, y, w), 360) + min(margin_top, 24)
    orientation = attrs.get("orientation")
    pad = min(parse_dp(attrs.get("paddingLeft"), 0) or parse_dp(attrs.get("padding"), 0) or 0, 18)
    bg = attrs.get("background")
    tag_low = tag.lower()
    start_y = y
    draws_card = bool(bg and depth <= 4 and "transparent" not in str(bg) and "scrollview" not in tag_low)
    card_style = box_style(bg, "#ffffff", "#e1e8ef", 10)
    if draws_card:
        svg.rect(x, y, w, 12, fill=card_style["fill"], stroke=card_style["stroke"], rx=card_style["rx"])
    y += 8 if draws_card else 0
    inner_x = x + pad
    inner_w = max(80, w - pad * 2)
    if orientation == "horizontal":
        shown = children[:4]
        gap = 10
        col_w = (inner_w - gap * (len(shown) - 1)) / max(1, len(shown))
        heights = []
        for idx, child in enumerate(shown):
            heights.append(render_node(svg, child, inner_x + idx * (col_w + gap), y, col_w, depth + 1))
        return max(36, max(heights or [0])) + 12 + min(margin_top, 24)
    total = 0
    for child in children[:22]:
        h = render_node(svg, child, inner_x, y + total, inner_w, depth + 1)
        total += h + 8
        if y + total > PHONE_H - 92:
            if depth == 0:
                svg.text(inner_x, PHONE_H - 64, "… 后续控件已折叠", size=12, fill="#7b8794")
            break
    if draws_card:
        svg.rect(x, start_y, w, min(total + 18, PHONE_H - start_y - 48), fill="none", stroke=card_style["stroke"], rx=card_style["rx"])
    return max(total + 8, 34) + min(margin_top, 24)


def title_from_layout(layout):
    name = layout.rsplit("/", 1)[-1]
    words = name.replace("_", " ")
    return words[:1].upper() + words[1:]


def render_layout(apktool_dir, values, layout_name, category, classes, out_svg, source_label="新版"):
    global CURRENT_ITEM_HINTS, CURRENT_CHANGE_KIND
    path = find_layout(apktool_dir, layout_name)
    if not path:
        return None
    root = node_from_xml(path, apktool_dir, values)
    base_name = normalize_layout_name(layout_name)
    CURRENT_ITEM_HINTS = ITEM_HINTS.get(base_name, [])
    CURRENT_CHANGE_KIND = layout_change_kind(layout_name, RAW_DIFF)
    svg = Svg()
    bg = color_from_ref(root["attrs"].get("background"), "#f6f8fb")
    svg.rect(0, 0, PHONE_W, PHONE_H, fill="#dfe7ef", stroke="#dfe7ef", rx=26)
    svg.rect(10, 10, PHONE_W - 20, PHONE_H - 20, fill=bg, stroke="#9faebd", rx=20)
    svg.rect(156, 21, 78, 5, fill="#172333", stroke="#172333", rx=3)
    is_dialog = "dialog" in layout_name or "bottom_sheet" in layout_name
    if is_dialog:
        svg.parts.append(
            f'<rect x="22" y="56" width="{PHONE_W - 44}" height="{PHONE_H - 98}" rx="16" fill="#000000" opacity="0.08" stroke="none"/>'
        )
        panel_y = 118 if "bottom_sheet" not in layout_name else 260
        svg.rect(28, panel_y, PHONE_W - 56, PHONE_H - panel_y - 34, fill="#ffffff", stroke="#d7e1ea", rx=18)
        svg.text(46, panel_y + 30, title_from_layout(layout_name), size=16, weight=750)
        render_node(svg, root, 46, panel_y + 48, PHONE_W - 92)
    else:
        badge = {"added": "新增", "changed": "变更", "removed": "删除"}.get(CURRENT_CHANGE_KIND, "静态")
        svg.rect(286, 34, 58, 24, fill="#e9f8ef" if CURRENT_CHANGE_KIND == "added" else "#fff7e6", stroke="#bfe4cc" if CURRENT_CHANGE_KIND == "added" else "#f2c879", rx=12)
        svg.text(300, 51, badge, size=12, fill="#13845b" if CURRENT_CHANGE_KIND == "added" else "#9a6400", weight=700)
        svg.text(26, 52, title_from_layout(layout_name), size=16, weight=750)
        render_node(svg, root, 24, 70, PHONE_W - 48)
    svg.text(24, PHONE_H - 22, f"{source_label}静态还原 · {category}", size=11, fill="#6d7b8a", max_chars=34)
    content = "\n".join(svg.parts)
    out_svg.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PHONE_W}" height="{PHONE_H}" viewBox="0 0 {PHONE_W} {PHONE_H}">{content}</svg>\n',
        encoding="utf-8",
    )
    return {
        "layout": layout_name,
        "category": category,
        "title": title_from_layout(layout_name),
        "classes": classes,
        "svg": str(out_svg.name),
        "sourceXml": str(path),
        "renderMode": "static-approximation",
        "changeKind": CURRENT_CHANGE_KIND,
        "itemLayouts": CURRENT_ITEM_HINTS,
        "states": state_hints_for_layout(layout_name, detail_for_layout(layout_name, RAW_DIFF)),
        "changeSummary": summarize_layout_change(layout_name, RAW_DIFF),
        "confidence": "中",
    }


def pick_layouts(layout_data, limit):
    added = layout_data.get("layouts", {}).get("added", [])
    changed = layout_data.get("layouts", {}).get("changed", [])
    by_name = {}
    for item in added + changed:
        base = item["name"].rsplit("/", 1)[-1]
        old = by_name.get(base)
        if not old or item["name"].startswith("layout/") or item.get("change") == "added":
            by_name[base] = item
    picked = []
    seen = set()
    for keyword in PRIORITY:
        for base, item in by_name.items():
            if keyword == base or keyword in item["name"]:
                picked.append(item)
                seen.add(base)
                break
    for base, item in by_name.items():
        if base not in seen:
            picked.append(item)
    return picked[:limit]


def main():
    global RESOURCE_VALUES, STYLE_VALUES, DRAWABLES, ITEM_HINTS, RAW_DIFF
    parser = argparse.ArgumentParser()
    parser.add_argument("--apktool-dir", required=True)
    parser.add_argument("--old-apktool-dir")
    parser.add_argument("--layout-data", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--ui-layout-diff")
    parser.add_argument("--limit", type=int, default=18)
    args = parser.parse_args()

    apktool_dir = Path(args.apktool_dir)
    old_apktool_dir = Path(args.old_apktool_dir) if args.old_apktool_dir else None
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    layout_data = json.loads(Path(args.layout_data).read_text("utf-8"))
    RAW_DIFF = load_raw_diff(args.ui_layout_diff)
    ITEM_HINTS = infer_item_hints(RAW_DIFF)
    values = resolve_resource_map(parse_values(apktool_dir))
    old_values = resolve_resource_map(parse_values(old_apktool_dir)) if old_apktool_dir and old_apktool_dir.exists() else {}
    RESOURCE_VALUES = values
    STYLE_VALUES = parse_styles(apktool_dir, values)
    DRAWABLES = parse_drawable_shapes(apktool_dir, values)
    previews = []
    for item in pick_layouts(layout_data, args.limit):
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", item["name"])
        out_svg = out_dir / f"{safe_name}.svg"
        preview = render_layout(
            apktool_dir,
            values,
            item["name"],
            item.get("category", "UI"),
            item.get("classes", []),
            out_svg,
            "新版",
        )
        if preview:
            preview["svg"] = f"{out_dir.name}/{out_svg.name}"
            if old_apktool_dir and old_apktool_dir.exists() and preview.get("changeKind") == "changed":
                old_svg = out_dir / f"{safe_name}_old.svg"
                old_preview = render_layout(
                    old_apktool_dir,
                    old_values,
                    item["name"],
                    item.get("category", "UI"),
                    item.get("classes", []),
                    old_svg,
                    "旧版",
                )
                if old_preview:
                    preview["oldSvg"] = f"{out_dir.name}/{old_svg.name}"
            previews.append(preview)
    output = {
        "note": "这些图片是基于 apktool layout XML、strings、colors、drawable 引用生成的静态近似还原，不是真机运行截图。",
        "source": args.layout_data,
        "apktoolDir": str(apktool_dir),
        "previews": previews,
    }
    Path(args.out_json).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": args.out_json, "count": len(previews)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
