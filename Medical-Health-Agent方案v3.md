# Medical-Health-Agent 方案 v3

> 2026-05-09 | 纯 API 架构 | Qwen3-Max + Self-RAG + LangGraph | ChromaDB | uni-app 微信小程序
> 基于 v2.3 + 全部历史方案 + 实际代码验证

---

## 一、决策演进史

| 版本 | 日期 | 核心变化 | 理由 | 当前状态 |
|------|------|---------|------|---------|
| v1.1 | 2026-05 | 三层Agent + 本地Qwen3-4B兜底 + 云端DeepSeek | 6GB显存是瓶颈，本地模型做兜底 | 已废弃 |
| v1.2 | 2026-05 | 硬件实测，确认CPU Embedding + GPU推理分工 | RTX 3060 6GB显存精算 | 架构参考保留 |
| v1.3 | 2026-05 | MedicalGPT云端训练全流程方案 | SFT+OPD+量化部署 | **已放弃** — 云端训练时间/金钱成本过高 |
| **v2.1** | 2026-05-07 | **完全移除本地模型**，纯API架构 | 租用A100训练9h≈55元，且本地4B医疗问答质量不如API+RAG | 架构基线 |
| v2.2 | 2026-05-07 | Self-RAG机制、切换Qwen3-Max、前端React Native Expo | 有Qwen额度；Self-RAG防幻觉 | 已被v2.3取代 |
| **v2.3** | 2026-05-08 | 前端改uni-app(Vue 3)，目标微信小程序 | 小程序分发零摩擦，Vue学习曲线低 | ★ 当前主方案 |

> **关键决策记录**：v1.x→v2.x放弃本地模型的原因——花了一天时间尝试微调与蒸馏流程后，发现租用算力进行SFT+OPD的时间成本（8-12h训练）和金钱成本（~35元）对于个人项目偏高，且训练出的4B模型医疗问答质量仍然不如「API强模型+RAG检索」的组合。因此v2.x起确立**纯API路线**：LLM推理全部走云端API，本地仅保留RAG知识库的Embedding和向量检索。

---

## 二、总体框架

### 2.1 系统定义

**Medical-Health-Agent** 是一个个人AI健康管家系统：接收Apple Health生理数据，结合华佗医疗知识库(RAG)，通过LangGraph多Agent协作提供健康数据分析与医疗问答服务。前端为微信小程序，后端为FastAPI。

### 2.2 核心能力清单

| #   | 能力                       | 对应 Phase | 状态     |
| --- | ------------------------ | -------- | ------ |
| 1   | Apple Health 数据自动同步 + 聚合 | Phase 1  | ✅ 已完成  |
| 2   | 华佗医疗知识 RAG 检索            | Phase 2  | ✅ 已完成  |
| 3   | 意图路由 + Self-RAG 医疗问答     | Phase 3  | ❌ 当前卡点 |
| 4   | 健康数据分析（感知Agent）          | Phase 3  | ❌      |
| 5   | 硬边界拒答（安全机制）              | Phase 3  | ❌      |
| 6   | 对话历史 + 周报 + 趋势追踪         | Phase 4  | ❌      |
| 7   | 微信小程序前端（对话/看板/周报）        | Phase 5  | ❌      |
| 8   | 多Provider LLM一键切换        | Phase 0  | ✅      |

### 2.3 模块划分

```
┌──────────────────────────────────────────────────────────────────┐
│                     LangGraph 调度层 (Phase 3)                     │
│           意图路由 → Self-RAG(检索→生成→自检→修正) → 回答           │
│                                                                  │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Router   │  │  Analysis    │  │Perception│  │  Action   │    │
│  │ 意图路由  │  │ Self-RAG问答  │  │ 健康分析  │  │ 对话生成  │    │
│  │temp=0.0  │  │ temp=0.15    │  │ temp=0.1 │  │ temp=0.5  │    │
│  └────┬─────┘  └──────┬───────┘  └────┬─────┘  └─────┬─────┘    │
│       │               │               │              │           │
│       └───────────────┴───────┬───────┴──────────────┘           │
│                               │                                   │
│              ┌────────────────┴────────────────┐                  │
│              ▼                                 ▼                  │
│  ┌───────────────────────┐     ┌──────────────────────────┐      │
│  │  Phase 2: RAG 知识库   │     │  Phase 1: 健康数据管道     │      │
│  │  ChromaDB (本地)       │     │  SQLite + 日聚合 + 基线    │      │
│  │  huatuo 27.6万条 ✅    │     │  data_pipeline/ ✅        │      │
│  └───────────────────────┘     └──────────────────────────┘      │
└──────────────────────────────────────────────────────────────────┘
                                 │ HTTP
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                  FastAPI 后端 (localhost:8000)                     │
│  /api/v1/chat  |  /api/v1/health/*  |  /api/v1/memory/*          │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTP
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│               uni-app 小程序前端 (Vue 3 + Pinia)                   │
│  ChatView (对话) | Dashboard (健康看板) | Report (周报) | Settings│
└──────────────────────────────────────────────────────────────────┘
```

### 2.4 模块职责速查

| 目录 | Phase | 职责 | 核心接口 |
|------|-------|------|---------|
| `config/` | 0 ✅ | LLM配置中心，多provider一键切换 | `get_llm(role)` → ChatOpenAI实例 |
| `data_pipeline/` | 1 ✅ | Apple Health数据接收+聚合+基线 | `GET /api/v1/health/*`（5个端点） |
| `rag/` | 2 ✅ | 医疗知识检索 | `MedicalRetriever.search(query, k)` |
| `agents/` | 3 ❌ | LangGraph Agent调度 | `graph.invoke(AgentState)` |
| `memory/` | 4 ❌ | 对话记忆+周报+趋势 | [待开发] |
| `prompts/` | 3 ❌ | Prompt模板管理 | [待开发] |
| `frontend/` | 5 ❌ | uni-app小程序 | [待开发] |

---

## 三、技术栈确定

| 层级 | 技术 | 版本 | 用途 |
|------|------|------|------|
| Agent 编排 | LangGraph | ≥0.2.0 | StateGraph 构建，条件路由 |
| LLM 调用 | langchain-openai (OpenAI兼容) | ≥0.3.0 | 统一接口，一键切换provider |
| 主力 LLM | **Qwen3-Max** (DashScope) | — | 额度优先消耗，额度用完切DeepSeek |
| 备选 LLM | DeepSeek V4 Flash | — | Qwen额度用完后切换 |
| Embedding | **DashScope text-embedding-v4** (API) | — | 1024维，入库~¥6，查询~100ms |
| 向量库 | ChromaDB (persistent) | ≥0.5.0 | HNSW索引，自动持久化 |
| 后端 | FastAPI | ≥0.115 | API服务 |
| 数据存储 | SQLite | — | 健康数据 + 对话历史 |
| 前端框架 | **uni-app (Vue 3 + Vite)** | 3.x | 微信小程序→多端 |
| 状态管理 | Pinia | — | Vue 3 官方推荐 |
| 内网穿透 | ngrok 免费版 → Cloudflare Tunnel | — | Phase 1快速落地 → 长期稳定 |
| Python | 3.11+ | — | |

---

## 四、分阶段详细计划

### Phase 0 — 基础设施 ✅ 已完成

| 维度 | 内容 |
|------|------|
| **目标** | 项目目录、依赖安装、LLM配置与连通性验证 |
| **任务清单** | ①目录结构 ②`.env`/`.gitignore`/`requirements.txt` ③`config/llm.py` ④LLM连通性自检 ⑤前端框架选型确认 |
| **输入** | 无 |
| **输出** | `config/llm.py`（5种Agent角色预设+多provider+连通性测试） |
| **状态** | ✅ 已完成。`python -m config.llm` 可验证连通性 |
| **预估工期** | Day 1（已完成） |

### Phase 1 — 数据管道 ✅ 已完成

| 维度 | 内容 |
|------|------|
| **目标** | iPhone Apple Health → ngrok → FastAPI → SQLite → 日聚合 + 30天基线 |
| **任务清单** | ①FastAPI Webhook接收端 ✅ ②Pydantic校验+SQLAlchemy持久化 ✅ ③日聚合+基线计算 ✅ ④ngrok部署 ✅ ⑤iPhone + 真机数据端到端验证 ✅ |
| **数据规模** | 一年 Apple Health 历史数据入库，含心率/步数/HRV/呼吸/步行/能量等 20+ 类指标 |
| **输入** | Phase 0 |
| **输出** | `data_pipeline/`下6个`.py`文件（已升级至v2）；5个API端点(`/sync`, `/daily`, `/raw`, `/baseline`, `/status`)；测试手册`docs/Phase1-测试手册.md` |
| **状态** | ✅ 已完成。2026-05-09 一年真实数据入库并通过端到端验证 |
| **预估工期** | 已投入1-2周 |

#### Phase 1 代码升级完成（v1 → v2）

| 变更 | 说明 |
|------|------|
| `datetime.utcnow()` → `datetime.now(timezone.utc)` | Python 3.12+ 兼容 |
| `normalize_date` 实际执行 ISO 8601 转换 | iOS 日期格式兼容 |
| 新增 `GET /api/v1/health/baseline` 端点 | Phase 3 感知Agent直接调用 |
| `compute_baseline` 返回 `upper_bound`/`lower_bound` | API 字段名规范化 |
| 心率字段 `Min`/`Avg`/`Max` 别名 | Pydantic `populate_by_name=True`，兼容官方大写格式 |
| `SLEEP_STAGES` 枚举对齐官方文档 | `"Core"`, `"REM"`, `"Deep"` 等 |
| `AGGREGATION_METRICS` 对齐真机数据 | `apple_exercise_time`, `basal_energy_burned` 等 16 个指标 |
| `on_event("startup")` → lifespan | FastAPI 新 API，消除 DeprecationWarning |

#### Phase 1 → Phase 3 接口契约

Phase 3 的 Perception Agent 可直接使用以下已就绪的接口：

| 数据需求 | 获取方式 | 可用状态 |
|---------|---------|---------|
| 今日日聚合 | `GET /api/v1/health/daily?date=today` | ✅ 可用 |
| 30天基线 | `GET /api/v1/health/baseline?metric_type=heart_rate&days=30` | ✅ 可用 |
| 原始数据点 | `GET /api/v1/health/raw?metric_type=X&date_from=Y` | ✅ 可用 |
| 数据库概览 | `GET /api/v1/health/status` | ✅ 可用 |
| Python 函数调用 | `aggregator.compute_baseline(db, metric, days)` | ✅ 可用 |

**Phase 3 启动策略**：Phase 1 已有真实数据，Perception Agent 直接消费上述 REST 端点或 Python 函数，无需再依赖模拟数据。

### Phase 2 — RAG 知识库 ✅ 已完成

| 维度 | 内容 |
|------|------|
| **目标** | 华佗医疗对话27.6万条 → ChromaDB向量库 → 检索接口 |
| **任务清单** | ①数据加载+清洗+去重 ✅ ②DashScope text-embedding-v4批量嵌入 ✅ ③ChromaDB持久化 ✅ ④`MedicalRetriever`检索接口 ✅ |
| **输入** | Phase 0 + 华佗数据集 |
| **输出** | `rag/build_vectordb.py`, `rag/retriever.py`, `data/chroma/` |
| **状态** | ✅ 已完成。27.6万条清洗后入库，1024维，检索延迟<150ms |

#### Phase 2 → Phase 3 接口契约

```python
# Phase 3 直接调用的接口（已就绪）
from rag.retriever import MedicalRetriever

retriever = MedicalRetriever()                    # persist_dir="./data/chroma"
docs = retriever.search("小孩发烧39度怎么办？", k=5)  # → list[dict]
# 每个 doc: {"id", "content", "question", "source", "score"}

context = retriever.format_context(docs)          # → str (可直接喂给LLM)
```

**已验证**：Embedding使用DashScope `text-embedding-v4`（1024维），入库约40分钟，费用~¥6。断点续传机制可用。

**未验证**：检索质量尚未通过Phase 3 Agent实际使用来评估（因为Agent还没开发）。但这不阻塞Phase 3——检索接口可直接调用，质量评估可在Phase 3开发过程中并行进行。

### Phase 3 — Agent 系统 ⭐ 核心（当前卡点）

| 维度       | 内容                                                                                                             |
| -------- | -------------------------------------------------------------------------------------------------------------- |
| **目标**   | 用LangGraph StateGraph构建完整Agent调度："意图路由→Self-RAG→回答生成"闭环                                                        |
| **输入**   | Phase 0：`config/llm.py` LLM实例；Phase 2：`rag/retriever.py`检索接口；Phase 1：`data_pipeline/`真实健康数据（✅已就绪） |
| **输出**   | `agents/`下8个`.py`文件 + `prompts/`下Prompt模板 + FastAPI `/api/v1/chat`端点                                           |
| **状态**   | ❌ 未开始。`agents/`和`prompts/`仅有空`__init__.py`                                                                     |
| **预估工期** | 2-3周                                                                                                           |

#### 开发顺序（文件级，严格按依赖排列）

```
Step 1: agents/state.py         — AgentState TypedDict 定义
Step 2: prompts/                 — 5个Prompt模板（router/analysis/reflect/revise/action）
Step 3: agents/boundary.py      — 硬边界拒答模板
Step 4: agents/router.py        — 意图路由节点
Step 5: agents/analysis.py      — Self-RAG核心（检索→生成→自检→修正）
Step 6: agents/perception.py    — 健康数据感知（消费Phase 1数据）
Step 7: agents/action.py        — 对话/建议生成
Step 8: agents/graph.py         — StateGraph编译 + FastAPI chat端点
```

**Phase 3 数据依赖现状**：
- Phase 1 真实数据已就绪（一年历史 + 日聚合 + 基线），Perception Agent 可直接消费
- Phase 2 RAG 检索接口已就绪（27.6万条医疗QA）
- Perception Agent 可直接调 `compute_baseline()` 或 `/api/v1/health/baseline` 获取 30 天基线
- 其余 Agent 节点（Router/Analysis/Action）完全不依赖 Phase 1

详见 **第五章 Phase 3 详细设计**。

### Phase 4 — 长期记忆 & 健康趋势

| 维度 | 内容 |
|------|------|
| **目标** | 对话历史持久化 + 周报生成 + 健康趋势查询 |
| **主要任务** | ①对话历史SQLite存储 + ChromaDB语义记忆 ②周报生成（LLM叙事+embedding存储） ③趋势查询 |
| **输入** | Phase 3（Agent系统可用，有对话产出） |
| **输出** | `memory/vector_store.py`, `memory/weekly_summary.py`, `memory/trend.py` |
| **状态** | ❌ 未开始 |
| **预估工期** | 1-2周（可与Phase 5并行） |

### Phase 5 — uni-app 小程序前端

| 维度 | 内容 |
|------|------|
| **目标** | 微信小程序，4个页面：对话、健康看板、周报、设置 |
| **主要任务** | ①uni-app项目初始化 ②ChatView对话页 ③Dashboard健康看板 ④Report周报展示 ⑤Settings设置页 ⑥与FastAPI联调 |
| **输入** | Phase 3（`/api/v1/chat`等端点） |
| **输出** | `frontend/`下完整uni-app项目 |
| **状态** | ❌ 未开始。`frontend/`仅有`README.md` |
| **预估工期** | 2-3周（可与Phase 4并行） |

**建议**：Phase 5不要等Phase 3全部完成再启动。可以在Phase 3有第一个可用的`/api/v1/chat`端点后就开始前端搭建，先做UI部分（用mock数据），再逐步替换为真实API。

### Phase 6 — 集成测试 & 上线

| 维度 | 内容 |
|------|------|
| **目标** | 端到端验证 + 质量评估 + 小程序审核提交 |
| **主要任务** | ①意图路由准确率测试 ②RAG检索质量评估 ③Self-RAG修正率统计 ④紧急词触发测试 ⑤性能优化 ⑥小程序审核 |
| **输入** | Phase 3 + Phase 4 + Phase 5 |
| **输出** | 测试报告、性能基线、小程序提交 |
| **状态** | ❌ 未开始 |
| **预估工期** | 1-2周 |

---

## 五、Phase 3 详细设计

### 5.1 AgentState 定义

```python
# agents/state.py
from typing import TypedDict, Optional, Annotated
from langgraph.graph.message import add_messages

class HealthMetrics(TypedDict):
    """Phase 1 输出的日聚合数据（初期用模拟数据）"""
    date: str
    heart_rate: dict        # {avg, min, max, stddev, baseline_mean, deviation_pct}
    hrv: dict               # {avg, baseline_mean, deviation_pct}
    steps: dict             # {total, baseline_mean}
    sleep: dict             # {total_hours, deep_hours, rem_hours}
    active_energy: dict     # {total, baseline_mean}

class AgentState(TypedDict):
    # ── 用户输入 ──
    query: str
    messages: Annotated[list, add_messages]

    # ── 路由 ──
    intent: str             # "health_data" | "medical_qa" | "general_chat" | "emergency"
    route: str              # "perception" | "analysis" | "action" | "emergency"

    # ── 上下文 ──
    health_metrics: Optional[HealthMetrics]
    retrieved_docs: Optional[list[dict]]   # MedicalRetriever.search() 的返回
    personal_context: Optional[str]        # 个人基线 + 历史趋势文本

    # ── Self-RAG 中间态 ──
    draft_response: Optional[str]          # 生成初稿
    reflection_result: Optional[dict]      # 自检结果 {"pass": bool, "issues": str, "action": str}

    # ── 输出 ──
    response: str
    source: str             # "qwen3-max" | "deepseek"
    safety_level: str       # "normal" | "caution" | "emergency"
```

### 5.2 LangGraph 拓扑

```
用户输入
  │
  ▼
┌──────────────┐
│   Router     │  ← 意图分类 (LLM, temp=0.0)
│  意图路由     │     输出: intent ∈ {health_data, medical_qa, general_chat, emergency}
└──┬───┬───┬──┘
   │   │   │
   ▼   ▼   ▼
  health_data  medical_qa  general_chat  emergency
   │            │            │            │
   ▼            ▼            ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐
│Perception│ │ Retrieve │ │  Action  │ │  Emergency   │
│健康分析   │ │ RAG检索  │ │ 直接对话  │ │  紧急处理     │
│temp=0.1  │ │          │ │ temp=0.5 │ │  硬编码模板   │
└────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘
     │            │            │               │
     ▼            ▼            │               │
┌──────────┐ ┌──────────┐      │               │
│  Action  │ │ Generate │      │               │
│ 生成建议  │ │ 生成回答  │      │               │
│ temp=0.5 │ │temp=0.15│      │               │
└────┬─────┘ └────┬─────┘      │               │
     │            │            │               │
     │            ▼            │               │
     │       ┌──────────┐      │               │
     │       │ Reflect  │      │               │
     │       │ 自检     │      │               │
     │       │temp=0.0  │      │               │
     │       └────┬─────┘      │               │
     │        ┌───┴───┐        │               │
     │        │       │        │               │
     │      pass   retry   reject             │
     │        │       │        │               │
     │        ▼       ▼        ▼               │
     │    ┌──────┐ ┌──────┐ ┌──────────┐       │
     │    │输出   │ │Revise│ │Reject    │       │
     │    │      │ │修正  │ │拒答模板   │       │
     │    └──┬───┘ └──┬───┘ └────┬─────┘       │
     │       │        │          │              │
     └───────┴────────┴──────────┴──────────────┘
                     │
                     ▼
                  END
```

### 5.3 各节点设计概要

#### Router 节点

- **LLM**: `get_llm("router")` → temp=0.0, max_tokens=100
- **输入**: `state["query"]`
- **输出**: `intent` ∈ `{health_data, medical_qa, general_chat, emergency}`
- **Prompt要点**: 四分类，仅回复标签

#### Perception 节点（健康数据分析）

- **LLM**: `get_llm("perception")` → temp=0.1, max_tokens=1024
- **数据来源**: 初期用模拟HealthMetrics；后期从`data_pipeline`读取
- **输出**: 结构化健康摘要 + 异常标注

#### Analysis 节点（Self-RAG核心）

子步骤：
1. **Retrieve**: 调用 `MedicalRetriever.search(query, k=5)` → 取回Top-5 QA对
2. **Generate**: LLM (temp=0.15) 基于检索知识生成回答初稿
3. **Reflect**: LLM (temp=0.0) 自检——回答是否有检索依据？是否有编造？是否越界诊断？
4. **条件路由**: pass→输出；retry→Revise修正；reject→拒答模板
5. **Revise** (如需要): LLM针对性修正后输出

#### Action 节点（对话生成）

- **LLM**: `get_llm("action")` → temp=0.5, max_tokens=2048
- **输入**: 上游分析结果 + 对话历史
- **输出**: 自然对话风格的最终回答

### 5.4 硬边界拒答规则

```python
# agents/boundary.py
EMERGENCY_KEYWORDS = ["胸痛", "呼吸困难", "大出血", "意识丧失", "严重外伤",
                       "中风", "心梗", "窒息", "休克", "濒死"]

REJECT_TEMPLATES = {
    "diagnosis": "我无法进行医学诊断。{issues}建议您前往正规医疗机构就诊。",
    "prescription": "我无法开具处方或推荐具体药物剂量。用药请咨询医生。",
    "emergency": "您描述的症状可能需要紧急医疗处理。请立即拨打120或前往最近的急诊科。",
}
```

### 5.5 Phase 3 与 Phase 1/2 的接口调用方式

```python
# ── 调用 Phase 2: RAG检索 ──
from rag.retriever import MedicalRetriever
retriever = MedicalRetriever()                      # 单例，初始化一次
docs = retriever.search(query, k=5)                 # 检索
context = retriever.format_context(docs)            # 格式化为LLM上下文

# ── 调用 Phase 1: 健康数据（初期用模拟数据替代） ──
from data_pipeline.database import SessionLocal
from data_pipeline.aggregator import compute_baseline
from data_pipeline.models import DailyMetric
from datetime import date

def get_health_summary() -> dict:
    """获取今日健康摘要 + 基线对比。初期可用硬编码模拟数据。"""
    db = SessionLocal()
    try:
        today_metrics = db.query(DailyMetric).filter(
            DailyMetric.date == date.today()
        ).all()

        result = {}
        for m in today_metrics:
            baseline = compute_baseline(db, m.metric_type, days=30)
            deviation = None
            if baseline.get("mean") and baseline.get("std") and baseline["std"] > 0:
                deviation = round((m.avg_value - baseline["mean"]) / baseline["std"], 2)
            result[m.metric_type] = {
                "avg": m.avg_value,
                "min": m.min_value,
                "max": m.max_value,
                "baseline_mean": baseline.get("mean"),
                "deviation_sigma": deviation,
            }
        return result
    finally:
        db.close()
```

---

## 六、数据流详解

### 数据流 A：Apple Health 数据通路

```
iPhone (Health Auto Export, 每30min自动)
  → HTTPS POST → ngrok公网URL
  → localhost:8000/api/v1/health/sync (FastAPI)
  → Pydantic校验 (HealthSyncRequest → HealthExportPayload → HealthMetric)
  → 逐条写入 raw_health_samples (SQLite)
  → 触发 aggregate_daily_metrics() → daily_metrics (SQLite)
  → Phase 3 Perception Agent 读取 daily_metrics + compute_baseline()
  → 生成结构化健康摘要 → 喂给Action Agent生成建议
```

### 数据流 B：医疗问答通路（核心）

```
用户输入 ("小孩发烧39度怎么办？")
  → POST /api/v1/chat → LangGraph graph.invoke()
  → Router节点: intent="medical_qa"
  → Analysis节点:
      ① MedicalRetriever.search(query, k=5) → ChromaDB本地检索(~20ms)
      ② DashScope embed_query(query) → API嵌入(~100ms)
      ③ Qwen3-Max 生成回答初稿
      ④ Qwen3-Max 自检 (reflect)
      ⑤ 条件: pass→输出 / retry→修正 / reject→拒答
  → Action节点: 拟人化对话输出
  → 返回给用户
```

### 数据流 C：周报生成通路（Phase 4）

```
定时任务 (每周日)
  → 读取 daily_metrics 最近7天
  → Qwen3-Max 生成叙事性健康周报
  → text-embedding-v4 embedding
  → 存入 ChromaDB memory collection
  → 用户查询"我这个月压力变化趋势？"
  → 语义检索历史周报 + SQL趋势数据 → Qwen3-Max生成回答
```

---

## 七、API 设计

### 7.1 已有端点（Phase 1）

| Method | Path | 说明 | 状态 |
|--------|------|------|------|
| `POST` | `/api/v1/health/sync` | 接收Health Auto Export推送 | ✅ |
| `GET` | `/api/v1/health/daily?date=YYYY-MM-DD` | 日聚合指标查询 | ✅ |
| `GET` | `/api/v1/health/raw?metric_type=X&date_from=Y` | 原始数据查询 | ✅ |
| `GET` | `/api/v1/health/status` | 数据库概览 | ✅ |

### 7.2 待开发端点

#### Phase 3 核心端点

```
POST /api/v1/chat
  Request:  {"query": "小孩发烧39度怎么办？", "session_id": "xxx"}
  Response: {
    "response": "小孩发烧39度属于高热...",
    "intent": "medical_qa",
    "source": "qwen3-max",
    "safety_level": "normal",
    "retrieved_docs": [{"question": "...", "score": 0.92}, ...]
  }

GET /api/v1/chat/{session_id}/history
  Response: {"messages": [...]}
```

#### Phase 1 待补充端点

```
GET /api/v1/health/baseline?metric_type=heart_rate&days=30
  Response: {
    "metric_type": "heart_rate",
    "window_days": 30,
    "mean": 68.5, "std": 4.2,
    "upper_bound": 76.9, "lower_bound": 60.1,
    "n_days": 28
  }
```

#### Phase 4 端点（规划）

```
GET  /api/v1/memory/weekly-report?week_start=YYYY-MM-DD
POST /api/v1/memory/trend
  Request:  {"query": "最近三个月HRV变化趋势"}
  Response: {"response": "...", "data": [...]}
```

---

## 八、里程碑与时间线

```
Week 1-2  (当前)    Phase 1 收尾: ngrok部署 + iOS联调
                    Phase 3 启动: agents/state.py + router.py + prompts/

Week 3-4           Phase 3 核心: analysis.py (Self-RAG) + perception.py
                   ★ 里程碑 M1: 首个 Self-RAG 闭环 (检索→生成→自检→修正)

Week 5-6           Phase 3 收尾: action.py + graph.py + /api/v1/chat 端点
                   ★ 里程碑 M2: 端到端对话可用 (curl测试通过)

Week 6-8           Phase 4 (长期记忆) || Phase 5 (小程序前端) 并行
                   ★ 里程碑 M3: 微信开发者工具可扫码预览

Week 8-10          Phase 6: 集成测试 + 质量评估 + 小程序审核提交
                   ★ 里程碑 M4: 小程序提交审核
```

### 关键里程碑

| 里程碑 | 定义 | 验证方式 |
|--------|------|---------|
| M0 | Phase 1真实数据到达 | `GET /status` 返回 total_raw_samples > 0 |
| M1 | Self-RAG闭环 | 20条医学测试问题，修正率>80% |
| M2 | 端到端对话 | `curl POST /api/v1/chat` 返回RAG增强回答 |
| M3 | 小程序扫码可用 | 微信开发者工具扫码，对话页可问答 |
| M4 | 提交审核 | 测试报告通过，小程序代码提交微信审核 |

---

## 九、风险管理

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| Phase 1 ngrok URL频繁变化 | 高 | 低 | 使用`start_pipeline.sh`自动获取URL；后续切Cloudflare Tunnel |
| Phase 1 JSON格式不兼容真机 | 中 | 中 | 先发模拟数据跑通Phase 3；真机数据到达后按Phase1v2附录D增量修复 |
| Qwen3-Max API额度耗尽 | 中 | 低 | `config/llm.py`一键切DeepSeek，零代码改动 |
| Self-RAG自检准确率低 | 中 | 高 | Prompt迭代优化；必要时引入独立审查（附录B方案） |
| RAG检索结果不满足医疗问答需求 | 低 | 中 | 调整检索参数(k值、距离阈值)；补充医疗数据集 |
| 微信小程序审核被拒 | 中 | 中 | 医疗类小程序需注意：不做诊断、不做处方、加免责声明 |
| 6GB显存不够（如需本地embedding） | - | - | 已确认：Embedding走API，ChromaDB检索走CPU，不占用GPU |

---

## 十、附录

### 附录 A：文档索引

| 文件 | 类型 | 用途 | 状态 |
|------|------|------|------|
| `Medical-Health-Agent方案v3.md` | ★ 主方案 | 当前版本，所有执行以此为准 | **当前** |
| `v3-前置mini方案.md` | 前置分析 | v3的规划输入，诊断+指令 | 保留 |
| `Medical-Health-Agent方案v2.3.md` | 历史方案 | v3的基础版本 | 保留 |
| `Medical-Health-Agent方案v2.2.md` | 历史方案 | Self-RAG设计细节参考 | 保留 |
| `Medical-Health-Agent方案v2.1.md` | 历史方案 | 总时间线+成本估算参考 | 保留 |
| `Medical-Health-Agent方案v1.1.md` | 历史方案 | 架构起源（三层Agent+混合架构） | 保留 |
| `Medical-Health-Agent方案v1.2-本地RAG方案分析.md` | 历史方案 | 硬件实测+显存精算 | 保留 |
| `Medical-Health-Agent方案v1.3-MedicalGPT训练部署方案.md` | 历史方案 | 训练流程参考（已弃用方向） | 保留 |
| `Phase0-项目搭建方案.md` | Phase文档 | Phase 0详细执行记录 | ✅ 已完成 |
| `Phase1v2-Apple-Health数据管道实施方案.md` | Phase文档 | Phase 1 v2改进方案（代码待升级） | ⚠️ 代码未同步 |
| `Phase1-Apple-Health数据管道实施方案.md` | Phase文档 | Phase 1 v1原版（已被v2取代） | 保留参考 |
| `Phase2-医疗RAG知识库构建方案.md` | Phase文档 | Phase 2详细执行记录 | ✅ 已完成 |
| `docs/ngrok-vs-cloudflare-tunnel.md` | 参考 | 内网穿透方案对比 | 参考 |

### 附录 B：已知待确认事项

| # | 事项 | 来源 | 优先级 |
|---|------|------|--------|
| 1 | Phase 1 代码升级到v2（JSON格式校正、baseline端点等） | Phase1v2附录D vs 实际代码 | P1（真机联调前） |
| 2 | 睡眠阶段枚举值真机验证（`"Core"` vs `"asleepCore"`等） | Phase1v2 §C.1 | P2（有睡眠数据后） |
| 3 | RAG检索质量评估（20条医学测试问题） | Phase2 §7.2 | P2（Phase 3开发中并行） |
| 4 | Qwen3-Max 额度剩余量确认 | 用户 | P3（额度用尽前一周切换） |
| 5 | 微信小程序医疗类目审核要求 | — | P3（Phase 5启动前调研） |

### 附录 C：v3 相对于 v2.3 的版本变更

| 变更点          | v2.3            | v3                                     | 理由              |
| ------------ | --------------- | -------------------------------------- | --------------- |
| 文档定位         | 方案描述            | **可执行方案 + 接口契约**                       | 解决"文档不能指导执行"的问题 |
| Phase 1 状态   | "代码已完成"         | ⚠️ 代码为v1，需升级到v2 + 部署ngrok              | 基于实际代码验证        |
| Phase 1→3 接口 | 未定义             | 明确定义Python函数调用接口                       | 解除Phase 3启动阻塞   |
| Phase 3 启动策略 | Phase 1/2 完成后启动 | **可立即启动**（用模拟健康数据）                     | 不等待iOS联调        |
| Phase 3 设计   | 概略描述            | 完整AgentState + Graph拓扑 + 节点设计 + 接口调用方式 | 可直接编码           |
| 本地模型         | 未提及             | 明确记录放弃原因（训练成本）                         | 决策可追溯           |
| Embedding方案  | 模糊（文档讨论过两种）     | 确认 DashScope text-embedding-v4         | 基于实际代码          |
| 进度控制         | 无               | 里程碑M0-M4 + 每个Phase验收标准                 | 防止不同步           |

---

> **下一步**：
> 1. 从 Phase 3 Step 1 (`agents/state.py`) 开始编码
> 2. Phase 1 ngrok部署可并行推进（不阻塞Phase 3）
> 3. Phase 3 开发期间持续用模拟数据验证，真实数据通路打通后切换
