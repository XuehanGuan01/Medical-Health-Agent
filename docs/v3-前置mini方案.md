# v3 前置 mini 方案

> 产出日期：2026-05-08
> 用途：为下一个 Max effort agent 提供结构化输入，产出完整“方案 v3”
> 基于：v2.3（当前最新版）+ 全部历史方案文档 + 实际代码状态

---

## 诊断：导致“思路受阻、框架缺失”的 6 个核心问题

| #   | 问题                       | 具体表现                                                                                                              | 影响                                      |
| --- | ------------------------ | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| 1   | **Phase 定义随版本漂移**        | Phase 3 在 v1.1 中=MedicalGPT部署，v2.1→v2.3=Agent系统；Phase 4 在 v1.x=长期记忆，v2.1=长期记忆，v2.3=长期记忆但时间线不同                     | 无法统一沟通“Phase X 做到哪了”                    |
| 2   | **v1.x→v2.x 路径分叉无决策记录**  | v1.x 核心思想=“本地模型兜底+云端主推理”，v2.x=完全移除本地模型；从未有正式文档解释为什么放弃、什么条件下可能恢复                                                   | 后续讨论容易回到已否决方向                           |
| 3   | **已完成 Phase 的“可消费性”未定义** | Phase 1 代码已完成但待 iOS 联调；Phase 2 已完成。但 Phase 3 要怎样消费 Phase 1/2 的输出——接口契约、数据格式、调用方式——从未明确                            | Phase 3 无法直接开工，需要先“摸索”前两个 Phase 到底产出了什么 |
| 4   | **文档与代码脱节**              | Phase 1 有两个方案文档版本（v1, v2）但只有一套代码；Phase 2 方案文档与实际 `rag/` 代码的一致性未验证；v2.3 声称 Phase 0 完成但 `agents/` 只有空 `__init__.py` | 文档不能作为执行依据                              |
| 5   | **方案版本间缺少“决策日志”**        | v2.1→v2.2→v2.3 的变更有记录，但 v1.x→v2.x 的巨大跳跃（放弃本地模型、放弃SFT训练、放弃Gradio前端）无单独记录                                           | 新人（或未来的自己）无法理解为什么选了当前方案                 |
| 6   | **缺少稳定的总体框架描述**          | 每个版本都是自成一体，但没有一个稳定的文档定义：系统是什么、核心能力清单、模块边界、Phase如何与模块对应                                                            | 每次迭代都在重新解释同一件事                          |

---

## Part A：阶段重定义（Phase 定义）

以下 Phase 定义**覆盖并取代**所有旧版本文档中的 Phase 划分。后续所有执行以此为准。

### Phase 0 — 基础设施 ✅ 已完成

| 维度 | 内容 |
|------|------|
| **目标** | 项目目录、依赖、LLM 配置与连通性验证，保证后续 Phase 不回头补环境 |
| **主要任务** | 1. 目录结构创建 2. `.env` / `.gitignore` / `requirements.txt` 3. `config/llm.py` 多 provider 配置中心 4. LLM 连通性自检（`python -m config.llm`） 5. 前端框架选型确认（uni-app） |
| **输入依赖** | 无 |
| **输出产物** | `config/llm.py`（可用）、`config/__init__.py`、`requirements.txt`、`.env.example`、各模块 `__init__.py` |
| **当前状态** | ✅ 已完成。`config/llm.py` 当前默认 provider=deepseek，5 种 Agent 角色预设就绪 |
| **验收标准** | `python -m config.llm` → ✅ 连通成功 |

### Phase 1 — 数据管道 ⚠️ 代码完成，待 iOS 联调

| 维度 | 内容 |
|------|------|
| **目标** | 实现 Apple Health 数据从 iPhone → 本地 SQLite 的自动同步 + 日聚合 + 基线计算 |
| **主要任务** | 1. FastAPI Webhook 接收端（已完成） 2. Pydantic 校验 + SQLAlchemy 持久化（已完成） 3. 日聚合 + 30天基线计算（已完成） 4. **待做**：iOS 端 Health Auto Export 配置 + ngrok 联通 5. **待做**：真实数据端到端验证 |
| **输入依赖** | Phase 0 |
| **输出产物** | `data_pipeline/` 全部 6 个 `.py` 文件、`data/health.db`（SQLite）、查询 API（`/daily`, `/raw`, `/status`, `/baseline`） |
| **当前状态** | ⚠️ 代码已完成，但 **从未通过真实 iOS 数据验证**。Phase 1v2 文档中的官方 JSON 格式校正（心率字段 `Min`/`Avg`/`Max` 首字母大写、血氧字段名应为 `blood_oxygen_saturation` 等）也**未应用到代码中** |
| **验收标准** | 1. iPhone Health Auto Export → ngrok → FastAPI 数据通路完整 2. `GET /status` 返回真实数据 >0 条 3. 附录 D（Phase1v2）的 JSON 格式校正已应用到代码 |

### Phase 2 — RAG 知识库 ✅ 已完成

| 维度       | 内容                                                                                                                     |
| -------- | ---------------------------------------------------------------------------------------------------------------------- |
| **目标**   | 构建华佗医疗对话 ChromaDB 向量库，为 Phase 3 分析 Agent 提供检索增强                                                                        |
| **主要任务** | 1. 华佗数据集加载+清洗+去重（已完成） 2. Embedding + ChromaDB 入库（已完成） 3. `MedicalRetriever` 检索接口（已完成） 4. 检索质量评估（已完成）                   |
| **输入依赖** | Phase 0（LLM配置）、华佗数据集                                                                                                   |
| **输出产物** | `rag/build_vectordb.py`、`rag/retriever.py`、`data/chroma/`（持久化向量库）、`MedicalRetriever.search()` + `.format_context()` 接口 |
| **当前状态** | ✅ 已完成。27.6万条清洗后入库，检索延迟 <150ms                                                                                          |
| **验收标准** | `from rag.retriever import MedicalRetriever` → `search("小孩发烧39度怎么办？", k=3)` → 返回相关 QA                                  |

### Phase 3 — Agent 系统 ⭐ 核心（当前卡点）

| 维度 | 内容 |
|------|------|
| **目标** | 用 LangGraph StateGraph 构建完整 Agent 调度系统，实现“意图路由 → Self-RAG → 回答生成”闭环 |
| **主要任务** | 按依赖顺序：1. `agents/state.py` — AgentState 定义 2. `prompts/` — 全部 prompt 模板 3. `agents/boundary.py` — 硬边界拒答 4. `agents/router.py` — 意图路由 5. `agents/analysis.py` — Self-RAG（检索→生成→自检→修正） 6. `agents/perception.py` — 健康数据分析（消费 Phase 1 输出） 7. `agents/action.py` — 对话/建议生成 8. `agents/graph.py` — StateGraph 编译 + FastAPI 端点 |
| **输入依赖** | Phase 0（`config/llm.py` LLM 实例）、Phase 2（`rag/retriever.py` 检索接口）、Phase 1（`data_pipeline/aggregator.py` 基线计算 — 可选，初期可用模拟数据） |
| **输出产物** | `agents/` 目录下全部 `.py` 文件、`prompts/` 目录下 prompt 模板、FastAPI `/api/v1/chat` 端点 |
| **当前状态** | ❌ 未开始。`agents/` 和 `prompts/` 仅有空 `__init__.py` |
| **验收标准** | 见 Part C |

### Phase 4 — 长期记忆 & 健康趋势

| 维度 | 内容 |
|------|------|
| **目标** | 对话历史持久化 + 周报生成 + 健康趋势查询 |
| **主要任务** | 1. 对话历史 SQLite 存储 + ChromaDB 语义记忆 2. 周报生成（LLM叙事 + embedding存储） 3. 健康趋势查询（多周对比） |
| **输入依赖** | Phase 3（Agent 系统可用、有对话产出） |
| **输出产物** | `memory/vector_store.py`、`memory/weekly_summary.py`、`memory/trend.py` |
| **当前状态** | ❌ 未开始 |
| **验收标准** | 1. 多轮对话历史可跨会话恢复 2. `generate_weekly_report()` 产出可读周报 3. 趋势查询返回 4 周+ 对比数据 |

### Phase 5 — uni-app 小程序前端

| 维度 | 内容 |
|------|------|
| **目标** | 构建微信小程序前端，提供对话、健康看板、周报展示、设置四大页面 |
| **主要任务** | 1. uni-app 项目初始化（HBuilderX 或 CLI） 2. 对话页面（ChatView） 3. 健康看板（Dashboard） 4. 周报展示（Report） 5. 设置页面（Settings） 6. 与 FastAPI 后端联调 |
| **输入依赖** | Phase 3（FastAPI `/api/v1/chat` 等端点可用） |
| **输出产物** | `frontend/` 目录下完整 uni-app 项目（Vue 3 + Pinia） |
| **当前状态** | ❌ 未开始。`frontend/` 仅有 `README.md` |
| **验收标准** | 1. 微信开发者工具中可扫码预览 2. 对话页可与后端完成一轮问答 3. 健康看板可展示模拟数据 |

### Phase 6 — 集成测试 & 上线

| 维度 | 内容 |
|------|------|
| **目标** | 端到端验证 + 质量评估 + 小程序提交审核 |
| **主要任务** | 1. 意图路由准确率测试（50条标注样本） 2. RAG 检索质量评估（50条医学问题） 3. Self-RAG 修正率统计 4. 紧急词触发测试 5. 性能优化（检索延迟、API 超时） 6. 微信小程序审核提交 |
| **输入依赖** | Phase 3 + Phase 4 + Phase 5 |
| **输出产物** | 测试报告、性能基线数据、小程序审核提交 |
| **当前状态** | ❌ 未开始 |

---

## Part B：整体 Workflow 图（文字版）

```
                    ┌─────────────────────────────────────┐
                    │           Phase 0: 基础设施           │
                    │   LLM配置 + 目录 + 依赖 + 连通性      │
                    └──────────────┬──────────────────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            │                      │                      │
            ▼                      ▼                      │
  ┌─────────────────┐    ┌─────────────────┐              │
  │  Phase 1: 数据管道 │    │ Phase 2: RAG知识库│           │
  │  Apple Health →   │    │  华佗 → ChromaDB │              │
  │  SQLite + 聚合     │    │  检索接口         │              │
  └────────┬──────────┘    └────────┬──────────┘           │
           │                        │                      │
           │   ┌────────────────────┘                      │
           │   │                                           │
           ▼   ▼                                           │
  ┌─────────────────────────────────┐                      │
  │      Phase 3: Agent 系统 ⭐      │  ← 当前卡点           │
  │  LangGraph StateGraph           │                      │
  │  意图路由 → Self-RAG → 回答      │                      │
  │  消费 Phase1 数据 + Phase2 检索   │                      │
  └──────────────┬──────────────────┘                      │
                 │                                         │
     ┌───────────┼───────────┐                             │
     │           │           │                             │
     ▼           ▼           ▼                             │
  ┌──────┐  ┌──────┐  ┌──────────┐                         │
  │Ph4记忆│  │Ph5前端│  │Ph6集成测试│  ← Ph4/Ph5 可并行      │
  └──┬───┘  └──┬───┘  └────┬─────┘                         │
     │         │           │                                │
     └─────────┴───────────┘                                │
                 │                                          │
                 ▼                                          │
           ┌──────────┐                                     │
           │  上线运行  │                                     │
           └──────────┘                                     │
```

**关键流转关系**：

1. Phase 0 → Phase 1 / Phase 2：**并行启动**（无相互依赖）
2. Phase 1 + Phase 2 → Phase 3：**汇聚依赖**（Phase 3 消费两者的接口）
3. Phase 3 → Phase 4 / Phase 5：**并行启动**（Phase 4 和 Phase 5 都依赖 Phase 3 的 API 端点，但彼此独立）
4. Phase 5 中，建议先做一个**纯本地模拟数据模式**的前端，不等待 Phase 3 完成后端，验证 UI 交互可用性
5. Phase 4 + Phase 5 → Phase 6：汇聚到集成测试

---

## Part C：落地进度控制建议

### C.1 每个 Phase 的检查点与验收标准

#### Phase 1 检查点

| 检查点 | 验收方式 | 阻塞下一阶段？ |
|--------|---------|--------------|
| CP1.1 真实 iOS 数据到达 | `GET /api/v1/health/status` 返回 `total_raw_samples > 0` | 否（Phase 3 初期可用模拟数据） |
| CP1.2 日聚合正确 | 查询 `/daily?date=today` 返回各指标 avg/min/max/stddev | 否 |
| CP1.3 JSON 格式校正应用 | 代码按 Phase1v2 附录 D 修正心率字段名、血氧字段名、睡眠阶段枚举 | 否（但建议 Phase 3 启动前完成） |
| CP1.4 基线计算可用 | `GET /baseline?metric_type=heart_rate&days=7` 返回有效基线 | 是（Phase 3 感知Agent 依赖此接口） |

#### Phase 2 检查点

| 检查点 | 验收方式 | 阻塞下一阶段？ |
|--------|---------|--------------|
| CP2.1 检索命中率 | 20 条测试问题，Top-5 至少 1 条相关 ≥ 90% | 是 |
| CP2.2 检索延迟 | 100 次查询均值 < 200ms（含 API 嵌入） | 否 |
| CP2.3 format_context() 可用 | LLM 能基于 context 生成有据可查的回答 | 是 |

#### Phase 3 检查点（⭐ 最关键）

| 检查点 | 验收方式 |
|--------|---------|
| CP3.1 AgentState 定义 | 代码可 import，字段覆盖消息列表、意图、检索结果、健康数据 |
| CP3.2 意图路由 | 输入“我今天心率有点高” → 路由到 perception；输入“小孩发烧怎么办” → 路由到 analysis |
| CP3.3 RAG 检索集成 | analysis 节点能调 `MedicalRetriever.search()` 并取回结果 |
| CP3.4 Self-RAG 闭环 | reflect 节点能评估回答质量，revise 节点能修正后输出 |
| CP3.5 硬边界 | 输入“我胸痛怎么办” → 触发 emergency handler / 拒答模板 |
| CP3.6 健康数据感知 | perception 节点能读取 daily_metrics + baseline 生成结构化摘要 |
| CP3.7 端到端对话 | `POST /api/v1/chat {"query": "小孩发烧39度怎么办？"}` → 返回含 RAG 引用的回答 |
| CP3.8 Self-RAG 修正率 | 对 20 条测试问题统计修正率，目标 >80% 修正后质量提升 |

#### Phase 4 检查点

| 检查点 | 验收方式 |
|--------|---------|
| CP4.1 对话历史持久化 | 重启服务后，同一 session_id 能恢复历史对话 |
| CP4.2 周报生成 | 基于 7 天聚合数据生成可读叙事（人工评估） |
| CP4.3 趋势查询 | “最近一个月 HRV 趋势如何” → 返回结构化对比 |

#### Phase 5 检查点

| 检查点 | 验收方式 |
|--------|---------|
| CP5.1 项目可编译 | `npm run dev:mp-weixin` 可在微信开发者工具中打开 |
| CP5.2 对话连通 | 对话页输入问题 → 调通 FastAPI → 展示回答 |
| CP5.3 健康看板 | 展示心率/睡眠/步数图表（可用模拟数据） |
| CP5.4 各页面路由正常 | Chat / Dashboard / Report / Settings 四个 Tab 切换正常 |

#### Phase 6 检查点

| 检查点 | 验收方式 |
|--------|---------|
| CP6.1 意图路由准确率 | 50 条标注样本，准确率 ≥ 85% |
| CP6.2 RAG 召回率 | 50 条医学问题 Top-3 召回率 ≥ 80% |
| CP6.3 紧急词触发率 | 10 条紧急描述，触发率 100% |
| CP6.4 性能基线 | 端到端延迟 P95 < 5s（含 API） |

### C.2 不同步预警信号

如果在执行过程中看到以下信号，说明 Phase 间出现不同步：

| 预警信号 | 含义 | 应对 |
|---------|------|------|
| Phase 3 开发时频繁返回 Phase 1 修代码 | Phase 1 的接口契约未被 Phase 3 认可 | 立即暂停 Phase 3，先补齐 Phase 1 → Phase 3 的接口文档 |
| Phase 3 开发时发现 RAG 检索结果不满足需求 | Phase 2 的验收标准（CP2.1）未严格执行 | 回到 Phase 2 补检索质量评估 |
| Phase 5 联调时发现 API 端点缺失 | Phase 3 的输出产物清单不完整 | 在 Phase 3 启动前就确定 `/api/v1/chat` 等端点的 Request/Response schema |
| 某一 Phase 超过预计时间 2 倍仍未完成 | Phase 范围过大或依赖未就绪 | 拆分为子 Phase，先交付 MVP 再迭代 |

---

## Part D：给下一个 Agent 的执行指令

### D.1 你的任务

基于本 mini 方案 + 项目目录下所有 `.md` 文件 + 实际代码，**产出“Medical-Health-Agent 方案 v3”**。

### D.2 方案 v3 必须包含的章节

以下为**必需章节清单**，顺序可微调：

1. **决策演进史**（1 页以内）
   - 从 v1.1 → v2.3 的关键决策转折点（本地模型放弃、前端框架切换、LLM 切换）
   - 每个转折的“当时理由”和“当前状态”
   - **目的**：消除未来“为什么选了A而不是B”的困扰

2. **总体框架**
   - 系统是什么（一句话定义）
   - 核心能力清单（6-8 条，对应 Phase 1-6）
   - 模块划分图（文字版 ASCII 即可，参考 v2.3 §二）
   - 各模块职责速查表

3. **技术栈确定**
   - 后端：FastAPI + LangGraph + LangChain + SQLite + ChromaDB
   - LLM：当前 DeepSeek（config/llm.py 一键切换）
   - Embedding：Phase 2 实际使用的方案 `[需从代码确认]`
   - 前端：uni-app (Vue 3 + Pinia)，目标微信小程序
   - 内网穿透：ngrok（Phase 1）→ Cloudflare Tunnel（后续）

4. **分阶段详细计划**（Phase 0 → Phase 6）
   - 每个 Phase：目标 / 任务清单 / 输入 / 输出 / 预估工期 / 当前状态
   - Phase 状态标记：✅已完成 / ⚠️部分完成 / ❌未开始
   - **对于 Phase 1 和 Phase 2**，明确列出“Phase 3 消费这些产物的具体方式”（即接口契约）

5. **Phase 3 详细设计**（当前卡点，需要最详细）
   - AgentState 字段定义
   - LangGraph 拓扑（节点 + 条件边）
   - 每个节点的 Prompt 模板概要
   - Self-RAG 闭环的 podmínky（何时 pass / retry / reject）
   - 硬边界拒答规则
   - 与 Phase 1 和 Phase 2 的接口调用方式
   - 开发顺序（文件级）

6. **数据流详解**
   - 三条主要数据流的端到端路径：
     - A) Apple Health 数据：iPhone → ngrok → FastAPI → SQLite → perception Agent
     - B) 医疗问答：用户问题 → router → RAG检索 → analysis Agent → reflect → action → 用户
     - C) 周报生成：daily_metrics (7天) → LLM叙事 → embedding → ChromaDB记忆

7. **API 设计**
   - 列出所有 FastAPI 端点（包括已有的和待开发的）
   - 每个端点的 Method / Path / Request Body / Response Body 概要

8. **里程碑与时间线**
   - 以 Phase 为单位的时间线（用 v2.3 §六的时间估算为基线）
   - 关键里程碑：首个真实健康数据到达、首次 Self-RAG 闭环、首个端到端对话、小程序首次扫码可用

9. **风险管理**
   - 技术风险（API 不可用、RAG 质量不达标、小程序审核被拒等）
   - 应对措施

10. **附录**
    - A：所有 Phase 文档和方案文档的索引（含版本号和用途说明）
    - B：已知待确认事项（Phase1v2 附录 C 中标注 `⚠️ 待真机验证` 的条目）
    - C：“方案 v3 的版本变更”相对于 v2.3 的 delta

### D.3 执行时的重要提醒

- **验证代码，不要只读文档**：Phase 1/Phase 2 的实际代码可能和文档描述有偏差。打开 `.py` 文件确认接口签名、参数名、返回值结构。
- **Phase 1 的代码需要特别审查**：Phase1v2 文档附录 D 列出了多个 JSON 格式校正项（心率字段首字母大写、血氧字段名等），检查这些是否已应用到 `models.py`。如果未应用，在方案 v3 中标注为 `⚠️ 待修复`。
- **确定 Embedding 实际方案**：v2.2 讨论过 DashScope API vs 本地 bge-small-zh，v2.3 说 Phase 2 已完成但未明确最终用了哪个。打开 `rag/retriever.py` 确认 `MedicalRetriever.__init__()` 中实际初始化的 embedder。
- **config/llm.py 当前状态**：CURRENT_PROVIDER 已切到 `"deepseek"`，与 v2.3 文档中说的“先用 Qwen3-Max 额度”有差异。在方案 v3 中同步此信息。
- **不要引入新的技术选型**：方案 v3 是整合和明确化已有决策，不是再开新分支。如果发现已有决策有矛盾，标注出来让用户裁决，不要自行选择。
- **标注信息可信度**：对每个关键信息点标注来源——是来自文档（哪个版本）、代码（哪个文件）、还是推断。例如：`[来源: config/llm.py L27]`、`[推断: Phase1v2附录D未在代码中看到对应修改]`。

### D.4 产出格式

- 单个 Markdown 文件：`Medical-Health-Agent方案v3.md`
- 放置于项目根目录
- 保持与 v2.3 类似的文档风格（表格清晰、代码块有语法高亮、ASCII 架构图）
