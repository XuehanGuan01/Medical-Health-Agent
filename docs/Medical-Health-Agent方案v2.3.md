# Medical-Health-Agent 方案 v2.3

> 2026-05-08 | 纯 API 架构 | Qwen3-Max + RAG + LangGraph | ChromaDB | **uni-app 小程序前端**
> 注：Qwen3-Max 额度用完后切 DeepSeek V4

---

## 零、版本变更

| 变更点       | v2.2               | v2.3                            | 理由                        |
| --------- | ------------------ | ------------------------------- | ------------------------- |
| 前端框架      | React Native Expo  | **uni-app (Vue 3)**             | 首选微信小程序，Vue 上手简单，一套代码多端发布 |
| 前端语言      | TypeScript (React) | **Vue 3 + JS/TS**               | Vue SFC 单文件组件，学习曲线更低      |
| 目标平台      | iOS + Android App  | **微信小程序→多端小程序→H5→App**          | 小程序分发零摩擦，用户无需下载安装         |
| Phase 0   | 仅目录创建              | **完整项目搭建 + LLM 连通性测试**          | 基础设施先行，保证后续阶段不卡环境问题       |
| LLM 配置    | langchain-qwen 专用库 | **langchain-openai (OpenAI兼容)** | 所有 provider 统一接口，一键切换     |
| Embedding | DashScope API (入库) | **Phase2 已完成 (ChromaDB)**       | RAG 知识库已构建完毕              |

---

## 一、前端框架对比：uni-app vs React Native (Expo)

### 1.1 对比总表

| 维度          | uni-app (Vue 3)                 | React Native (Expo)                   |
| ----------- | ------------------------------- | ------------------------------------- |
| **语言**      | Vue 3 (JS/TS)                   | React (JSX/TSX)                       |
| **学习曲线**    | ⭐ 低 — Vue 模板语法接近原生 HTML         | ⭐⭐⭐ 中 — 需理解 React 生态 (Hooks/JSX/状态管理) |
| **目标平台**    | 微信/支付宝/百度/字节等 8+ 小程序 + H5 + App | iOS + Android App                     |
| **小程序支持**   | ✅ **核心能力**，条件编译精准适配             | ❌ 不支持                                 |
| **App 性能**  | ⭐⭐⭐ (nvue/uni-app x 可接近原生)      | ⭐⭐⭐⭐ (Bridge → JSI/Fabric 架构)         |
| **H5 支持**   | ✅ 一套代码出 H5                      | ❌ 需单独用 React DOM                      |
| **热更新**     | ✅ HBuilderX / CLI + 小程序热重载      | ✅ Expo Go / OTA updates               |
| **UI 组件**   | uni-ui (官方) + uView + 微信原生组件    | react-native-gifted-chat + NativeBase |
| **生态成熟度**   | ⭐⭐⭐⭐⭐ 国内极度成熟，中文文档完善             | ⭐⭐⭐⭐ 国际成熟，英文为主                        |
| **包体积**     | 小程序 < 2MB (分包) / App ~15MB      | App ~15-20MB                          |
| **调试体验**    | HBuilderX 集成 + 微信开发者工具          | VS Code + Expo Go + Flipper           |
| **Chat UI** | 可复用微信聊天界面风格                     | react-native-gifted-chat (成熟)         |
| **部署分发**    | 小程序审核发布 + H5 直接部署               | App Store + Google Play 审核            |
| **本项目适配度**  | ⭐⭐⭐⭐⭐                           | ⭐⭐⭐                                   |

### 1.2 适用场景分析

**uni-app 更适合本项目的理由**：

1. **分发零摩擦**：医疗健康问答是工具型应用，用户更愿意扫码打开小程序，而非下载 App。微信小程序的「搜一搜 + 扫码 + 分享」三个入口覆盖绝大多数场景。
2. **Vue 3 上手快**：Vue 单文件组件（template + script + style）结构清晰，比 React 的 JSX + Hooks 心智负担低。一人开发时，简单就是生产力。
3. **一套代码多端覆盖**：写完微信小程序 = 同时得到支付宝小程序 + H5 Web 版，后续如需 App 也可以用 uni-app x 或 nvue 编译。
4. **中文医疗场景适配**：uni-app 的富文本、语音输入（微信原生接口）、客服消息等能力对医疗问答场景有直接加成。
5. **中国用户习惯**：目标用户群体（中文医疗咨询）更习惯在微信内使用服务，而非安装独立 App。

**React Native Expo 适用场景**：
- 需要深度调用原生硬件（ARKit、Bluetooth LE、CoreML 等）
- 海外用户为主（Google Play / App Store 分发）
- 团队已有 React 技术栈
- 对动画/手势交互有高要求（如健身跟练 App）

> **结论**：本项目选择 **uni-app (Vue 3)**。首选微信小程序，同步产出 H5 版本。React Native 保留作为备选方案（如果后续需要 Watch 端 App 或深度健康硬件集成时再评估）。

### 1.3 uni-app 技术选型细节

```
框架层:   uni-app 3.x (Vue 3 + Vite)
状态管理: Pinia (Vue 3 官方推荐)
HTTP:     uni.request (小程序端) / axios (H5 端)
UI 组件:  uni-ui (官方) + 自定义组件
构建工具: HBuilderX (推荐) 或 VS Code + uni-app CLI
目标:     微信小程序 (首选) → 支付宝小程序 → H5
```

---

## 二、架构总览 (v2.3)

```
┌──────────────────────────────────────────────────────────────┐
│                   LangGraph 调度层 (StateGraph)                │
│              意图路由 → Self-RAG 检索增强 → 回答生成           │
│                    全部 LLM 调用: Qwen3-Max API               │
│                    配置一键切换: config/llm.py                 │
└──────┬─────────────────┬─────────────────┬───────────────────┘
       │                 │                 │
       ▼                 ▼                 ▼
┌──────────────┐ ┌───────────────┐ ┌───────────────┐
│  感知 Agent   │ │  分析 Agent    │ │  行动 Agent    │
│              │ │               │ │               │
│ Apple Health │ │ 医疗问答       │ │ 对话/建议      │
│ 数据分析     │ │ Self-RAG:     │ │               │
│              │ │ 检索→生成→自检 │ │               │
│ Qwen3-Max    │ │ Qwen3-Max     │ │ Qwen3-Max     │
│ temp=0.1     │ │ temp=0.15      │ │ temp=0.3-0.5  │
└──────┬───────┘ └───────┬───────┘ └───────┬───────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │   共享 RAG 知识库     │
              │   ChromaDB (本地)    │
              │   huatuo 27.6万条    │
              │   Embedding: ✅ 已完成 │
              └─────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    uni-app 小程序前端 (Vue 3)                  │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ 对话页面  │  │ 健康看板  │  │ 周报展示  │  │ 设置页面  │    │
│  │ ChatView │  │Dashboard │  │  Report  │  │ Settings │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       └──────────────┴──────────────┴──────────────┘         │
│                          │ HTTP / WebSocket                   │
└──────────────────────────┼───────────────────────────────────┘
                           │
                           ▼
              ┌─────────────────────┐
              │   FastAPI 后端       │
              │   localhost:8000    │
              └─────────────────────┘
```

---

## 三、数据集 & RAG (Phase 2 已完成 ✅)

华佗医疗对话 27.6 万条 → 清洗 → ChromaDB 向量库 → 已验证。

> 见 `Phase2-医疗RAG知识库构建方案.md` 和 `rag/` 目录下的实际代码。

---

## 四、LLM 配置分离设计 (Phase 0 已实现 ✅)

### 4.1 文件结构

```
config/
├── __init__.py
└── llm.py          # LLM 配置中心 (已实现 — 见下方)
```

### 4.2 设计要点

- **统一 OpenAI 兼容接口**：所有 provider (Qwen/DeepSeek/OpenAI) 均通过 `langchain_openai.ChatOpenAI` 调用，接口完全一致
- **角色化预设**：router/analysis/action/reflect/perception 五种 Agent 角色各有独立的 temperature + max_tokens 配置
- **一键切换**：改 `CURRENT_PROVIDER = "qwen"` → `"deepseek"` 即可切换模型
- **连通性自检**：`python -m config.llm` 直接测试当前 provider 是否可用

### 4.3 切换方式

```bash
# .env 文件配置 API Key
DASHSCOPE_API_KEY=sk-xxx    # Qwen 额度先用
DEEPSEEK_API_KEY=sk-xxx     # 额度用完后切

# 切换模型
# config/llm.py 改一行: CURRENT_PROVIDER = "deepseek"
```

```python
# Agent 中使用 — 不直接写模型名
from config.llm import get_analysis_llm

llm = get_analysis_llm()  # 自动用 CURRENT_PROVIDER 的模型
```

---

## 五、uni-app 前端方案

### 5.1 App 架构

```
frontend/
├── pages/
│   ├── chat/            # 主对话界面
│   │   └── index.vue
│   ├── dashboard/       # 健康数据图表
│   │   └── index.vue
│   ├── report/          # 周报展示
│   │   └── index.vue
│   └── settings/        # LLM 切换 / 通知设置
│       └── index.vue
├── components/
│   ├── ChatBubble.vue   # 聊天气泡
│   ├── HealthCard.vue   # 健康指标卡片
│   └── ChartView.vue    # 图表 (ucharts/ECharts)
├── stores/
│   ├── chat.js          # 对话状态 (Pinia)
│   └── health.js        # 健康数据状态
├── api/
│   ├── request.js       # HTTP 请求封装
│   ├── chat.js          # 对话 API
│   └── health.js        # 健康数据 API
├── static/              # 静态资源
├── App.vue
├── main.js
├── pages.json           # 页面路由配置
├── manifest.json        # 应用配置
└── uni.scss             # 全局样式
```

### 5.2 与 FastAPI 通信

```javascript
// api/request.js
const BASE_URL = 'http://localhost:8000/api/v1'

export function request(options) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: BASE_URL + options.url,
      method: options.method || 'GET',
      data: options.data,
      header: {
        'Content-Type': 'application/json',
        ...options.header,
      },
      success: (res) => {
        if (res.statusCode === 200) resolve(res.data)
        else reject(res)
      },
      fail: reject,
    })
  })
}
```

### 5.3 为什么 Chat UI 不直接用 react-native-gifted-chat

uni-app 的聊天界面方案：

| 方案 | 说明 |
|------|------|
| 微信小程序原生 `<scroll-view>` + 自定义气泡 | 最灵活，医疗场景可定制免责提示、硬边界卡片 |
| uView UI `u-chat` 组件 | 开箱即用，样式美观 |
| 自建 ChatBubble 组件 | 可控性最高，适合 Self-RAG 修正回答的特殊展示 |

---

## 六、Phase 规划总览 (v2.3)

### Phase 0 — 项目搭建 ✅ (Day 1, 已完成)

```
├── 目录结构创建
├── .env / .gitignore / requirements.txt
├── config/llm.py (多 provider + 连通性测试)
├── 前端框架选型确认 (uni-app)
└── Phase0-项目搭建方案.md
```

### Phase 1 — 数据管道 (Week 1-2)

```
├── data_pipeline/ ✅ 代码已完成
├── 待：iOS 端联调 + ngrok 部署
└── 文档：Phase1v2-Apple-Health数据管道实施方案.md
```

### Phase 2 — RAG 知识库 ✅ (已完成)

```
├── rag/build_vectordb.py ✅
├── rag/retriever.py ✅
├── ChromaDB 向量库 ✅
└── 文档：Phase2-医疗RAG知识库构建方案.md
```

### Phase 3 — Agent 系统 (Week 3-5) ⭐ 核心

```
├── agents/state.py (AgentState 定义)
├── agents/router.py (意图路由)
├── agents/analysis.py (Self-RAG: retrieve→generate→reflect→revise)
├── agents/perception.py (健康数据分析)
├── agents/action.py (对话/建议生成)
├── agents/graph.py (LangGraph StateGraph 编译)
├── agents/boundary.py (硬边界拒答)
└── prompts/ (所有 prompt 模板)
```

### Phase 4 — 长期记忆 (Week 5-6)

```
├── memory/vector_store.py (ChromaDB 摘要记忆)
├── memory/weekly_summary.py (周报生成)
└── memory/trend.py (趋势查询)
```

### Phase 5 — uni-app 小程序前端 (Week 6-8)

```
├── uni-app 项目初始化 (HBuilderX / CLI)
├── pages/chat/ — 对话界面
├── pages/dashboard/ — 健康图表
├── pages/settings/ — 设置
└── 与 FastAPI 后端联调
```

### Phase 6 — 集成测试 (Week 8-10)

```
├── 端到端测试
├── RAG 检索质量评估
├── Self-RAG 修正率统计
├── 小程序审核提交
└── 性能优化
```

---

## 七、成本估算

| 阶段 | 费用来源 | 金额 |
|------|----------|------|
| Phase 0 | 无 | 0 元 |
| Phase 1 | ngrok 免费版 / Cloudflare Tunnel | 0 元 |
| Phase 2 | ✅ 已完成 (Embedding API ~¥6) | 已完成 |
| Phase 3 开发 | Qwen3-Max API 测试调用 | < 10 元 (有额度) |
| Phase 4-5 | Qwen3-Max API 测试调用 | < 10 元 (有额度) |
| 上线后 | Qwen3-Max API (~100次/天) | ~0 元 (额度覆盖) |
| 上线后 (切 DeepSeek) | DeepSeek V4 Flash (~100次/天) | ~26 元/月 |
| 小程序 | 微信认证 300 元/年 (可选) | 0-300 元/年 |

---

## 八、当前目录结构 (Phase 0 完成后)

```
Medical-Health-Agent/
├── agents/                    # Phase 3 Agent 系统 (待开发)
│   └── __init__.py
├── config/                    # 全局配置
│   ├── __init__.py
│   └── llm.py                 # ✅ LLM 配置中心 (多 provider + 连通性测试)
├── data_pipeline/             # Phase 1 数据管道 ✅
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── database.py
│   ├── webhook_server.py
│   ├── aggregator.py
│   └── test_data.py
├── rag/                       # Phase 2 RAG 知识库 ✅
│   ├── __init__.py
│   ├── build_vectordb.py
│   ├── retriever.py
│   ├── analyze_datasets.py
│   └── data/
├── memory/                    # Phase 4 长期记忆 (待开发)
│   └── __init__.py
├── prompts/                   # Prompt 模板 (待开发)
│   └── __init__.py
├── frontend/                  # Phase 5 uni-app 小程序 (待开发)
│   └── README.md
├── tests/                     # 测试 (待开发)
│   └── __init__.py
├── docs/                      # 外部参考文档
├── data/                      # 运行时数据 (SQLite/ChromaDB 持久化)
├── .env.example               # ✅ 环境变量模板
├── .gitignore                 # ✅
├── requirements.txt           # ✅ Python 依赖清单
├── Medical-Health-Agent方案v2.3.md      # ★ 当前版本
├── Phase0-项目搭建方案.md
├── Phase1v2-Apple-Health数据管道实施方案.md
├── Phase2-医疗RAG知识库构建方案.md
├── Medical-Health-Agent方案v1.1.md      # 保留 (架构起源)
├── Medical-Health-Agent方案v1.2-本地RAG方案分析.md
├── Medical-Health-Agent方案v1.3-MedicalGPT训练部署方案.md
├── Medical-Health-Agent方案v2.1.md
└── Medical-Health-Agent方案v2.2.md
```

---

## 九、附录：未来迭代方案

### A. 对话历史持久化方案 (v3)

| 方案 | 实现 | 优点 | 缺点 |
|------|------|------|------|
| A1: SQLite 存聊天记录 | `(session_id, role, content, timestamp)` | 简单 | 无语义检索 |
| A2: ChromaDB 对话记忆 | embed → ChromaDB 检索相关历史 | 语义检索 | 额外存储 |
| A3: LangGraph SqliteSaver | `graph.compile(checkpointer=SqliteSaver(conn))` | 框架原生 | 灵活性低 |

**v3 建议**：A1 + A2 混合。

### B. 安全审查制度方案 (v3)

| 方案 | 实现 | 开销 | 效果 |
|------|------|------|------|
| B1: 关键词硬过滤 | regex 检测 → 拒答 | 0 延迟 | 60% |
| B2: Self-RAG reflect | 当前已设计 | 1 次 API | 85% |
| B3: 独立审查模型 | 另一 LLM 专门审查 | 1 次 API | 95% |
| B4: 内容安全 API | 阿里云/腾讯云 API | ~0.01 元/次 | 98% |

**v3 建议**：B1 (实时) + B2 (已有) → 敏感场景 B4 兜底。

### C. 小程序拓展路线

| 阶段 | 平台 | 说明 |
|------|------|------|
| Phase 5 | 微信小程序 | 首选，用户量最大 |
| v3.0 | 支付宝小程序 | 复用 90% 代码，条件编译适配 |
| v3.1 | H5 Web 版 | 一套代码直接编译，部署到 Vercel/CloudBase |
| v3.2 | App (iOS/Android) | uni-app x 或 nvue 编译原生 App |

---

> **下一步**：Phase 0 项目搭建完成后，进入 Phase 3 Agent 系统开发。
