# Medical-Health-Agent

> AI 个人健康管家 — Apple Health 数据同步 + 华佗 RAG 医疗知识库 + LangGraph 多 Agent 协作

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.4-4FC08D.svg)](https://vuejs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-orange.svg)](https://www.langchain.com/langgraph)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-0.5+-brightgreen.svg)](https://www.trychroma.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 项目简介

**Medical-Health-Agent** 是一个个人 AI 健康管家系统。它接收 iPhone Apple Health 的生理数据（39 种指标，覆盖 376 天），结合 **华佗医疗知识库**（27.6 万条 QA）进行 RAG 增强检索，通过 LangGraph 编排多个 Agent 协作，提供健康数据分析与医疗问答服务。前端为 Vue 3 H5 SPA，后端为 FastAPI。

### 核心能力

| # | 能力 | 说明 | 状态 |
|---|------|------|:--:|
| 1 | **Apple Health 数据管道** | iPhone → ngrok → FastAPI → SQLite，39 种指标日聚合 + 30 天基线 | ✅ |
| 2 | **华佗 RAG 知识库** | 27.6 万条医疗 QA，ChromaDB 向量检索，延迟 <150ms | ✅ |
| 3 | **Self-RAG 医疗问答** | 检索→生成→自检→修正闭环，防幻觉、防编造 | ✅ |
| 4 | **健康数据分析** | 近 3 天滑动窗口 + 基线偏离检测 + 逐项指标分析 | ✅ |
| 5 | **意图路由** | 关键词快速分类（<0.01s）+ LLM 兜底，四分类准确率 ≥85% | ✅ |
| 6 | **硬边界安全** | 10 个紧急关键词短路 + 诊断/处方拒答模板 | ✅ |
| 7 | **多轮对话记忆** | SQLite 持久化 + 最近 5 轮上下文注入 + 会话管理 | ✅ |
| 8 | **周报 & 趋势** | LLM 叙事周报 + 多周趋势对比（direction + change_pct） | ✅ |
| 9 | **H5 前端** | Vue 3 + Vite + Pinia，对话/看板/周报/设置 4 页面 | ✅ |
| 10 | **多 Provider LLM** | 一行切换 Qwen3-Max / DeepSeek，零代码改动 | ✅ |

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                     LangGraph 调度层                              │
│       意图路由 → Self-RAG(检索→生成→自检→修正) → 回答              │
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
│  │  RAG 知识库 (ChromaDB) │     │  健康数据管道 (SQLite)     │      │
│  │  华佗 27.6 万条 QA     │     │  39 指标 × 376 天 × 聚合   │      │
│  └───────────────────────┘     └──────────────────────────┘      │
└──────────────────────────────────────────────────────────────────┘
                                │ HTTP
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                  FastAPI 后端 (localhost:8000)                     │
│  /api/v1/chat  |  /api/v1/health/*  |  /api/v1/report/*          │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTP
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│               Vue 3 H5 前端 (localhost:5173)                      │
│  Chat 对话 | Dashboard 健康看板 | Report 周报 | Settings 设置     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
Medical-Health-Agent/
├── agents/                    # LangGraph Agent 系统
│   ├── state.py               # AgentState 类型定义
│   ├── graph.py               # Graph 编译 + chat() 入口
│   ├── router.py              # 意图路由（关键词 + LLM 兜底）
│   ├── analysis.py            # Self-RAG 核心（检索→生成→自检→修正）
│   ├── perception.py          # 健康数据感知分析
│   ├── action.py              # 对话生成 + 时间问候
│   └── boundary.py            # 硬边界紧急检测 + 拒答模板
│
├── prompts/                   # Prompt 模板
│   ├── router.py              # 意图分类 Prompt
│   ├── analysis.py            # 医疗问答 + Self-RAG Prompt
│   ├── perception.py          # 健康数据分析 Prompt
│   ├── action.py              # 对话生成 Prompt
│   └── boundary.py            # 紧急关键词定义
│
├── data_pipeline/             # Apple Health 数据管道
│   ├── webhook_server.py      # FastAPI 服务（13 个端点）
│   ├── models.py              # Pydantic + SQLAlchemy 模型
│   ├── database.py            # 数据库初始化与连接
│   ├── aggregator.py          # 日聚合 + 基线计算
│   ├── config.py              # 管道配置 + 39 种指标定义
│   └── test_data.py           # 模拟数据生成
│
├── rag/                       # RAG 知识库
│   ├── retriever.py           # MedicalRetriever 检索接口
│   └── build_vectordb.py      # 华佗数据集 → ChromaDB
│
├── memory/                    # 长期记忆系统
│   ├── database.py            # memory.db 初始化
│   ├── schema.py              # 表结构定义
│   ├── history.py             # 对话历史 CRUD + 会话管理
│   ├── weekly.py              # 周报生成 + 查询
│   └── trend.py               # 多周趋势分析
│
├── config/                    # 全局配置
│   └── llm.py                 # LLM 配置中心（多 Provider 一键切换）
│
├── frontend/                  # Vue 3 H5 前端
│   ├── src/
│   │   ├── pages/
│   │   │   ├── chat/          # 对话页（气泡 + 会话侧栏 + 进度动画）
│   │   │   ├── dashboard/     # 健康看板（39 指标卡片 + 趋势图）
│   │   │   ├── report/        # 周报页（横滑选择 + LLM 叙事）
│   │   │   └── settings/      # 设置页（API 检测 + 数据同步）
│   │   ├── stores/            # Pinia 状态管理
│   │   └── api/               # fetch 封装 + API 模块
│   ├── vite.config.js         # Vite 代理配置
│   └── package.json
│
├── data/                      # 持久化数据
│   ├── health.db              # 健康数据（raw_health_samples + daily_metrics）
│   ├── memory.db              # 记忆数据（chat_history + weekly_reports）
│   └── chroma/                # ChromaDB 向量库（27.6 万条）
│
├── docs/                      # 测试手册
│   ├── Phase1-测试手册.md
│   ├── Phase3-测试手册.md
│   ├── Phase4-测试手册.md
│   └── Phase5-测试手册.md
│
├── requirements.txt           # Python 依赖
├── .env.example               # 环境变量模板
└── Medical-Health-Agent方案v3.md  # 完整方案文档
```

---

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 18+
- DashScope API Key（[阿里云灵积](https://dashscope.aliyun.com/)）
- （可选）DeepSeek API Key 作为备用
- （可选）iPhone + Health Auto Export App + ngrok 用于真机数据

### 1. 克隆项目

```bash
git clone <repo-url>
cd Medical-Health-Agent
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少填入 DASHSCOPE_API_KEY
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### 4. 验证 LLM 连通性

```bash
python -m config.llm
```

### 5. 启动后端

```bash
python -m data_pipeline.webhook_server
# → http://localhost:8000
```

### 6. 启动前端

```bash
cd frontend
npm run dev
# → http://localhost:5173
```

浏览器打开 `http://localhost:5173`，前端自动代理 `/api/*` 到后端。

---

## API 端点总览

### 健康数据（Phase 1+4）

| Method | Path | 说明 |
|--------|------|------|
| `POST` | `/api/v1/health/sync` | 接收 Apple Health Auto Export 推送 |
| `GET` | `/api/v1/health/status` | 数据库概览 + 同步状态 |
| `GET` | `/api/v1/health/daily?date=YYYY-MM-DD` | 日聚合指标查询 |
| `GET` | `/api/v1/health/raw?metric_type=X&date_from=Y` | 原始数据点查询 |
| `GET` | `/api/v1/health/baseline?metric_type=X&days=30` | 30 天基线（均值 ± 2σ） |
| `GET` | `/api/v1/health/trend?metric=X&weeks=4` | 多周趋势（direction + change_pct） |

### 对话 & 记忆（Phase 3+4）

| Method | Path | 说明 |
|--------|------|------|
| `POST` | `/api/v1/chat` | 多轮对话（含 Self-RAG） |
| `GET` | `/api/v1/memory/sessions` | 会话列表 |
| `GET` | `/api/v1/memory/history?session_id=X` | 对话历史 |
| `DELETE` | `/api/v1/memory/sessions/{id}` | 清除会话 |
| `POST` | `/api/v1/report/weekly` | 生成周报 |
| `GET` | `/api/v1/report/weekly?week_start=X` | 查询历史周报 |
| `GET` | `/api/v1/report/weekly/list` | 周报列表 |

---

## 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| Agent 编排 | **LangGraph** ≥0.2.0 | StateGraph 构建，条件路由 |
| LLM 调用 | **langchain-openai** (兼容接口) | 统一接口，一键切换 Provider |
| 主力 LLM | **Qwen3-Max** (DashScope) | 额度优先消耗 |
| 备选 LLM | **DeepSeek V4 Flash** | Qwen 额度用完后切换 |
| Embedding | **DashScope text-embedding-v4** | 1024 维向量嵌入 |
| 向量库 | **ChromaDB** (persistent) | HNSW 索引，本地持久化 |
| 后端 | **FastAPI** ≥0.115 | API 服务 |
| 数据存储 | **SQLite** | 健康数据 + 对话历史 |
| 前端 | **Vue 3 + Vite + Pinia** | H5 SPA |
| 内网穿透 | **ngrok** → Cloudflare Tunnel | iPhone → 后端数据通路 |

---

## 工作流程

### Apple Health 数据通路

```
iPhone (Health Auto Export, 每 30min 自动)
  → HTTPS POST → ngrok 公网 URL
  → localhost:8000/api/v1/health/sync
  → Pydantic 校验 → raw_health_samples (SQLite)
  → 自动触发 aggregate_daily_metrics()
  → daily_metrics (SQLite)
  → Phase 3 Perception Agent 消费
```

### 医疗问答通路（Self-RAG）

```
用户输入 "小孩发烧 39 度怎么办？"
  → POST /api/v1/chat → LangGraph graph.invoke()
  → Router: intent="medical_qa"（关键词匹配 <0.01s）
  → Retrieve: ChromaDB 本地检索 Top-5 QA（~20ms）
  → Generate: Qwen3-Max 基于知识生成初稿
  → Reflect: Qwen3-Max 自检（是否有依据？是否编造？是否越界？）
  → pass → Action 拟人化输出
  → retry → Revise 修正 → 重新生成
  → reject → 拒答模板
```

### 紧急短路

```
用户输入 "我胸痛呼吸困难"
  → boundary.check_emergency() 命中关键词
  → 直接返回紧急引导（含 120），不调用任何 LLM
  → source="rule", safety_level="emergency", 响应 <0.1s
```

---

## 数据规模

| 指标 | 数值 |
|------|------|
| Apple Health 指标种类 | **39 种** |
| 历史数据覆盖天数 | **376 天** |
| 原始数据点数 | **116,857 条** |
| 日聚合行数 | **9,635 行** |
| 华佗医疗 QA 入库 | **27.6 万条** |
| ChromaDB 向量维度 | **1024** 维 |
| RAG 检索延迟 | **<150ms** |
| 意图路由（关键词命中） | **<0.01s** |
| Self-RAG 全流程 | **~60s** |

---

## LLM 多 Provider 切换

编辑 `config/llm.py` 第 28 行：

```python
CURRENT_PROVIDER = "qwen"        # Qwen3-Max（默认）
CURRENT_PROVIDER = "deepseek"    # DeepSeek V4 Flash
CURRENT_PROVIDER = "deepseek-pro"# DeepSeek V4 Pro
CURRENT_PROVIDER = "qwen-flash"  # Qwen3-Flash（快速+节省）
```

支持任意 OpenAI 兼容接口，在 `PROVIDER_CONFIGS` 字典中添加一行即可扩展。

---

## iPhone 真机配置

1. 安装 [Health Auto Export](https://apps.apple.com/app/health-auto-export/id1115567069) App
2. 启动后端：`python -m data_pipeline.webhook_server`
3. 启动 ngrok：`ngrok http 8000`
4. 在 App 中配置 Automation → API Export：
   - URL: `https://<ngrok-url>/api/v1/health/sync`
   - Format: JSON
   - Header: `Authorization: Bearer medical-health-agent-dev-key-2026`
5. 手动触发同步或设置自动同步（每 30 分钟）

---

## 本地测试

```bash
# 验证所有 Agent 节点导入
python -c "from agents.state import AgentState; from agents.graph import build_graph; \
  from agents.router import router_node; from agents.analysis import retrieve, generate, reflect; \
  from agents.perception import perception_node; from agents.action import action_node; \
  print('ALL IMPORTS OK')"

# 测试紧急检测
python -c "from agents.boundary import check_emergency; \
  print(check_emergency('我胸痛呼吸困难'))"

# 测试 RAG 检索
python -c "from rag.retriever import MedicalRetriever; \
  r = MedicalRetriever(); \
  docs = r.search('小孩发烧39度怎么办？', k=3); \
  [print(f'  [{d[\"score\"]:.3f}] {d[\"content\"][:60]}...') for d in docs]"

# 测试 LLM 连通性
python -m config.llm
```

---

## 里程碑

| 里程碑 | 定义 | 状态 |
|--------|------|:--:|
| M0 | Phase 1 真实数据到达（376 天，116K+ 条） | ✅ |
| M1 | Self-RAG 闭环（检索→生成→自检→修正） | ✅ |
| M2 | 端到端对话（`POST /api/v1/chat` 可用） | ✅ |
| M3 | 前端 H5 可访问（4 页面完整） | ✅ |
| M4 | 集成测试 & 上线 | 🔜 |

---

## 安全性

- **紧急关键词短路**：胸痛、呼吸困难、大出血等 10 个关键词直接触发紧急引导，零 LLM 调用
- **硬边界拒答**：拒绝医学诊断、开具处方、药物剂量推荐
- **Self-RAG 自检**：每次医疗回答经过「是否有依据？是否编造？是否越界？」三层检查
- **API 鉴权**：`/api/v1/health/sync` 使用 Bearer Token 验证
- **免责声明**：前端对话页明确标注「AI 健康助手，不构成医疗建议」

---

## 演进历史

| 版本 | 日期 | 核心变化 |
|------|------|---------|
| v1.x | 2026-05 | 三层 Agent + 本地 Qwen3-4B → **已废弃**（6GB 显存瓶颈 + 训练成本过高） |
| v2.x | 2026-05 | 纯 API 架构，Self-RAG 机制，切换 Qwen3-Max → 确立基底 |
| **v3** | **2026-05-10** | **可执行方案 + 接口契约**，Phases 0-5 全部完成 |

> **关键决策**：v2.x 起放弃本地模型，采用纯 API 路线 —— LLM 推理全部走云端，本地仅保留 ChromaDB 向量检索。理由是 API 强模型 + RAG 的医疗问答质量远超本地 4B 模型。

---

## License

MIT

---

## 参考文档

- [Medical-Health-Agent 方案 v3](./Medical-Health-Agent方案v3.md) — 完整系统方案
- [Phase 1 测试手册](./docs/Phase1-测试手册.md)
- [Phase 3 测试手册](./docs/Phase3-测试手册.md)
- [Phase 4 测试手册](./docs/Phase4-测试手册.md)
- [Phase 5 测试手册](./docs/Phase5-测试手册.md)
