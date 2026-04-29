const state = {
  data: null,
  staticUi: null,
  layoutUi: null,
  uiPreviews: null,
  filter: "全部",
  assetTab: "addedImages",
  layoutView: "added",
};

const labels = {
  resourceStringsAdded: "新增资源字符串",
  eventsAdded: "新增埋点/UI key",
  apisAdded: "新增 API/类线索",
  imagesAdded: "新增图片资源",
  imagesRemoved: "删除图片资源",
  features: "功能变化",
  uiChanges: "UI 变化",
  infraChanges: "底层变化",
  apiSurfaceHitsAdded: "API surface 新增",
  diffAwareFeatureFlows: "变化调用链",
};

const evidenceTypes = [
  ["UI", /(layout|fragment|activity|dialog|view|btn|tv|iv|cl_|rl_|ll_|fl_|bg_|ic_|drawable|mipmap)/i],
  ["接口", /(^\/|https?:\/\/|api|user\/|group\/|photo\/|label\/|vip|sync|upload)/i],
  ["文案", /[\u4e00-\u9fa5]{2,}/],
  ["类名", /(com\.|\/xhey\/|Activity|Fragment|Dialog|ViewModel|DataBinder|Binding)/],
  ["埋点", /(android_|event|track|click|enter|exit|success|fail|show|exposure)/i],
];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function unique(items) {
  return Array.from(new Set((items || []).filter(Boolean)));
}

function toNumber(value) {
  return Number.isFinite(Number(value)) ? Number(value) : 0;
}

function evidenceProfile(feature) {
  const groups = feature.evidenceGroups || {};
  const groupedItems = [
    ...(groups.added || []),
    ...(groups.changed || []),
    ...(groups.removed || []),
  ];
  const items = unique([...(feature.evidence || []), ...groupedItems, ...(feature.ui || []), ...(feature.pages || [])]);
  const counts = {};
  evidenceTypes.forEach(([label, pattern]) => {
    counts[label] = items.filter((item) => pattern.test(String(item))).length;
  });
  const matched = Object.values(counts).reduce((sum, value) => sum + value, 0);
  counts["其他"] = Math.max(items.length - matched, 0);
  return { items, counts };
}

function featurePriority(feature) {
  const text = searchableText([feature.title, feature.type, feature.impact, feature.summary, feature.pages, feature.evidence, feature.ui]);
  const highWords = ["新增功能", "会员", "vip", "支付", "微信", "验证", "安全", "定位", "团队", "台账", "入口", "权限"];
  const mediumWords = ["ui", "改版", "弹窗", "状态", "提示", "筛选", "编辑", "埋点", "接口"];
  const confidence = String(feature.confidence || "");
  let score = 0;
  if (confidence.includes("高")) score += 2;
  if (highWords.some((word) => text.includes(word))) score += 3;
  if (mediumWords.some((word) => text.includes(word))) score += 1;
  const evidenceCount = evidenceProfile(feature).items.length;
  if (evidenceCount >= 12) score += 2;
  if (evidenceCount >= 6) score += 1;
  if (score >= 6) return { level: "高", score, label: "重点关注" };
  if (score >= 3) return { level: "中", score, label: "建议跟进" };
  return { level: "低", score, label: "持续观察" };
}

function featureModule(feature) {
  const text = searchableText([feature.id, feature.title, feature.type, feature.impact, feature.pages, feature.evidence, feature.ui]);
  const modules = [
    ["账号安全", ["微信", "wechat", "verify", "vericode", "bind", "手机号", "账号"]],
    ["团队协作", ["团队", "workgroup", "work_group", "photo_label", "台账", "标签"]],
    ["拍照/编辑", ["拍照", "camera", "puzzle", "拼图", "编辑", "insert"]],
    ["会员商业化", ["会员", "vip", "member", "权益", "expire"]],
    ["定位/风控", ["定位", "location", "poi", "gps", "lock", "位置"]],
    ["安全/隐私", ["安全", "safe", "safemode", "隐私", "权限"]],
    ["上传同步", ["上传", "同步", "upload", "sync", "cloud"]],
  ];
  const match = modules.find(([, words]) => words.some((word) => text.includes(word)));
  return match ? match[0] : "其他模块";
}

function suggestedAction(feature) {
  const module = featureModule(feature);
  const type = String(feature.type || "");
  if (module === "账号安全") return "建议用新账号、已绑定微信账号、手机号变更场景分别验证入口和异常弹窗。";
  if (module === "团队协作") return "建议加入团队后验证入口、筛选、导出和多人协作状态，判断是否面向企业用户增强。";
  if (module === "会员商业化") return "建议用未开通、即将过期、已过期会员态验证展示和转化入口。";
  if (module === "定位/风控") return "建议切换定位权限、虚拟定位和不同 POI 场景，确认是否是风控或会员权益变化。";
  if (module === "安全/隐私") return "建议在异常启动、权限受限、拍照失败场景下验证是否触发安全模式。";
  if (type.includes("UI")) return "建议让产品和设计同学对照旧/新版静态图，重点看入口、状态和弹窗文案是否变化。";
  return "建议安装新版做一次主路径走查，并在下个版本继续观察该模块是否持续迭代。";
}

function candidateNameFromLayout(layoutName, category) {
  const base = normalizeKey(layoutName)
    .replace(/^(activity|fragment|dialog|layout|item|view|widget)_/, "")
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
  const suffix = /dialog|bottom_sheet/i.test(layoutName) ? "DialogCandidate" : /fragment/i.test(layoutName) ? "FragmentCandidate" : /activity/i.test(layoutName) ? "ActivityCandidate" : "UiCandidate";
  if (base) return `${base}${suffix}`;
  return `${String(category || "Unknown").replace(/[^\u4e00-\u9fa5A-Za-z0-9]/g, "")}${suffix}`;
}

function isObfuscatedClass(name) {
  const value = String(name || "");
  const tail = value.split(".").pop() || "";
  return (
    value.includes("defpackage") ||
    /^[a-z]{1,3}\d*$/i.test(tail) ||
    /\$[a-z]\d*$/i.test(value) ||
    /^sources\.[^.]+\.[^.]+\.[a-z]$/i.test(value)
  );
}

function obfuscationModel() {
  const layouts = [
    ...(state.layoutUi?.layouts?.added || []),
    ...(state.layoutUi?.layouts?.changed || []),
    ...(state.layoutUi?.layouts?.removed || []),
  ];
  const classLinks = [];
  layouts.forEach((layout) => {
    (layout.classes || []).forEach((className) => {
      classLinks.push({
        className,
        layout: layout.name,
        category: layout.category,
        views: layout.views || [],
        change: layout.change,
        alias: candidateNameFromLayout(layout.name, layout.category),
      });
    });
  });
  const uniqueClasses = unique(classLinks.map((item) => item.className));
  const obfuscatedClasses = unique(uniqueClasses.filter(isObfuscatedClass));
  const obfuscatedLinks = classLinks.filter((item) => isObfuscatedClass(item.className));
  const meaningfulLayouts = layouts.filter((layout) => !String(layout.category || "").includes("其他")).length;
  const resourceNamedLayouts = layouts.filter((layout) => /safe|wechat|verify|photo|label|vip|member|location|work|group|puzzle|upload|sync/i.test(layout.name)).length;
  const ratio = uniqueClasses.length ? obfuscatedClasses.length / uniqueClasses.length : 0;
  const impact = ratio >= 0.6 ? "高" : ratio >= 0.25 ? "中" : "低";
  const aliasMap = new Map();
  obfuscatedLinks.forEach((item) => {
    const key = item.className;
    const existing = aliasMap.get(key);
    if (!existing || String(existing.layout).includes("其他")) aliasMap.set(key, item);
  });
  return {
    uniqueClassCount: uniqueClasses.length,
    obfuscatedClassCount: obfuscatedClasses.length,
    ratio,
    impact,
    meaningfulLayouts,
    resourceNamedLayouts,
    aliases: Array.from(aliasMap.values()).slice(0, 20),
  };
}

function confidenceReason(feature) {
  const profile = evidenceProfile(feature);
  const active = Object.entries(profile.counts).filter(([, count]) => count > 0);
  if (!active.length) return "置信度说明：当前只有少量弱信号，需要人工验证。";
  const bits = active
    .filter(([label]) => label !== "其他")
    .map(([label, count]) => `${label} ${count}`)
    .slice(0, 5)
    .join("、");
  const prefix = String(feature.confidence || "").includes("高") ? "多类证据相互印证" : "已有静态证据但仍需运行时确认";
  return `置信度说明：${prefix}，命中 ${bits || `其他线索 ${profile.items.length}`}。`;
}

function addTags(container, items) {
  container.innerHTML = "";
  items.forEach((item) => container.appendChild(el("span", "tag", item)));
}

function renderHeader(data) {
  document.getElementById("reportTitle").textContent = data.app;
  document.getElementById("versionPill").innerHTML = `
    <strong>${data.oldVersion} → ${data.newVersion}</strong><br>
    ${data.oldDate} → ${data.newDate}<br>
    包名：${data.package}
  `;
  const top = topFeatures(data).slice(0, 3).map((item) => item.title).join("、");
  document.getElementById("summaryText").textContent =
    `本报告聚合 APK 静态差异，优先帮助 PM 识别本次值得关注的产品变化。新版包体从 ${data.summary.apkOldSize} 变为 ${data.summary.apkNewSize}，重点线索包括：${top || "暂无明确高优先级产品线索"}。`;
}

function topFeatures(data) {
  return [...(data.features || [])].sort((a, b) => featurePriority(b).score - featurePriority(a).score);
}

function renderMetrics(data) {
  const counts = data.raw?.counts || {};
  const metrics = [
    ["features", data.summary.features],
    ["uiChanges", data.summary.uiChanges],
    ["resourceStringsAdded", data.summary.resourceStringsAdded],
    ["eventsAdded", data.summary.eventsAdded],
    ["apisAdded", data.summary.apisAdded],
    ["apiSurfaceHitsAdded", counts.api_surface_hits_added || 0],
    ["diffAwareFeatureFlows", counts.diff_aware_feature_flows || 0],
    ["imagesAdded", data.summary.imagesAdded],
    ["imagesRemoved", data.summary.imagesRemoved],
  ];
  const grid = document.getElementById("metricGrid");
  grid.innerHTML = "";
  metrics.forEach(([key, value]) => {
    const card = el("div", "metric");
    card.appendChild(el("strong", "", String(value)));
    card.appendChild(el("span", "", labels[key]));
    grid.appendChild(card);
  });
}

function renderPmInsights(data) {
  const features = topFeatures(data);
  const hero = document.getElementById("insightHero");
  const grid = document.getElementById("insightGrid");
  const validation = document.getElementById("validationList");
  const high = features.filter((feature) => featurePriority(feature).level === "高");
  const modules = new Set(features.map(featureModule));
  hero.innerHTML = "";
  const heroItems = [
    ["重点变化", high.length || features.length, "优先查看高影响功能、商业化、账号安全和团队协作变化"],
    ["涉及模块", modules.size, Array.from(modules).slice(0, 5).join(" / ") || "暂无明确模块"],
    ["API 差异", data.coverage?.apiSurfaceDiff?.hitsAdded || 0, `新增 API/WebView/URL/auth 证据，净变化 ${data.coverage?.apiSurfaceDiff?.netHitDelta || 0}`],
    ["静态 UI 图", state.uiPreviews?.previews?.length || 0, state.uiPreviews?.previews?.length ? "已生成页面级静态还原，可辅助理解结构变化" : "未生成深度 UI 预览"],
  ];
  heroItems.forEach(([title, value, desc]) => {
    const card = el("article", "insight-hero-card");
    card.appendChild(el("span", "", title));
    card.appendChild(el("strong", "", String(value)));
    card.appendChild(el("p", "", desc));
    hero.appendChild(card);
  });

  grid.innerHTML = "";
  features.slice(0, 6).forEach((feature, index) => {
    const priority = featurePriority(feature);
    const card = el("article", "insight-card");
    const head = el("div", "insight-card-head");
    head.appendChild(el("span", `priority priority-${priority.level}`, `${priority.label} · ${priority.level}`));
    head.appendChild(el("span", "module-chip", featureModule(feature)));
    card.appendChild(head);
    card.appendChild(el("h3", "", `${index + 1}. ${feature.title}`));
    card.appendChild(el("p", "", feature.impact || (feature.summary || [])[0] || "需要结合证据继续判断产品影响。"));
    const bullets = el("ul", "insight-bullets");
    (feature.summary || []).slice(0, 3).forEach((line) => bullets.appendChild(el("li", "", line)));
    card.appendChild(bullets);
    card.appendChild(el("p", "insight-action", suggestedAction(feature)));
    grid.appendChild(card);
  });

  validation.innerHTML = "";
  features.slice(0, 8).forEach((feature, index) => {
    const item = el("article", "validation-item");
    item.appendChild(el("strong", "", `${index + 1}. ${feature.title}`));
    item.appendChild(el("p", "", suggestedAction(feature)));
    validation.appendChild(item);
  });
}

function renderEvidenceGroups(feature, container) {
  const groups = feature.evidenceGroups || {};
  const rows = [
    ["added", "新增证据", groups.added || []],
    ["changed", "变更/关联证据", groups.changed || []],
    ["removed", "移除证据", groups.removed || []],
  ].filter(([, , items]) => items.length);
  container.innerHTML = "";
  if (!rows.length) return;
  const wrap = el("div", "evidence-groups");
  rows.forEach(([kind, title, items]) => {
    const block = el("div", `evidence-group evidence-group-${kind}`);
    block.appendChild(el("strong", "", `${title} · ${items.length}`));
    const chips = el("div", "evidence-group-chips");
    items.slice(0, 12).forEach((item) => chips.appendChild(el("code", "", item)));
    block.appendChild(chips);
    wrap.appendChild(block);
  });
  container.appendChild(wrap);
}

function renderFilters(data) {
  const types = ["全部", ...Array.from(new Set(data.features.map((item) => item.type)))];
  const filters = document.getElementById("featureFilters");
  filters.innerHTML = "";
  types.forEach((type) => {
    const button = el("button", `filter ${type === state.filter ? "active" : ""}`, type);
    button.type = "button";
    button.addEventListener("click", () => {
      state.filter = type;
      renderFilters(state.data);
      renderFeatures(state.data);
    });
    filters.appendChild(button);
  });
}

function normalizeKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/^@?layout[/-]/, "")
    .replace(/^layout\//, "")
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function searchableText(parts) {
  return parts
    .flatMap((part) => (Array.isArray(part) ? part : [part]))
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function matchFeaturePreviews(feature) {
  const previews = state.uiPreviews?.previews || [];
  if (!previews.length) return [];
  const uiKeys = new Set((feature.ui || []).map(normalizeKey).filter(Boolean));
  const evidenceKeys = new Set((feature.evidence || []).map(normalizeKey).filter(Boolean));
  const featureText = searchableText([feature.id, feature.title, feature.type, feature.pages, feature.summary, feature.evidence, feature.ui]);
  const categoryText = searchableText([feature.id, feature.title, feature.type, feature.pages, feature.summary, feature.ui]);
  const categoryMap = [
    ["safe", "安全模式"],
    ["safemode", "安全模式"],
    ["安全", "安全模式"],
    ["photo_label", "团队照片标签/台账"],
    ["照片标签", "团队照片标签/台账"],
    ["台账", "团队照片标签/台账"],
    ["wechat", "微信绑定/验证"],
    ["微信", "微信绑定/验证"],
    ["verify", "微信绑定/验证"],
    ["vip", "会员/VIP"],
    ["member", "会员/VIP"],
    ["会员", "会员/VIP"],
    ["location", "定位/位置"],
    ["定位", "定位/位置"],
    ["lock", "定位/位置"],
    ["workgroup", "工作组/桌面组件"],
    ["work_group", "工作组/桌面组件"],
    ["widget", "工作组/桌面组件"],
    ["工作组", "工作组/桌面组件"],
    ["puzzle", "拼图/图片编辑"],
    ["拼图", "拼图/图片编辑"],
  ];
  const wantedCategories = new Set(
    categoryMap
      .filter(([keyword]) => categoryText.includes(keyword))
      .map(([, category]) => category),
  );
  const scored = [];
  previews.forEach((preview, index) => {
    const layoutKey = normalizeKey(preview.layout);
    const titleKey = normalizeKey(preview.title);
    const previewText = searchableText([preview.layout, preview.title, preview.category, preview.classes, preview.itemLayouts]);
    let score = 0;
    if (uiKeys.has(layoutKey) || uiKeys.has(titleKey)) score += 100;
    if (evidenceKeys.has(layoutKey) || evidenceKeys.has(titleKey)) score += 80;
    if ([...uiKeys].some((key) => key && (layoutKey.includes(key) || key.includes(layoutKey)))) score += 70;
    if ([...evidenceKeys].some((key) => key && layoutKey.includes(key))) score += 55;
    if (wantedCategories.has(preview.category)) score += 36;
    if (featureText.includes(layoutKey) || previewText.includes(normalizeKey(feature.id))) score += 28;
    if (score > 0) {
      scored.push({ preview, score, index });
    }
  });
  return scored
    .sort((a, b) => {
      const exactDelta = (b.score >= 70) - (a.score >= 70);
      if (exactDelta) return exactDelta;
      const oldDelta = Boolean(b.preview.oldSvg) - Boolean(a.preview.oldSvg);
      if (oldDelta) return oldDelta;
      if (b.score !== a.score) return b.score - a.score;
      return a.index - b.index;
    })
    .slice(0, 6)
    .map((item) => item.preview);
}

function appendPreviewImages(container, preview) {
  const pair = el("div", "preview-pair");
  const sources = preview.oldSvg
    ? [
        ["旧版", preview.oldSvg, false],
        ["新版", preview.svg, false],
      ]
    : [
        ["旧版", "", true],
        ["新版", preview.svg, false],
      ];
  sources.forEach(([label, src, isEmpty]) => {
    const pane = el("div", "preview-pane");
    pane.appendChild(el("span", "", label));
    if (isEmpty) {
      pane.appendChild(el("div", "feature-preview-empty", "旧版无对应静态页面"));
    } else {
      const img = document.createElement("img");
      img.src = src;
      img.alt = `${preview.layout} ${label}`;
      pane.appendChild(img);
    }
    pair.appendChild(pane);
  });
  container.appendChild(pair);
}

function renderFeaturePreviewToggle(feature, container) {
  const previews = matchFeaturePreviews(feature);
  container.innerHTML = "";
  if (!previews.length) return;
  const details = el("details", "feature-preview-details");
  const summary = el("summary", "feature-preview-toggle", `查看 ${previews.length} 个 UI 对比`);
  details.appendChild(summary);
  const panel = el("div", "feature-preview-panel");
  const grid = el("div", "feature-preview-grid");
  previews.forEach((preview) => {
    const card = el("article", "feature-preview-card");
    const frame = el("div", "feature-preview-frame");
    appendPreviewImages(frame, preview);
    const meta = el("div", "feature-preview-meta");
    const changeLabel = { added: "新增", changed: "变更", removed: "删除" }[preview.changeKind] || "静态";
    meta.appendChild(el("span", "type-badge", `${changeLabel} · ${preview.category}`));
    meta.appendChild(el("h4", "", preview.title));
    meta.appendChild(el("p", "", `${preview.layout} · 置信度 ${preview.confidence}`));
    const chips = el("div", "preview-classes");
    (preview.changeSummary || []).slice(0, 3).forEach((item) => chips.appendChild(el("code", "change-chip", item)));
    (preview.states || []).slice(0, 2).forEach((item) => chips.appendChild(el("code", "state-chip", item)));
    meta.appendChild(chips);
    card.appendChild(frame);
    card.appendChild(meta);
    grid.appendChild(card);
  });
  panel.appendChild(grid);
  details.appendChild(panel);
  container.appendChild(details);
}

function renderFeatures(data) {
  const template = document.getElementById("featureTemplate");
  const list = document.getElementById("featureList");
  list.innerHTML = "";
  data.features
    .filter((item) => state.filter === "全部" || item.type === state.filter)
    .forEach((feature) => {
      const node = template.content.cloneNode(true);
      node.querySelector(".type-badge").textContent = feature.type;
      node.querySelector("h3").textContent = feature.title;
      node.querySelector(".confidence").textContent = `置信度 ${feature.confidence}`;
      node.querySelector(".impact").textContent = feature.impact;
      const priority = featurePriority(feature);
      const meta = node.querySelector(".feature-meta-row");
      meta.innerHTML = "";
      [
        `${priority.label} · ${priority.level}`,
        featureModule(feature),
        feature.type,
      ].forEach((item) => meta.appendChild(el("span", "module-chip", item)));
      const summary = node.querySelector(".summary-list");
      feature.summary.forEach((line) => summary.appendChild(el("li", "", line)));
      addTags(node.querySelector(".page-tags"), feature.pages);
      const badges = node.querySelector(".evidence-badges");
      badges.innerHTML = "";
      Object.entries(evidenceProfile(feature).counts)
        .filter(([, count]) => count > 0)
        .forEach(([label, count]) => badges.appendChild(el("span", "evidence-badge", `${label} ${count}`)));
      renderEvidenceGroups(feature, badges);
      node.querySelector(".confidence-reason").textContent = confidenceReason(feature);
      node.querySelector(".suggested-action").textContent = suggestedAction(feature);
      let previewSlot = node.querySelector(".feature-preview-slot");
      if (!previewSlot) {
        previewSlot = el("div", "feature-preview-slot");
        node.querySelector(".card-main").appendChild(previewSlot);
      }
      renderFeaturePreviewToggle(feature, previewSlot);
      const content = node.querySelector(".evidence-content");
      content.innerHTML = feature.evidence.map((item) => `<code>${escapeHtml(item)}</code>`).join("");
      const evidenceSummary = node.querySelector(".feature-evidence-details summary");
      if (evidenceSummary) evidenceSummary.textContent = `技术证据 · ${feature.evidence.length} 条`;
      const evidenceToggle = node.querySelector(".evidence-toggle");
      if (evidenceToggle) {
        evidenceToggle.textContent = `技术证据 · ${feature.evidence.length} 条`;
        evidenceToggle.addEventListener("click", (event) => {
          content.classList.toggle("open");
          event.currentTarget.classList.toggle("active", content.classList.contains("open"));
        });
      }
      list.appendChild(node);
    });
}

function renderShots(data) {
  const staticUi = state.staticUi;
  document.getElementById("uiNote").textContent = staticUi.note;
  renderLayoutSummary();
  renderUiPreviews();
  renderLayoutTabs();
  renderLayoutDiff();
  const template = document.getElementById("reconstructTemplate");
  const list = document.getElementById("reconstructList");
  list.innerHTML = "";
  staticUi.uiPages.forEach((page) => {
    const node = template.content.cloneNode(true);
    node.querySelector(".type-badge").textContent = page.type;
    node.querySelector("h3").textContent = page.title;
    node.querySelector(".confidence").textContent = `置信度 ${page.confidence}`;
    node.querySelector(".phone-title").textContent = page.pages.join(" / ");
    const wires = node.querySelector(".wire-list");
    page.uiKeys.slice(0, 9).forEach((key) => wires.appendChild(el("div", "wire-item", key)));
    if (!page.uiKeys.length) wires.appendChild(el("div", "wire-item", "未发现明确 UI key"));
    const keyList = node.querySelector(".key-list");
    page.uiKeys.slice(0, 28).forEach((key) => keyList.appendChild(el("span", "key-chip", key)));
    const evidence = node.querySelector(".mini-evidence");
    page.apiEvidence.slice(0, 18).forEach((key) => evidence.appendChild(el("span", "key-chip", key)));
    list.appendChild(node);
  });
  renderAssetTabs();
  renderAssets();
}

function renderUiPreviews() {
  const data = state.uiPreviews;
  const note = document.getElementById("previewNote");
  const grid = document.getElementById("uiPreviewGrid");
  note.textContent = data?.note || "未生成静态页面预览。";
  grid.innerHTML = "";
  if (!data?.previews?.length) return;
  const template = document.getElementById("uiPreviewTemplate");
  data.previews.forEach((preview) => {
    const node = template.content.cloneNode(true);
    const frame = node.querySelector(".preview-frame");
    frame.innerHTML = "";
    if (preview.oldSvg) {
      const pair = el("div", "preview-pair");
      [
        ["旧版", preview.oldSvg],
        ["新版", preview.svg],
      ].forEach(([label, src]) => {
        const pane = el("div", "preview-pane");
        pane.appendChild(el("span", "", label));
        const img = document.createElement("img");
        img.src = src;
        img.alt = `${preview.layout} ${label}`;
        pane.appendChild(img);
        pair.appendChild(pane);
      });
      frame.appendChild(pair);
    } else {
      const img = document.createElement("img");
      img.src = preview.svg;
      img.alt = preview.layout;
      frame.appendChild(img);
    }
    const changeLabel = { added: "新增", changed: "变更", removed: "删除" }[preview.changeKind] || "静态";
    node.querySelector(".type-badge").textContent = `${changeLabel} · ${preview.category}`;
    node.querySelector("h3").textContent = preview.title;
    node.querySelector("p").textContent = `${preview.layout} · 置信度 ${preview.confidence}`;
    const classes = node.querySelector(".preview-classes");
    (preview.changeSummary || []).forEach((item) => classes.appendChild(el("code", "change-chip", item)));
    (preview.states || []).forEach((item) => classes.appendChild(el("code", "state-chip", item)));
    (preview.itemLayouts || []).slice(0, 4).forEach((item) => classes.appendChild(el("code", "item-chip", `列表项 ${item}`)));
    preview.classes.slice(0, 4).forEach((name) => classes.appendChild(el("code", "", name)));
    if (!preview.classes.length) classes.appendChild(el("code", "", "未映射到明确类"));
    grid.appendChild(node);
  });
}

function renderLayoutSummary() {
  const summary = state.layoutUi?.summary;
  const box = document.getElementById("layoutSummary");
  if (!summary) {
    box.innerHTML = "";
    return;
  }
  const items = [
    ["新增 layout", summary.layoutsAdded],
    ["删除 layout", summary.layoutsRemoved],
    ["变更 layout", summary.layoutsChanged],
    ["JADX 映射", summary.mappingNewLayoutLinks || 0],
    ["新增资源值", summary.resourceValuesAdded],
    ["新增资源文件", summary.resourceFilesAdded],
  ];
  box.innerHTML = "";
  items.forEach(([label, value]) => {
    const card = el("div", "layout-metric");
    card.appendChild(el("strong", "", String(value)));
    card.appendChild(el("span", "", label));
    box.appendChild(card);
  });
}

function renderLayoutTabs() {
  document.querySelectorAll(".layout-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.layoutView === state.layoutView);
    tab.onclick = () => {
      state.layoutView = tab.dataset.layoutView;
      renderLayoutTabs();
      renderLayoutDiff();
    };
  });
}

function viewLabel(view) {
  const attrs = view.attrs || {};
  const bits = [];
  if (view.id) bits.push(`#${view.id}`);
  if (attrs.text) bits.push(`text=${formatAttr(attrs.text)}`);
  if (attrs.hint) bits.push(`hint=${formatAttr(attrs.hint)}`);
  if (attrs.src) bits.push(`src=${formatAttr(attrs.src)}`);
  if (attrs.background) bits.push(`bg=${formatAttr(attrs.background)}`);
  return bits.join(" · ");
}

function formatAttr(value) {
  if (value && typeof value === "object") {
    return `${value.ref}: ${value.value}`;
  }
  return String(value);
}

function appendTreeRow(container, view, prefix = "") {
  const row = el("div", "tree-row");
  row.style.marginLeft = `${Math.min((view.depth || 0) * 12, 48)}px`;
  row.innerHTML = `${prefix}<strong>${escapeHtml(view.tag || view.signature)}</strong><br><code>${escapeHtml(viewLabel(view) || view.signature || "")}</code>`;
  container.appendChild(row);
}

function renderLayoutDiff() {
  const data = state.layoutUi;
  const list = document.getElementById("layoutDiffList");
  list.innerHTML = "";
  if (!data) return;
  if (state.layoutView === "resources") {
    const card = el("article", "layout-card");
    card.innerHTML = `<div class="layout-card-head"><div><span class="type-badge">资源变化</span><h3>strings / drawable / style</h3></div></div>`;
    const content = el("div", "resource-list");
    const groups = [
      ["新增资源值", data.resources.valuesAdded],
      ["变更资源值", data.resources.valuesChanged],
      ["新增资源文件", data.resources.filesAdded],
      ["删除资源文件", data.resources.filesRemoved],
      ["变更资源文件", data.resources.filesChanged],
    ];
    groups.forEach(([title, items]) => {
      const section = el("div", "tree-row");
      section.innerHTML = `<strong>${escapeHtml(title)} (${items.length})</strong><br><code>${escapeHtml(items.slice(0, 80).join("\\n"))}</code>`;
      content.appendChild(section);
    });
    card.appendChild(content);
    list.appendChild(card);
    return;
  }
  const template = document.getElementById("layoutDiffTemplate");
  const items = data.layouts[state.layoutView] || [];
  items.slice(0, 80).forEach((layout) => {
    const node = template.content.cloneNode(true);
    node.querySelector(".type-badge").textContent = layout.category;
    node.querySelector("h3").textContent = layout.name;
    const tree = node.querySelector(".layout-tree");
    if (layout.classes?.length) {
      const links = el("div", "layout-links");
      links.innerHTML = `<strong>关联类</strong>${layout.classes.map((name) => `<code>${escapeHtml(name)}</code>`).join("")}`;
      tree.appendChild(links);
    }
    if (state.layoutView === "changed") {
      node.querySelector(".layout-count").textContent = `+${layout.counts.addedViews} -${layout.counts.removedViews} Δ${layout.counts.changedViews}`;
      layout.addedViews.forEach((view) => appendTreeRow(tree, view, "+ "));
      layout.removedViews.forEach((view) => appendTreeRow(tree, view, "- "));
      layout.changedViews.forEach((item) => appendTreeRow(tree, item.new, "Δ "));
    } else {
      node.querySelector(".layout-count").textContent = `${layout.root || "layout"} · ${layout.viewCount} views`;
      layout.views.forEach((view) => appendTreeRow(tree, view));
    }
    list.appendChild(node);
  });
}

function renderAssetTabs() {
  document.querySelectorAll(".asset-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.asset === state.assetTab);
    tab.onclick = () => {
      state.assetTab = tab.dataset.asset;
      renderAssetTabs();
      renderAssets();
    };
  });
}

function renderAssets() {
  const grid = document.getElementById("assetGrid");
  const assets = state.staticUi.assets[state.assetTab] || [];
  grid.innerHTML = "";
  assets.forEach((asset) => {
    const card = el("article", "asset-card");
    const preview = el("div", "asset-preview");
    const img = document.createElement("img");
    img.src = asset.url;
    img.alt = asset.apkPath;
    preview.appendChild(img);
    const meta = el("div", "asset-meta");
    meta.innerHTML = `<strong>${escapeHtml(asset.apkPath)}</strong><br>${Math.round(asset.size / 1024)} KB`;
    card.appendChild(preview);
    card.appendChild(meta);
    grid.appendChild(card);
  });
}

function renderInfra(data) {
  const list = document.getElementById("infraList");
  list.innerHTML = "";
  data.infra.forEach((item) => {
    const card = el("article", "infra-card");
    const head = el("div", "infra-head");
    const title = el("div");
    title.appendChild(el("span", "type-badge", item.type));
    title.appendChild(el("h3", "", item.title));
    head.appendChild(title);
    head.appendChild(el("span", "confidence", `置信度 ${item.confidence}`));
    card.appendChild(head);
    card.appendChild(el("p", "impact", item.summary));
    const evidence = el("div", "evidence-content open");
    evidence.innerHTML = item.evidence.map((entry) => `<code>${escapeHtml(entry)}</code>`).join("");
    card.appendChild(evidence);
    list.appendChild(card);
  });
}

function renderEvidence(data) {
  const rows = document.getElementById("countRows");
  rows.innerHTML = "";
  Object.entries(data.raw.counts).forEach(([key, value]) => {
    const tr = document.createElement("tr");
    tr.appendChild(el("td", "", key));
    tr.appendChild(el("td", "", String(value)));
    rows.appendChild(tr);
  });
  document.getElementById("rawBox").textContent = JSON.stringify(
    {
      manifest: data.raw.manifest,
      apiSurfaceDiff: data.raw.apiSurfaceDiff,
      featureFlow: data.raw.featureFlow?.summary,
      images: data.raw.images,
      urlsAdded: data.raw.urlsAdded,
      urlsRemoved: data.raw.urlsRemoved,
    },
    null,
    2,
  );
}

function layoutCategoryCounts() {
  return state.layoutUi?.summary?.categories || {};
}

function collectUnexplainedLayouts() {
  const layouts = [
    ...(state.layoutUi?.layouts?.added || []),
    ...(state.layoutUi?.layouts?.changed || []),
  ];
  return layouts
    .filter((layout) => String(layout.category || "").includes("其他"))
    .slice(0, 16)
    .map((layout) => `${layout.change === "changed" ? "变更" : "新增"} ${layout.name} · ${layout.root || "layout"} · ${layout.viewCount || layout.counts?.changedViews || 0} views`);
}

function unexplainedLayoutCount() {
  const categoryCounts = layoutCategoryCounts();
  return Object.entries(categoryCounts)
    .filter(([name]) => String(name).includes("其他"))
    .reduce((sum, [, value]) => sum + toNumber(value), 0);
}

function coverageModel(data) {
  const counts = data.raw?.counts || {};
  const summary = data.summary || {};
  const signalTotal = Object.values(counts).reduce((sum, value) => sum + toNumber(value), 0);
  const featureEvidence = new Set();
  (data.features || []).forEach((feature) => evidenceProfile(feature).items.forEach((item) => featureEvidence.add(item)));
  const layoutSummary = state.layoutUi?.summary || {};
  const layoutTotal = toNumber(layoutSummary.layoutsAdded) + toNumber(layoutSummary.layoutsChanged) + toNumber(layoutSummary.layoutsRemoved);
  const categoryCounts = layoutCategoryCounts();
  const explainedLayouts = Object.entries(categoryCounts)
    .filter(([name]) => !String(name).includes("其他"))
    .reduce((sum, [, value]) => sum + toNumber(value), 0);
  const previewCount = state.uiPreviews?.previews?.length || 0;
  const apiDiff = data.coverage?.apiSurfaceDiff || {};
  const featureFlow = data.coverage?.featureFlow || {};
  const staticDepth = [
    state.layoutUi ? "apktool layout/resource diff 已生成" : "缺少 apktool layout/resource diff",
    previewCount ? `静态 UI 预览 ${previewCount} 张` : "缺少静态 UI 预览",
    state.layoutUi?.summary?.mappingNewStatus === "ok" ? "JADX 页面映射可用" : "JADX 页面映射缺失或失败",
  ];
  return {
    signalTotal,
    featureEvidenceCount: featureEvidence.size,
    layoutTotal,
    explainedLayouts,
    unexplainedLayouts: unexplainedLayoutCount(),
    previewCount,
    productConclusionCount: data.features?.length || 0,
    apiHitsAdded: toNumber(apiDiff.hitsAdded),
    apiHitsRemoved: toNumber(apiDiff.hitsRemoved),
    apiAddedByModule: apiDiff.addedByModule || {},
    diffAwareFlows: toNumber(featureFlow.diff_aware_flows),
    staticDepth,
    summary,
  };
}

function renderCoverage(data) {
  const model = coverageModel(data);
  const obfuscation = obfuscationModel();
  const grid = document.getElementById("coverageGrid");
  grid.innerHTML = "";
  [
    ["产品结论", model.productConclusionCount, "已归纳为 PM 可读功能变化的结论数"],
    ["API 差异", `${model.apiHitsAdded}+ / ${model.apiHitsRemoved}-`, "old/new API surface 的 URL、WebView、OkHttp、auth 差异"],
    ["变化调用链", model.diffAwareFlows, "命中本次 API 或 layout 差异的 Activity/Fragment 候选链路"],
    ["证据链线索", model.featureEvidenceCount, "进入功能卡片的 UI/接口/类名/文案/埋点证据"],
    ["页面级变化", `${model.explainedLayouts}/${model.layoutTotal}`, "已归类产品模块的新增/变更/删除 layout"],
    ["疑似产品未归类", model.unexplainedLayouts, "页面级变化中仍属于“其他 UI”的 layout 数量"],
    ["混淆影响", obfuscation.impact, `${obfuscation.obfuscatedClassCount}/${obfuscation.uniqueClassCount} 个关联类疑似混淆`],
    ["原始信号总量", model.signalTotal, "包含 DEX 字符串、删除项、混淆符号和 SDK 噪声，不等同于产品遗漏"],
    ["静态 UI 图", model.previewCount, "基于 apktool layout XML 生成的第二层静态还原图"],
    ["图片素材", `${model.summary.imagesAdded || 0}+ / ${model.summary.imagesRemoved || 0}-`, "APK 中新增和删除的真实图片资源"],
  ].forEach(([label, value, desc]) => {
    const card = el("article", "coverage-metric");
    card.appendChild(el("strong", "", String(value)));
    card.appendChild(el("span", "", label));
    card.appendChild(el("p", "", desc));
    grid.appendChild(card);
  });

  const unexplained = document.getElementById("unexplainedList");
  unexplained.innerHTML = "";
  const apiModuleItems = Object.entries(model.apiAddedByModule)
    .slice(0, 8)
    .map(([name, value]) => `API surface 新增模块：${name} ${value} 条`);
  const layoutItems = collectUnexplainedLayouts();
  const rawItems = [
    `口径说明：这里优先展示未归入产品模块的页面级 UI；原始字符串总量不直接代表产品遗漏。`,
    `新增资源字符串 ${model.summary.resourceStringsAdded || 0} 条：已用于功能结论和 UI 证据，剩余需结合语义抽样。`,
    `新增 API/类线索 ${model.summary.apisAdded || 0} 条：包含产品接口、SDK、混淆类和底层实现，需要二次分类。`,
    `新增埋点/UI key ${model.summary.eventsAdded || 0} 条：适合继续挖疑似预埋/灰度功能。`,
  ];
  [...apiModuleItems, ...layoutItems, ...rawItems].slice(0, 24).forEach((item) => unexplained.appendChild(el("code", "", item)));

  const obfuscationSummary = document.getElementById("obfuscationSummary");
  obfuscationSummary.innerHTML = "";
  [
    ["影响等级", obfuscation.impact],
    ["疑似混淆类", `${obfuscation.obfuscatedClassCount}/${obfuscation.uniqueClassCount}`],
    ["业务命名 layout", obfuscation.resourceNamedLayouts],
  ].forEach(([label, value]) => {
    const chip = el("span", "module-chip", `${label}：${value}`);
    obfuscationSummary.appendChild(chip);
  });
  const obfuscationList = document.getElementById("obfuscationList");
  obfuscationList.innerHTML = "";
  if (!obfuscation.aliases.length) {
    obfuscationList.appendChild(el("code", "", "未发现明显混淆类关联到新增/变更 layout。"));
  } else {
    obfuscation.aliases.forEach((item) => {
      obfuscationList.appendChild(
        el(
          "code",
          "",
          `${item.className}\n-> ${item.alias}\n证据：${item.layout} · ${item.category}`,
        ),
      );
    });
  }

  const blindspots = document.getElementById("blindspotList");
  blindspots.innerHTML = "";
  [
    "服务端开关/灰度配置：APK 里可能只有 key，是否展示给用户需要运行时验证。",
    "WebView/H5/动态下发页面：页面内容可能不在 native layout 中。",
    "加密或压缩字符串：普通 DEX 字符串扫描可能无法还原。",
    "Compose/Flutter/RN UI：不一定存在 XML layout，静态还原覆盖有限。",
    "账号态/会员态/团队态/异常态：需要真实账号和操作路径才能确认。",
    ...model.staticDepth,
  ].forEach((item) => blindspots.appendChild(el("code", "", item)));

  const metadataList = document.getElementById("runMetadataList");
  if (metadataList) {
    metadataList.innerHTML = "";
    const metadata = data.runMetadata || {};
    const template = metadata.reportTemplate || {};
    const repro = metadata.reproducibility || {};
    [
      `工具版本：${metadata.toolVersion || "unknown"}`,
      `配置指纹：${metadata.projectConfigFingerprint || "missing"}`,
      `配置文件 SHA256：${metadata.projectConfigSha256 || "missing"}`,
      `模板指纹：${template.combinedSha256 || "missing"}`,
      `直接覆盖参数：${(metadata.directOverrideKeys || []).join(", ") || "none"}`,
      `锁定报告模板：${repro.lock_report_template ? "yes" : "no"}`,
      `记录运行元数据：${repro.record_run_metadata ? "yes" : "no"}`,
    ].forEach((item) => metadataList.appendChild(el("code", "", item)));
  }
}

function bindTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((panel) => panel.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(tab.dataset.target).classList.add("active");
    });
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function main() {
  bindTabs();
  const [response, staticResponse, layoutResponse, previewResponse] = await Promise.all([
    fetch("./report-data.json"),
    fetch("./static-ui-data.json"),
    fetch("./ui-layout-data.json").catch(() => null),
    fetch("./ui-preview-data.json").catch(() => null),
  ]);
  const data = await response.json();
  state.staticUi = await staticResponse.json();
  state.layoutUi = layoutResponse && layoutResponse.ok ? await layoutResponse.json() : null;
  state.uiPreviews = previewResponse && previewResponse.ok ? await previewResponse.json() : null;
  state.data = data;
  renderHeader(data);
  renderMetrics(data);
  renderPmInsights(data);
  renderFilters(data);
  renderFeatures(data);
  renderShots(data);
  renderCoverage(data);
  renderInfra(data);
  renderEvidence(data);
}

main().catch((error) => {
  document.body.innerHTML = `<main><pre>${escapeHtml(error.stack || error.message)}</pre></main>`;
});
