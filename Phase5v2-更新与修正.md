# Phase 5 v2 — 更新与修正

> 2026-05-12 | 相对于 Phase5-uni-app小程序实施方案.md 的 delta
> 汇总近期测试中发现的问题修复 + 架构调整

---

## 一、技术栈变更：uni-app → Vue 3 + Vite (H5)

| 项目   | v1 方案                             | v2 实际                     |
| ---- | --------------------------------- | ------------------------- |
| 框架   | uni-app 3 (Vue 3)                 | **Vue 3 + Vite** SPA      |
| 路由   | pages.json                        | **Vue Router 4** (hash模式) |
| HTTP | uni.request                       | **fetch** API             |
| 存储   | uni.setStorageSync                | **localStorage**          |
| 组件   | `<view>` `<text>` `<scroll-view>` | `<div>` `<span>` `<div>`  |
| 事件   | `@tap` `@tap.stop`                | `@click` `@click.stop`    |
| 编译目标 | 微信小程序 → H5                        | **H5 网页** (简历展示)          |
| 图表   | uCharts                           | 纯 CSS 柱状图 (后续可引入 uCharts) |

**变更理由**：简历项目用网页展示即可，暂时不需要小程序审核流程。Vue 3 + Vite 开发体验更好，`@tap`/`<view>` 等 uni-app 专有语法导致的 bug 全部消除。

---

## 二、Bug 修复汇总

### B1 — Perception 日期僵硬 + 指标不全 🔴

| 问题              | 原因                                                         | 修复                                                |
| --------------- | ---------------------------------------------------------- | ------------------------------------------------- |
| 健康数据分析只返回1-2个指标 | `perception_node` 只查 `date.today()`，且 LLM Prompt 未要求列出全部指标 | 改为**近3天窗口**（今天/昨天/前天），Prompt 明确要求"逐一列出所有可用指标"     |
| 问"昨天心率"仍返回今天数据  | perception 不解析查询中的日期                                       | 3天数据全量提供给 LLM，在 Prompt 中加入"如果用户询问了具体日期，优先回答那天的数据" |

**影响文件**：`agents/perception.py`（重写）

### B2 — 医疗问答超时 🔴

| 问题 | 原因 | 修复 |
|------|------|------|
| Self-RAG 耗时 ~60s，前端显示"网页连接错误" | `fetch` 超时 30s < Self-RAG 实际耗时 | 超时升至 **120s** |

**影响文件**：`frontend/src/api/request.js`

### B3 — 422 错误 🔴

| 问题 | 原因 | 修复 |
|------|------|------|
| `POST /api/v1/chat` 返回 422 | Pydantic v2 中 `session_id: str = None` 拒绝 `null` 值 | 改为 `Optional[str] = None` |

**影响文件**：`data_pipeline/webhook_server.py`

### B4 — 设置页"检测"按钮无效 🔴

| 问题 | 原因 | 修复 |
|------|------|------|
| 点击无反应 | `@tap` 是 uni-app 指令，Vue 3 不识别 | 改为 `@click`；store 的 `checkServer` 修复动态导入 |

**影响文件**：`frontend/src/pages/settings/index.vue`、`frontend/src/stores/app.js`

### B5 — Report 页不渲染 🔴

| 问题 | 原因 | 修复 |
|------|------|------|
| 页面空白 | `<view>` `<text>` `<scroll-view>` 是 uni-app 组件 | 全部换为标准 HTML `<div>` `<span>` |

**影响文件**：`frontend/src/pages/report/index.vue`（重写）

### B6 — 日期格式兼容性 🟡

| 问题 | 原因 | 修复 |
|------|------|------|
| `GET /daily?date=2026-5-11` 返回空 | SQLite 存储 `2026-05-11`，与输入不匹配 | `/daily` 和 `/raw` 端点加 `dateutil.parser.parse()` 标准化 |

**影响文件**：`data_pipeline/webhook_server.py`

### B7 — 增量聚合全量重算 🟡

| 问题 | 原因 | 修复 |
|------|------|------|
| 增量聚合每次触发全量 | `func.date()` 返回 `str`，`DailyMetric.date` 是 `datetime.date`，set差集类型不匹配 | `raw_days` 统一转 `date.fromisoformat(str(r[0]))` |

**影响文件**：[[Phase1-测试手册]] §5.2

### B8 — 会话切换无反馈 🟡

| 问题 | 原因 | 修复 |
|------|------|------|
| 点击历史会话无反应 | 错误被静默吞掉，无用户提示 | 添加 `try/catch` + Toast 提示 |

**影响文件**：`frontend/src/pages/chat/index.vue`

### B9 — 设置页白框 🟢

| 问题 | 原因 | 修复 |
|------|------|------|
| 输入框内白色背景与卡片不协调 | `background: #fafafa` 偏白 | 改为 `#f5f5f5` |

**影响文件**：`frontend/src/pages/settings/index.vue`

---

## 三、版本号更新

| 位置 | v1 | v2 |
|------|----|----|
| 设置页版本 | Phase 5 v1.0 | **v3.0** |
| 后端版本 | 2.0.0 (webhook_server) | — (不变) |
| 方案文档 | Phase5-uni-app小程序实施方案.md | 本文件 |

---

## 四、Phase 5 v2 新增端点

| 端点 | 说明 | 状态 |
|------|------|------|
| `GET /api/v1/report/weekly/list` | 周报历史列表 | ✅ 已实现 |
| `DELETE /api/v1/memory/sessions/{id}` | 清除会话 | ✅ 已实现 |
| `GET /api/v1/health/trend` | 多周趋势 | ✅ 已实现 (Phase 4) |

---

## 五、当前全部端点总览

| 端点 | Phase | 方法 | 用途 |
|------|-------|------|------|
| `/api/v1/health/sync` | 1 | POST | 接收 Apple Health 数据 |
| `/api/v1/health/status` | 1 | GET | 数据库概览 |
| `/api/v1/health/daily` | 1 | GET | 日聚合指标 |
| `/api/v1/health/raw` | 1 | GET | 原始数据查询 |
| `/api/v1/health/baseline` | 1 | GET | 30天基线 |
| `/api/v1/health/trend` | 4 | GET | 多周趋势 |
| `/api/v1/chat` | 3+4 | POST | 多轮对话 |
| `/api/v1/memory/sessions` | 4 | GET | 会话列表 |
| `/api/v1/memory/history` | 4 | GET | 对话历史 |
| `/api/v1/memory/sessions/{id}` | 4 | DELETE | 清除会话 |
| `/api/v1/report/weekly` | 4 | POST | 生成周报 |
| `/api/v1/report/weekly` | 4 | GET | 查询历史周报 |
| `/api/v1/report/weekly/list` | 4 | GET | 周报列表 |

---

## 六、Phase 5 v2 第二轮修复 (2026-05-12 晚间)

### B10 — 回复含 Markdown 符号 🔴

| 问题 | 原因 | 修复 |
|------|------|------|
| 回复中出现 `*`、`-`、`**` 等符号，无分段 | LLM 默认输出 Markdown 格式 | `prompts/action.py` 和 `prompts/analysis.py` 加入 **禁止 Markdown 格式** 规则，要求纯文本分段输出 |

**影响文件**：`prompts/action.py`、`prompts/analysis.py`

### B11 — 等待期间无进度反馈 🔴

| 问题 | 原因 | 修复 |
|------|------|------|
| 60s 等待完全空白 | 前端仅显示"思考中..." | 根据耗时显示动态进度标签：意图分析→检索知识库→生成草稿→自检修正；加入脉冲动画 |

**影响文件**：`frontend/src/pages/chat/index.vue`

### B12 — 看板全显示"数据收集中" 🔴

| 问题 | 原因 | 修复 |
|------|------|------|
| Dashboard 所有卡片 -- | `getTodayMetrics()` 只查今天，今天无数据则返回空 | 改为回退策略：今天→昨天→前天，查到非空即止 |

**影响文件**：`frontend/src/stores/health.js`

### B13 — 浏览器 CORS 预检 405 🔴

| 问题 | 原因 | 修复 |
|------|------|------|
| `OPTIONS` 请求返回 405 | FastAPI 未配置 CORS 中间件 | 添加 `CORSMiddleware(allow_origins=["*"])` |

**影响文件**：`data_pipeline/webhook_server.py`

### B14 — 周报 POST 422 🔴

| 问题 | 原因 | 修复 |
|------|------|------|
| 生成周报返回 422 | `WeeklyRequest.week_start: str = None` 同上 Pydantic bug | 改为 `Optional[str] = None` |

**影响文件**：`data_pipeline/webhook_server.py`


---

## 七、Phase 5 v3 — 全量指标聚合与展示 (2026-05-13)

### B15 — 全量指标聚合

iOS 同步 39 种指标，`config.py` 仅 16 种。补全全部 39 种，376 天全量重聚合 → 9635 行。

**新增 23 种**：`walking_heart_rate_average`, `cardio_recovery`, `apple_stand_hour`, `vo2_max`, `six_minute_walking_test_distance`, `stair_speed_down/up`, `running_power/speed/ground_contact_time/vertical_oscillation/stride_length`, `cycling_distance`, `sleep_analysis`, `weight_body_mass`, `body_fat_percentage`, `body_mass_index`, `height`, `environmental_audio_exposure`, `headphone_audio_exposure`, `time_in_daylight`, `mindful_minutes`, `handwashing`

**影响**：`data_pipeline/config.py`

### B16-B18 — 前端 & Perception 标签同步

| 文件 | 改动 |
|------|------|
| `frontend/.../dashboard/index.vue` | `iconMap`/`labelMap` 9→39, 趋势图 2→4 |
| `frontend/.../report/index.vue` | `labelMap` 9→39 |
| `agents/perception.py` | `metric_labels` 16→39 英文标签 |

### B19 — UI/UX 综合改进

| # | 改进 | 文件 |
|---|------|------|
| Settings 重构 | 去 URL 编辑, 全英文化, 加数据来源+技术栈 | `settings/index.vue` |
| Markdown 渲染 | `**粗体**`/`- 列表`/`## 标题` → HTML | `markdown.js` + `chat/index.vue` |
| Perception 传日期 | `Today's date: {today}` 注入 Prompt | `agents/perception.py` |
| Perception 全量 | Prompt 要求 "逐项分析全部 N 指标, 不得遗漏" | `agents/perception.py` |
| 进度动画 | 意图分析→检索→生成→自检 四阶段动态标签 | `chat/index.vue` |
| Dashboard 回退 | 今天无数据 → 昨天 → 前天 | `stores/health.js` |
| Prompt 恢复 | action/analysis 恢复 Markdown 输出 | `prompts/action.py`, `prompts/analysis.py` |

---

## 八、Phase 5 v4 — 速度 + 日期 + 会话修复 (2026-05-14)

### B20 — Router 极速版 🔴

意图识别从 ~2s 降到 <0.01s（80%+ 查询命中关键词）：

| 策略 | 说明 |
|------|------|
| 关键词优先 | 健康数据、医疗问答各 15+ 关键词，命中即返回 |
| LLM 兜底 | 仅关键词同时命中或都未命中的模糊查询才调 LLM |

**影响**：`agents/router.py`（重写）

### B21 — 进度实时更新 🔴

`Date.now()` 在 `computed` 中不触发响应式 → 进度标签卡住。

修复：`setInterval` 每 0.5s 刷新 `elapsed` 值 → 标签实时跳动。

**影响**：`frontend/.../chat/index.vue`

### B22 — 日期感知 v4 🔴

始终给 LLM **3 天数据 + 当前时间**，不再根据 query 缩小日期范围。

```
Current time: 08:30, date: 2026-05-14
The day is not over yet — data shown is partial for today.
```

**影响**：`agents/perception.py`

### B23 — 时间问候 🟡

LLM 回复开头根据时间段问候（早上好/下午好/晚上好），输出中包含当前具体时间。

**影响**：`agents/action.py`、`prompts/action.py`

### B24 — 会话切换修复 🔴

GET 请求的 `data` 参数被放入 `body`（浏览器忽略）→ 后端收不到 `session_id` → 切换失败。

修复：GET/DELETE 请求自动将 `data` 拼为 URL 查询字符串。

**影响**：`frontend/src/api/request.js`

### B25 — 会话删除 🔴

新增 ✕ 按钮，调 `DELETE /api/v1/memory/sessions/{id}`，即时从列表移除。

**影响**：`frontend/.../chat/index.vue`

---

## 九、完整 Bug 索引 (B1-B25)

| # | 类别 | 问题 | 状态 |
|---|------|------|:--:|
| B1 | Perception | 日期僵硬 + 指标不全 | ✅ |
| B2 | 前端 | Self-RAG 超时 30s→120s | ✅ |
| B3 | 后端 | Pydantic 422 session_id | ✅ |
| B4 | 前端 | @tap→@click + 检测按钮 | ✅ |
| B5 | 前端 | Report uni-app 组件 → HTML | ✅ |
| B6 | 后端 | 日期格式兼容 dateutil | ✅ |
| B7 | 聚合 | 增量聚合类型不匹配 | ✅ |
| B8 | 前端 | 会话切换无反馈 | ✅ |
| B9 | 前端 | 设置页白框 | ✅ |
| B10 | Prompt | 回复含 Markdown 符号 | ✅ |
| B11 | 前端 | 等待无进度反馈 | ✅ |
| B12 | 前端 | Dashboard 空数据回退 | ✅ |
| B13 | 后端 | CORS OPTIONS 405 | ✅ |
| B14 | 后端 | 周报 POST 422 | ✅ |
| B15 | 聚合 | 39 种指标全量聚合 | ✅ |
| B16 | 前端 | Dashboard 标签 9→39 | ✅ |
| B17 | 前端 | Report 标签 9→39 | ✅ |
| B18 | Agent | Perception 标签 16→39 | ✅ |
| B19 | UI/UX | Settings+Markdown+进度 | ✅ |
| B20 | Router | 关键词快速分类 | ✅ |
| B21 | 前端 | 进度条实时更新 | ✅ |
| B22 | Agent | 日期感知 3天+时间 | ✅ |
| B23 | Agent | 时间问候语 | ✅ |
| B24 | 前端 | GET 参数拼 URL | ✅ |
| B25 | 前端 | 会话删除按钮 | ✅ |
