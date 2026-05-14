# Phase 5 uni-app 小程序前端 — 实施方案

> 2026-05-11 | 依赖 Phase 1 ✅ + Phase 3 ✅ + Phase 4 ⚠️ | Vue 3 + Pinia + uni-app
> 目标：微信小程序，对话+健康看板+周报+设置 四大页面

---

## 一、前置条件 & 接口依赖总览

### 1.1 后端 API 就绪清单

| 端点 | Phase | 前端页面 | 用途 |
|------|-------|---------|------|
| `POST /api/v1/chat` | 3+4 | Chat | 单轮/多轮对话，返回 `session_id` |
| `GET /api/v1/memory/sessions` | 4 | Chat | 历史会话列表，前端切换 session |
| `GET /api/v1/memory/history?session_id=X` | 4 | Chat | 加载某 session 的聊天记录 |
| `DELETE /api/v1/memory/sessions/{id}` | 4 | Chat | 清除会话 |
| `GET /api/v1/health/status` | 1 | Dashboard, Settings | 数据库概览（最近同步时间） |
| `GET /api/v1/health/daily?date=today` | 1 | Dashboard | 今日各指标聚合值 |
| `GET /api/v1/health/baseline?metric=X&days=30` | 1 | Dashboard | 30天基线对比 |
| `GET /api/v1/health/trend?metric=X&weeks=4` | 4 | Dashboard, Report | 多周趋势图 |
| `POST /api/v1/report/weekly` | 4 | Report | 生成本周周报 |
| `GET /api/v1/report/weekly?week_start=X` | 4 | Report | 查询历史周报 |
| `GET /api/v1/report/weekly/list` | 4 | Report | 周报历史列表 |

### 1.2 数据流图

```
┌─────────────────────────────────────────────────────────────┐
│                     uni-app 小程序                           │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Chat    │  │Dashboard │  │  Report  │  │ Settings │   │
│  │  对话页   │  │ 健康看板  │  │ 周报展示  │  │ 设置页面  │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │              │              │              │        │
│  ┌────┴──────────────┴──────────────┴──────────────┴────┐   │
│  │              Pinia Store (状态管理)                    │   │
│  │  chatStore  │  healthStore  │  reportStore  │  appStore│   │
│  └───────────────────────┬──────────────────────────────┘   │
│                          │                                  │
│  ┌───────────────────────┴──────────────────────────────┐   │
│  │              api/ (HTTP 请求封装)                      │   │
│  │  request.js  │  chat.js  │  health.js  │  report.js   │   │
│  └───────────────────────┬──────────────────────────────┘   │
└──────────────────────────┼──────────────────────────────────┘
                           │ HTTP (ngrok URL 或 localhost)
                           ▼
              ┌─────────────────────────┐
              │   FastAPI :8000         │
              │   /api/v1/chat          │
              │   /api/v1/health/*      │
              │   /api/v1/report/*      │
              │   /api/v1/memory/*      │
              └─────────────────────────┘
```

---

## 二、技术栈

### 2.1 框架与工具

| 层级    | 技术                             | 说明                             |
| ----- | ------------------------------ | ------------------------------ |
| 框架    | **uni-app 3.x** (Vue 3 + Vite) | 一套代码→微信小程序/H5/App              |
| 语言    | JavaScript (ES6+)              | Vue SFC 单文件组件                  |
| 状态管理  | **Pinia**                      | Vue 3 官方推荐，替代 Vuex             |
| HTTP  | `uni.request`                  | 小程序原生请求（自动处理域名白名单）             |
| 图表    | **uCharts**                    | uni-app 生态，轻量<30KB，支持折线/柱状/环形图 |
| UI 组件 | uni-ui 官方组件                    | 按钮、输入框、卡片、列表等                  |
| 构建    | HBuilderX 或 CLI                | HBuilderX 推荐（一键编译+调试）          |
| 目标平台  | **微信小程序** (首选) → 支付宝小程序 → H5   |                                |

### 2.2 为什么这些选型

**uCharts 而非 ECharts**：
- ECharts 完整包 ~1MB，微信小程序主包限制 2MB，不够用
- uCharts <30KB，支持心率趋势折线图、步数柱状图、睡眠环形图，完全够用
- uni-app 插件市场可直接引入，`<qiun-data-charts>` 组件

**Pinia 而非 Vuex**：
- Pinia 是 Vue 3 官方推荐，TypeScript 友好，API 更简洁
- 模块化 `defineStore` 天然隔离 chat/health/report 状态

**`uni.request` 而非 axios**：
- 微信小程序不支持 axios（依赖浏览器 XMLHttpRequest）
- `uni.request` 是小程序原生 HTTP API，uni-app 自动跨平台适配

---

## 三、项目结构

```
frontend/
├── pages/
│   ├── chat/
│   │   └── index.vue              # 对话主页面
│   ├── dashboard/
│   │   └── index.vue              # 健康看板
│   ├── report/
│   │   └── index.vue              # 周报展示
│   └── settings/
│       └── index.vue              # 设置页
├── components/
│   ├── ChatBubble.vue             # 聊天气泡（用户/AI 左右区分）
│   ├── HealthCard.vue             # 健康指标卡片（心率/步数/睡眠）
│   ├── MetricChart.vue            # 趋势折线图（uCharts 封装）
│   ├── WeeklyNarrative.vue        # 周报叙事卡片
│   ├── SessionList.vue            # 历史会话列表
│   └── StatusBar.vue              # 数据同步状态条
├── stores/
│   ├── chat.js                    # 对话状态
│   ├── health.js                  # 健康数据状态
│   ├── report.js                  # 周报状态
│   └── app.js                     # 全局配置（API地址、LLM provider等）
├── api/
│   ├── request.js                 # uni.request 封装（baseURL + 拦截器）
│   ├── chat.js                    # /chat + /memory API
│   ├── health.js                  # /health API
│   └── report.js                  # /report API
├── static/
│   └── logo.png
├── pages.json                     # 页面路由 + TabBar 配置
├── manifest.json                  # 应用配置（微信 appid 等）
├── uni.scss                       # 全局样式变量
├── App.vue                        # 应用入口
└── main.js                        # Vue 初始化 + Pinia 注册
```

---

## 四、逐文件详细设计

### 4.1 `api/request.js` — HTTP 封装

```javascript
// api/request.js
// 统一封装 uni.request，自动拼接 baseURL，处理错误

const BASE_URL = 'https://your-ngrok-url.ngrok-free.app'  // 开发时改这里
// const BASE_URL = 'http://localhost:8000'               // 本地调试用

const request = (url, options = {}) => {
  return new Promise((resolve, reject) => {
    uni.request({
      url: BASE_URL + url,
      method: options.method || 'GET',
      data: options.data,
      header: {
        'Content-Type': 'application/json',
        ...options.header,
      },
      timeout: 30000,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          uni.showToast({ title: `请求失败: ${res.statusCode}`, icon: 'none' })
          reject(res)
        }
      },
      fail: (err) => {
        uni.showToast({ title: '网络不可达，请检查服务是否启动', icon: 'none' })
        reject(err)
      },
    })
  })
}

export default request
```

**技术点**：`uni.request` 是小程序原生 HTTP API。不支持浏览器 `fetch`/`axios`。返回 Promise 方便 `async/await`。`BASE_URL` 开发时写 ngrok URL，上线后换成正式域名。

### 4.2 `api/chat.js` — 对话 API

```javascript
// api/chat.js
import request from './request'

// 发送消息（多轮通过 session_id 关联）
export const sendMessage = (query, sessionId = null) => {
  return request('/api/v1/chat', {
    method: 'POST',
    data: { query, session_id: sessionId },
  })
}

// 获取历史会话列表
export const getSessions = () => {
  return request('/api/v1/memory/sessions')
}

// 加载某会话的聊天记录
export const getHistory = (sessionId, n = 20) => {
  return request('/api/v1/memory/history', {
    data: { session_id: sessionId, n },
  })
}

// 删除会话
export const deleteSession = (sessionId) => {
  return request(`/api/v1/memory/sessions/${sessionId}`, {
    method: 'DELETE',
  })
}
```

### 4.3 `api/health.js` — 健康数据 API

```javascript
// api/health.js
import request from './request'

// 今日聚合数据
export const getTodayMetrics = (date) => {
  return request('/api/v1/health/daily', {
    data: { date: date || new Date().toISOString().slice(0, 10) },
  })
}

// 30天基线
export const getBaseline = (metric, days = 30) => {
  return request('/api/v1/health/baseline', {
    data: { metric_type: metric, days },
  })
}

// 多周趋势
export const getTrend = (metric, weeks = 4) => {
  return request('/api/v1/health/trend', {
    data: { metric, weeks },
  })
}

// 同步状态
export const getSyncStatus = () => {
  return request('/api/v1/health/status')
}
```

### 4.4 `api/report.js` — 周报 API

```javascript
// api/report.js
import request from './request'

export const generateReport = (weekStart = null) => {
  return request('/api/v1/report/weekly', {
    method: 'POST',
    data: { week_start: weekStart },
  })
}

export const getReport = (weekStart) => {
  return request('/api/v1/report/weekly', {
    data: { week_start: weekStart },
  })
}

export const getReportList = () => {
  return request('/api/v1/report/weekly/list')
}
```

---

### 4.5 `stores/chat.js` — Pinia 对话状态

```javascript
// stores/chat.js
import { defineStore } from 'pinia'
import { sendMessage, getSessions, getHistory } from '@/api/chat'

export const useChatStore = defineStore('chat', {
  state: () => ({
    messages: [],           // [{ role: 'user'|'assistant', content, time }]
    currentSessionId: null, // 当前会话 ID
    sessions: [],           // 历史会话列表
    loading: false,
  }),

  actions: {
    // 发送消息
    async send(query) {
      this.messages.push({ role: 'user', content: query, time: Date.now() })
      this.loading = true

      try {
        const res = await sendMessage(query, this.currentSessionId)
        this.currentSessionId = res.session_id
        this.messages.push({
          role: 'assistant',
          content: res.response,
          intent: res.intent,
          safety: res.safety_level,
          time: Date.now(),
        })
      } catch (e) {
        this.messages.push({
          role: 'assistant',
          content: '抱歉，网络连接失败，请检查服务是否启动。',
          time: Date.now(),
        })
      } finally {
        this.loading = false
      }
    },

    // 加载历史会话列表
    async loadSessions() {
      const res = await getSessions()
      this.sessions = res.sessions || []
    },

    // 切换到历史会话
    async switchSession(sessionId) {
      this.currentSessionId = sessionId
      const res = await getHistory(sessionId)
      this.messages = (res.history || []).map(h => ({
        role: h.role,
        content: h.content,
        time: Date.now(),
      }))
    },

    // 开始新对话
    newChat() {
      this.currentSessionId = null
      this.messages = []
    },
  },
})
```

**技术点**：Pinia 的 `defineStore` 使用 Options API 风格（`state` + `actions`），与 Vue 组件语法一致。`this.currentSessionId` 自动关联多轮——首次 `send` 时后端返回新 session_id，后续追问自动携带。

---

### 4.6 `pages/chat/index.vue` — 对话页

```
┌─────────────────────────┐
│  ☰ 历史会话    ✚ 新对话   │  ← 顶部导航栏
├─────────────────────────┤
│                         │
│   [AI] 我是您的私人健康  │
│   顾问，有什么可以帮您？  │
│                         │
│              [User] 今天 │
│              心率怎么样？ │
│                         │
│   [AI] 您今日平均心率    │
│   72 bpm，在正常范围...  │
│                         │
├─────────────────────────┤
│  [输入框____________] 📤 │  ← 底部输入区
└─────────────────────────┘
```

关键交互：
- 进入页面自动 `loadSessions()`，点击左上角弹出 `SessionList` 组件
- 消息列表 `scroll-view` 自动滚到底部
- 发送后显示 loading 动画（AI 思考中...）
- 紧急回答用红色气泡标识

### 4.7 `pages/dashboard/index.vue` — 健康看板

```
┌─────────────────────────┐
│  健康看板     5月11日     │
│  ✅ 数据同步于 08:30      │  ← StatusBar 组件
├─────────────────────────┤
│  ┌──────┐ ┌──────┐     │
│  │ ❤️ 72 │ │ 👣 8.5k│     │  ← HealthCard 组件
│  │ 心率   │ │ 步数   │     │     (2列网格)
│  │ 正常   │ │ 达标   │     │
│  └──────┘ └──────┘     │
│  ┌──────┐ ┌──────┐     │
│  │ 💤 7.2│ │ 🔥 2100│    │
│  │ 睡眠   │ │ 能量   │     │
│  └──────┘ └──────┘     │
├─────────────────────────┤
│  心率趋势 (近4周)        │
│  ╱╲  ╱╲                │  ← MetricChart 组件
│ ╱  ╲╱  ╲╱╲            │     (uCharts 折线图)
│─────────────────────────│
│  步数趋势 (近4周)        │
│  ██ ██ ███ ██          │  ← uCharts 柱状图
└─────────────────────────┘
```

数据加载顺序：
1. `getTodayMetrics()` → 填充 HealthCard 卡片
2. `getSyncStatus()` → 显示最近同步时间
3. `getBaseline('heart_rate', 30)` → 判断"正常/偏高/偏低"
4. `getTrend('heart_rate', 4)` → MetricChart 折线图
5. `getTrend('step_count', 4)` → MetricChart 柱状图

**技术点**：uCharts 的 `<qiun-data-charts>` 组件接收 `{ categories: [...], series: [{ data: [...] }] }` 格式。需要将 `weeks_data` 转换为这个结构。

### 4.8 `pages/report/index.vue` — 周报页

```
┌─────────────────────────┐
│  健康周报               │
│  ◀ 4月28日-5月4日 ▶    │  ← 左右滑动切换周
├─────────────────────────┤
│                         │
│  📊 本周总览             │
│  本周您的心率稳定在72bpm │  ← WeeklyNarrative 组件
│  步数日均8500步...       │     (LLM 叙事)
│                         │
│  📈 核心指标             │
│  ┌───────────────┐      │
│  │ 心率  72 bpm  →│      │  ← 与上周对比箭头
│  │ 步数  8.5k   →│      │
│  │ 能量  2100   →│      │
│  └───────────────┘      │
│                         │
│  💡 下周建议             │
│  建议增加有氧运动...     │
│                         │
├─────────────────────────┤
│  [生成最新周报]          │  ← 底部按钮
└─────────────────────────┘
```

数据加载：
1. `getReportList()` → 填充周选择器
2. 用户选择某周 → `getReport(weekStart)` → 展示叙事+指标
3. 点击"生成最新周报" → `generateReport()` → 自动跳转到本周

### 4.9 `pages/settings/index.vue` — 设置页

```
┌─────────────────────────┐
│  设置                    │
├─────────────────────────┤
│  API 服务                │
│  ┌──────────────────┐   │
│  │ 服务地址           │   │  ← 可编辑的 BASE_URL
│  │ https://xxx.ngrok │   │
│  └──────────────────┘   │
│  🟢 服务正常             │   ← GET /status 检测
│                         │
│  数据同步                │
│  最近同步: 2026-05-11 08:30
│  已入库: 15,230 条
│  [强制同步]              │
│                         │
│  关于                    │
│  Medical-Health-Agent   │
│  Phase 5 v1.0           │
│  Powered by Qwen3-Max   │
└─────────────────────────┘
```

---

### 4.10 `pages.json` — 路由 & TabBar

```json
{
  "pages": [
    { "path": "pages/chat/index", "style": { "navigationBarTitleText": "健康顾问" } },
    { "path": "pages/dashboard/index", "style": { "navigationBarTitleText": "健康看板" } },
    { "path": "pages/report/index", "style": { "navigationBarTitleText": "健康周报" } },
    { "path": "pages/settings/index", "style": { "navigationBarTitleText": "设置" } }
  ],
  "tabBar": {
    "color": "#999",
    "selectedColor": "#4A90D9",
    "list": [
      { "pagePath": "pages/chat/index", "text": "对话", "iconPath": "static/chat.png", "selectedIconPath": "static/chat-active.png" },
      { "pagePath": "pages/dashboard/index", "text": "看板", "iconPath": "static/dashboard.png", "selectedIconPath": "static/dashboard-active.png" },
      { "pagePath": "pages/report/index", "text": "周报", "iconPath": "static/report.png", "selectedIconPath": "static/report-active.png" },
      { "pagePath": "pages/settings/index", "text": "设置", "iconPath": "static/settings.png", "selectedIconPath": "static/settings-active.png" }
    ]
  }
}
```

---

## 五、组件设计细节

### 5.1 ChatBubble.vue

```
Props: role ('user'|'assistant'), content, time, intent, safety
UI:
  - user:    右对齐，蓝色气泡
  - assistant: 左对齐，白色气泡
  - safety=emergency: 红色边框 + ⚠️ 图标
```

### 5.2 HealthCard.vue

```
Props: icon, label, value, unit, status ('normal'|'high'|'low')
UI:
  - 圆角卡片，左侧 emoji 图标
  - 大字数值 + 单位
  - status 颜色: normal=绿, high=橙, low=蓝
```

### 5.3 MetricChart.vue

```
Props: title, data (categories + series), chartType ('line'|'column')
使用 uCharts <qiun-data-charts>:
  - chartType="line" → 心率/HRV 趋势
  - chartType="column" → 步数/能量柱状图
  - 支持 canvas 2d 渲染（微信新版API）
```

**技术点**：uCharts 的 `categories` 是 X 轴标签数组（如 `['5/1','5/8','5/15','5/22']`），`series[0].data` 是 Y 轴数值数组。趋势 API 返回的 `weeks_data` 需要这样转换：

```javascript
const chartData = {
  categories: trend.weeks_data.map(w => w.week_start.slice(5)),  // "05-01"
  series: [{ name: '周均值', data: trend.weeks_data.map(w => w.avg) }],
}
```

---

## 六、页面间数据流

```
Chat 页面                     Dashboard 页面
   │                              │
   │ POST /chat ──→ session_id    │
   │ 追问时自动携带                │ GET /daily + /baseline + /trend
   │                              │
   │ health_data 追问              │ 指标卡片 + 趋势图
   │ → Router→Perception          │
   │ → 返回今日数据叙事            │
   │                              │
   └──────────┬───────────────────┘
              │
         Report 页面
              │
              │ POST /report/weekly → LLM叙事
              │ GET /report/weekly?week_start=X → 历史
              │ GET /trend → 图表数据
              │
         Settings 页面
              │
              │ GET /status → 同步状态
              │ 编辑 BASE_URL → 切换 ngrok/正式域名
```

---

## 七、开发排期

| Step | 内容 | 预估 |
|------|------|------|
| Step 1 | uni-app 项目初始化（HBuilderX 创建 + pages.json + TabBar） | 0.5天 |
| Step 2 | `api/request.js` + 4个 API 模块 + 4个 Pinia Store | 0.5天 |
| Step 3 | Chat 页面（ChatBubble + SessionList + scroll-view） | 1天 |
| Step 4 | Dashboard 页面（HealthCard + MetricChart + 数据联动） | 1天 |
| Step 5 | Report 页面（WeeklyNarrative + 周切换 + 生成按钮） | 0.5天 |
| Step 6 | Settings 页面 + 全局联调 | 0.5天 |
| **合计** | | **4天** |

---

## 八、待确认问题 & 模糊点

### Q1 — BASE_URL 如何配置？
开发阶段 ngrok URL 频繁变化。方案：Settings 页面提供可编辑的 BASE_URL 输入框，存入 Pinia + `uni.setStorageSync` 持久化。首次启动默认 `localhost:8000`。

### Q2 — 微信小程序域名白名单
微信小程序要求 `request` 合法域名在后台配置。ngrok 的随机域名无法提前配置。**方案**：开发阶段在微信开发者工具中勾选"不校验合法域名"；上线后切到正式域名并配置白名单。

### Q3 — uCharts 在微信小程序 Canvas 2d 的兼容性
微信基础库 2.9.0+ 推荐 Canvas 2d API，旧版 Canvas API 已不维护。uCharts 需配置 `canvas2d: true`。需确认目标微信版本基础库 ≥2.9.0（覆盖率 >99%）。

### Q4 — Dashboard 首次加载慢
进入 Dashboard 需同时调 3-4 个 API（daily + baseline + trend × N）。是否需要骨架屏/loading 占位？**建议**：各模块独立 loading，卡片先出、图表后出。

### Q5 — 周报生成的 LLM 调用
`POST /report/weekly` 内部调 LLM 可能耗时 5-10s。前端需显示"生成中..."并禁用按钮防重复点击。

### Q6 — 离线/弱网体验
小程序在弱网下 `uni.request` 可能超时。**策略**：`api/request.js` 超时 30s + 错误提示 "网络不可达"。不考虑离线缓存（健康数据实时性要求高）。

### Q7 — 暗黑模式
微信小程序支持 `darkmode`。是否做暗黑模式适配？**建议**：首版不做，使用微信默认跟随系统即可。

### Q8 — 推送通知
Phase 4 Q10 提到周报 push 触达。微信小程序用**订阅消息**模板（`wx.requestSubscribeMessage`），用户授权后可推送周报生成通知。需申请模板 ID，首版可跳过。

### Q9 — 图表数据为空时的降级
Dashboard 首次使用无历史数据时，`getTrend` 返回 `{ error: "No data" }`。前端需降级显示"数据收集中，请保持同步"占位图。

### Q10 — H5 版本的适配优先级
uni-app 可编译到 H5，但 `uni.request` 在 H5 端实际是 `XMLHttpRequest`，可能存在跨域问题。**建议**：首版仅微信小程序，H5 后续再适配。
