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
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
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
  document.getElementById("summaryText").textContent =
    `本报告聚合 APK 静态差异，重点识别功能和 UI 增删改。新版包体从 ${data.summary.apkOldSize} 降至 ${data.summary.apkNewSize}，同时出现安全模式、团队照片标签、微信绑定、会员状态和工作组入口等产品线索。`;
}

function renderMetrics(data) {
  const metrics = [
    ["features", data.summary.features],
    ["uiChanges", data.summary.uiChanges],
    ["resourceStringsAdded", data.summary.resourceStringsAdded],
    ["eventsAdded", data.summary.eventsAdded],
    ["apisAdded", data.summary.apisAdded],
    ["imagesAdded", data.summary.imagesAdded],
    ["imagesRemoved", data.summary.imagesRemoved],
    ["infraChanges", data.summary.infraChanges],
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
      const summary = node.querySelector(".summary-list");
      feature.summary.forEach((line) => summary.appendChild(el("li", "", line)));
      addTags(node.querySelector(".page-tags"), feature.pages);
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
      images: data.raw.images,
      urlsAdded: data.raw.urlsAdded,
      urlsRemoved: data.raw.urlsRemoved,
    },
    null,
    2,
  );
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
  renderFilters(data);
  renderFeatures(data);
  renderShots(data);
  renderInfra(data);
  renderEvidence(data);
}

main().catch((error) => {
  document.body.innerHTML = `<main><pre>${escapeHtml(error.stack || error.message)}</pre></main>`;
});
