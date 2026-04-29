# APK Competitor Monitor Product Requirements

## 1. 背景

产品团队需要持续跟踪竞品 Android App 和配套 Web/admin 后台的变化，快速判断竞品是否上线了新功能、调整了关键路径、改变了商业化/团队协作/安全能力，或者仅仅是 SDK、资源、构建产物变化。

传统竞品分析依赖人工安装、截图、走查和零散记录，存在几个问题：

- 新版本发现不稳定，容易漏掉 APK 更新。
- 反编译证据难读，产品经理无法直接判断影响。
- UI 变化、API 变化、事件 key、Manifest 入口和 Web 后台变化分散在不同工具里。
- 周报生成、归档、发布和企业微信通知依赖人工串流程。
- 不同竞品项目接入时，配置、发布地址、企微机器人和 Web 路由需要可复用。

本工具的目标是把这些动作产品化为一条可被 Codex skill、Codex plugin 或 MCP client 调用的竞品监控流水线。

## 2. 产品目标

### 2.1 核心目标

- 自动检查豌豆荚 App 页面是否有新 APK 版本。
- 当 APK 有新版本时，自动完成 old/new APK 静态 diff、深度 UI diff、源码级 API/调用链分析和 PM 报告生成。
- 每次运行 Web/admin 路由监控，识别后台页面结构、状态和关键业务信号变化。
- 生成统一 PM 周报，支持本地查看、轻量归档、静态站点发布和企业微信通知。
- 以 MCP tools 形式开放单步能力和一键总编排能力，方便其他 agent 或自动化系统调用。

### 2.2 非目标

- 不绕过登录、付费、权限或服务端风控。
- 不提供商业用途授权；仓库遵循 PolyForm Noncommercial License。
- 不把静态 UI 重建当成真实运行截图。
- 不把 Web/admin 原始快照、客户、成员、照片、位置、网络日志等敏感数据公开发布。
- 不保证仅靠 APK 静态分析能确认灰度、账号态、会员态、服务端配置或 H5 动态页面。

## 3. 目标用户

- 产品经理：查看竞品功能变化、影响判断、验证建议和周报结论。
- 竞品分析人员：追溯 evidence chain、静态 UI、API diff、layout diff 和未解释变化池。
- 研发/逆向分析人员：使用 MCP tools 执行 APK diff、反编译、API surface diff、feature flow tracing。
- 自动化/Agent 系统：通过 `run_full_weekly_pipeline` 执行端到端监控、发布和通知。

## 4. 核心场景

### 4.1 APK 新版本监控

输入：

- 豌豆荚 App 页面 URL。
- 上一次监控状态 `state.json`。
- 项目配置 `project_config`，包含 App 名称、包名、报告目录和发布/通知设置。

流程：

1. 检查豌豆荚页面版本信息。
2. 如果没有新版，跳过 APK 报告生成，并在统一周报中明确显示“沿用上一份 APK 报告”。
3. 如果有新版，下载 APK，和上一次监控版本对比。
4. 只有 APK 报告和归档生成成功后，才更新 APK state。

输出：

- APK 详情报告。
- 轻量 searchable archive。
- PDF，若本地 Chrome/Playwright 可用。
- 状态更新结果。

### 4.2 APK 功能/UI 变化分析

分析层包括：

- 基础 APK diff：文件、Manifest、DEX strings、resources、URLs、API path、events、native libs、SDK hints。
- 产品分类：安全模式、团队/工作组、拼图/图片编辑、会员/VIP、微信验证、定位、上传同步、广告、AI、拍摄底层等。
- 深度 UI diff：apktool layout/resource diff、JADX Activity/Fragment/Dialog 到 layout 映射。
- 静态 UI 重建：新增/变更 layout 的 SVG preview，支持 old/new side-by-side。
- API surface：从 JADX sources 提取 URL、OkHttp、Retrofit、Volley、WebView、auth、base URL。
- API surface diff：比较 old/new API surface，识别新增/移除的网络/API/H5/auth 信号。
- Feature flow：把 screen、click/navigation/lifecycle、layout 和 API diff 串成变化调用链候选。
- Evidence grouping：每个功能卡区分新增、移除、变更/关联证据。

### 4.3 Web/admin 路由监控

输入：

- `artifacts/web-monitor/config.json` 中配置的路由列表。
- 登录态 storage state。
- baseline 文件。

流程：

1. 使用 Playwright 访问配置路由。
2. 识别正常页、登录页、团队选择页、空白页和网络失败。
3. 登录页、团队选择页、空白页和网络失败属于阻塞状态，不允许更新 baseline。
4. 成功探测后生成 Web/admin PM 报告和归档。

输出：

- Web/admin 详情报告。
- 路由状态统计。
- 变更路由摘要。
- 红acted PM-facing 变化结论。

### 4.4 统一周报、发布和通知

流程：

1. 汇总 APK 线和 Web/admin 线。
2. 生成统一 PM 周报。
3. 构建静态发布目录。
4. 部署到 GitHub Pages。
5. 企业微信机器人发送报告链接和红acted 摘要。

规则：

- 部署成功时，公共 GitHub Pages URL 是主入口。
- 本地 APK/Web/统一报告路径作为次级入口。
- 企微 webhook 必须支持项目配置覆盖。
- 企微发送失败不应影响本地报告产物，但必须在结果中明确标记。

## 5. 功能需求

### 5.1 项目配置

系统必须支持通过 JSON 配置复用不同项目。

配置字段：

- `project_id`
- `app.name`
- `app.package`
- `source.type`
- `source.app_url`
- `apk.state_file`
- `apk.report_root`
- `apk.report_dir`
- `apk.preview_limit`
- `web.enabled`
- `web.route_ids`
- `web.report_dir`
- `weekly.enabled`
- `weekly.report_dir`
- `publish.enabled`
- `publish.dir`
- `publish.url`
- `notify.enabled`
- `notify.dry_run`
- `notify.wecom_webhook_url`
- `analysis.enable_deep_ui_diff`
- `analysis.enable_static_ui_previews`
- `analysis.export_pdf`
- `analysis.export_archive`

### 5.2 MCP tools

APK / reverse-engineering tools:

- `get_skill_overview`
- `monitor_wandoujia`
- `check_re_dependencies`
- `decompile_with_engines`
- `analyze_apk_diff`
- `extract_api_surface`
- `diff_api_surface`
- `trace_feature_flow`
- `deep_ui_analysis`
- `product_ui_analysis`
- `build_deep_ui_web_data`
- `render_static_ui_previews`
- `generate_apk_report_bundle`
- `export_simple_archive`
- `export_report_pdf`

Workspace tools:

- `web_probe_admin`
- `web_generate_report`
- `web_run_weekly`
- `weekly_generate_unified_report`
- `publish_build_site`
- `publish_deploy_site`
- `notify_wecom_weekly_report`
- `run_full_weekly_pipeline`

### 5.3 报告能力

APK 报告必须包含：

- PM 洞察页。
- 功能变化卡片。
- 证据 badge。
- 新增/移除/变更证据分组。
- API surface diff 摘要。
- diff-aware feature flow 摘要。
- 静态 UI 预览。
- layout/resource diff。
- decompilation coverage。
- obfuscation impact。
- unexplained-change pool。
- SDK/native changes。
- raw evidence counts。

统一周报必须包含：

- APK 版本状态。
- APK 报告是否为本周新生成或沿用上一份报告。
- Web/admin route 状态统计。
- top PM-facing changes。
- coverage / obfuscation summary。
- manual validation items。
- public URL 和本地详情路径。

### 5.4 隐私与安全

- Web/admin 原始快照不得发布到公开站点。
- Web/admin visible text、HTML、network logs、截图若可能包含敏感数据，只能保存在本地工作区。
- 周报和企微通知只能包含红acted 摘要。
- WeCom webhook 可以通过参数传入，但不应写入公开报告。
- APK 静态分析结论必须标注静态/运行态边界。

## 6. 数据产物

APK 产物：

- `diff-OLD-to-NEW.json`
- `product-ui-analysis-OLD-to-NEW.json`
- `ui-layout-diff-OLD-to-NEW.json`
- `ui-layout-data.json`
- `ui-preview-data.json`
- `api-surface-old.json`
- `api-surface.json`
- `api-surface-diff.json`
- `feature-flow.json`
- `report-data.json`
- `static-ui-data.json`
- `archive-manifest.json`
- `*.zip`
- `report.pdf` 或 `PDF_EXPORT_NOT_AVAILABLE.txt`

Web/admin 产物：

- `probe-summary.json`
- `report-data.json`
- `archive.zip`
- baseline 更新结果。

统一周报产物：

- `weekly-data.json`
- `index.html`
- `weekly-archive.zip`

## 7. 验收标准

### 7.1 APK 线

- 无新版 APK 时，不生成新的 APK 详情报告，不更新 APK state，并在统一周报明确标注沿用上一份 APK 报告。
- 有新版 APK 时，必须生成 APK 详情报告和 archive 后才允许更新 APK state。
- APK 报告必须包含 API surface diff 和 diff-aware feature flow 统计。
- 功能卡必须能展示至少一组新增/移除/变更证据。
- 静态 UI 预览失败时，报告必须说明缺失原因，不能静默成功。

### 7.2 Web/admin 线

- 每次运行都必须执行 Web/admin route probe。
- 登录页、团队选择页、空白页、网络失败必须阻止 baseline 更新。
- 报告和 archive 生成成功后，才允许更新 baseline。
- 公共发布产物不得包含 raw snapshots、storage state、visible text、network logs 或 HTML。

### 7.3 通知和发布

- GitHub Pages 部署成功后，企微通知优先使用公共 URL。
- 企微发送失败必须返回失败原因。
- `dry_run` 模式必须输出 payload，但不能真实发送。

### 7.4 MCP

- `initialize` 和 `tools/list` 必须成功。
- 每个 tool 必须返回结构化 JSON 或包含可解析 JSON 的 stdout。
- 一键 pipeline 必须返回 APK/Web/weekly/publish/notify 各阶段结果。

## 8. 关键指标

- 新版 APK 检测准确率。
- APK 报告生成成功率。
- Web route probe 成功率。
- baseline 阻塞态识别准确率。
- 静态 UI preview 覆盖数。
- diff-aware feature flow 数量。
- PM 人工验证项命中率。
- 周报发布成功率。
- 企微通知送达成功率。

## 9. 风险与限制

- 豌豆荚页面结构变化会影响 APK 检测。
- Java、apktool、jadx、Chrome/Playwright 缺失会影响深度分析或 PDF 导出。
- 混淆、加密字符串、动态配置会降低功能语义恢复能力。
- H5/WebView 页面内容可能不在 APK 中。
- 静态 UI SVG 不是运行截图，不能证明用户一定可见。
- Web/admin 登录态过期会阻塞 Web 基线更新。

## 10. 路线图

### P0 已具备

- APK version check。
- APK static diff。
- product/UI analysis。
- apktool/JADX deep UI diff。
- static UI preview。
- API surface extraction。
- API surface diff。
- diff-aware feature flow。
- Web/admin route monitor。
- unified weekly report。
- static publish。
- WeCom notification。
- MCP tools 和一键 pipeline。

### P1 下一步

- JSON Schema 配置校验。
- method-level semantic diff。
- feature score 解释表。
- 登录态刷新辅助 tool。
- 一键初始化监控工作区脚手架。
- CI regression tests。

### P2 后续

- 动态真机截图/ADB/UIAutomator 对比。
- H5/WebView 内容抓取和红action。
- 多竞品项目 dashboard。
- 报告订阅和历史趋势分析。

