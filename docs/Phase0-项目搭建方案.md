# Phase 0: 项目搭建方案

> **目标**：完成项目目录搭建、依赖安装、LLM 配置与连通性验证，为 Phase 1-6 提供可运行的基础环境。
>
> **周期**：半天
>
> **核心原则**：基础设施先行，保证后续每个 Phase 不需要回头补环境配置。

---

## 目录

1. [成果清单](#1-成果清单)
2. [目录结构](#2-目录结构)
3. [环境准备](#3-环境准备)
4. [LLM 配置与测试](#4-llm-配置与测试)
5. [数据管道验证](#5-数据管道验证)
6. [RAG 知识库验证](#6-rag-知识库验证)
7. [验收清单](#7-验收清单)
8. [下一步 Phase 3](#8-下一步-phase-3)

---

## 1. 成果清单

| # | 产出 | 状态 | 说明 |
|---|------|------|------|
| 1 | 目录结构 | ✅ 已创建 | 7 个模块目录 + 配置/文档 |
| 2 | `.env.example` | ✅ | 环境变量模板，含所有配置项说明 |
| 3 | `.gitignore` | ✅ | 排除 `__pycache__`/`.env`/`data/`/`node_modules` |
| 4 | `requirements.txt` | ✅ | Python 依赖清单 (FastAPI + LangChain + ChromaDB) |
| 5 | `config/llm.py` | ✅ | 多 provider 配置中心 + 连通性测试 |
| 6 | `config/__init__.py` | ✅ | Python 包标记 |
| 7 | 模块 `__init__.py` | ✅ | agents/, prompts/, memory/, tests/ |
| 8 | `frontend/README.md` | ✅ | uni-app 技术栈说明 (Phase 5 执行) |
| 9 | `Medical-Health-Agent方案v2.3.md` | ✅ | 主方案文档 (uni-app 框架确认) |
| 10 | 本文档 | ✅ | Phase 0 项目搭建方案 |

---

## 2. 目录结构

```
Medical-Health-Agent/
│
├── agents/                        # Phase 3 | LangGraph Agent 系统
│   └── __init__.py
│
├── config/                        # Phase 0 ✅ | 全局配置
│   ├── __init__.py
│   └── llm.py                     #   LLM 配置中心 (多 provider + 测试)
│
├── data_pipeline/                 # Phase 1 ✅ | Apple Health 数据管道
│   ├── __init__.py
│   ├── config.py                  #   全局配置 (DB / API Key / 聚合白名单)
│   ├── models.py                  #   Pydantic 校验 + SQLAlchemy 表
│   ├── database.py                #   数据库引擎 + 会话管理
│   ├── webhook_server.py          #   FastAPI 主应用 (全部 API 端点)
│   ├── aggregator.py              #   数据聚合引擎
│   └── test_data.py               #   模拟测试数据生成器
│
├── rag/                           # Phase 2 ✅ | 医疗 RAG 知识库
│   ├── __init__.py
│   ├── build_vectordb.py          #   数据清洗 + ChromaDB 构建
│   ├── retriever.py               #   MedicalRetriever 检索接口
│   ├── analyze_datasets.py        #   数据集分析
│   └── data/                      #   ChromaDB 持久化目录
│       └── chroma/                #     huatuo_medical_qa collection
│
├── memory/                        # Phase 4 | 长期记忆模块
│   └── __init__.py
│
├── prompts/                       # Phase 3 | Prompt 模板
│   └── __init__.py
│
├── frontend/                      # Phase 5 | uni-app 小程序
│   └── README.md                  #   技术栈说明 (Phase 5 执行)
│
├── tests/                         # Phase 3+ | 测试
│   └── __init__.py
│
├── docs/                          # 外部参考文档
│   └── (Health Auto Export 文档待放入)
│
├── data/                          # 运行时数据 (自动生成，不提交)
│   ├── health.db                  #   SQLite 数据库
│   └── chroma/                    #   ChromaDB 向量库
│
├── .env.example                   # ✅ 环境变量模板
├── .gitignore                     # ✅ Git 忽略规则
├── requirements.txt               # ✅ Python 依赖清单
├── Medical-Health-Agent方案v2.3.md     # ✅ 主方案文档
├── Phase0-项目搭建方案.md              # ✅ 本文档
├── Phase1v2-Apple-Health数据管道实施方案.md
├── Phase2-医疗RAG知识库构建方案.md
├── Medical-Health-Agent方案v1.1.md
├── Medical-Health-Agent方案v1.2-本地RAG方案分析.md
├── Medical-Health-Agent方案v1.3-MedicalGPT训练部署方案.md
├── Medical-Health-Agent方案v2.1.md
├── Medical-Health-Agent方案v2.2.md
└── coding_test.py                 # LLM 快速测试脚本 (可删除)
```

### 各目录职责速查

| 目录 | Phase | 职责 | 输入 → 输出 |
|------|-------|------|------------|
| `config/` | 0 | LLM 配置 + 环境变量 | `.env` API Keys → Agent 可用的 LLM 实例 |
| `data_pipeline/` | 1 ✅ | Apple Health 数据采集 | iOS JSON → SQLite `raw_health_samples` + `daily_metrics` |
| `rag/` | 2 ✅ | 医疗知识检索 | 用户查询 → ChromaDB → Top-K QA 对 |
| `agents/` | 3 | LangGraph Agent 调度 | 用户输入 + RAG + 健康数据 → AI 回答 |
| `memory/` | 4 | 对话记忆 + 周报 | 对话历史 → ChromaDB 记忆 + 趋势分析 |
| `prompts/` | 3 | Prompt 模板管理 | 模板文件 → Agent 使用的 system/user prompt |
| `frontend/` | 5 | uni-app 小程序 | 用户交互 → HTTP → FastAPI 后端 |
| `tests/` | 3+ | 单元/集成测试 | 测试用例 → pass/fail 报告 |

---

## 3. 环境准备

### 3.1 前置要求

| 工具 | 版本要求 | 检查命令 |
|------|---------|----------|
| Python | ≥ 3.11 | `python --version` |
| pip | ≥ 23.0 | `pip --version` |
| Git | ≥ 2.40 | `git --version` |

### 3.2 安装依赖

```bash
cd Medical-Health-Agent
pip install -r requirements.txt
```

**依赖清单说明**：

| 依赖 | 用途 | Phase |
|------|------|-------|
| `fastapi` + `uvicorn` | API 服务框架 | Phase 1 |
| `sqlalchemy` | 数据库 ORM | Phase 1 |
| `pydantic` | 请求校验 | Phase 1 |
| `numpy` | 数值计算 (聚合/基线) | Phase 1 |
| `langchain` + `langchain-openai` | LLM 统一调用接口 | Phase 0-6 |
| `langgraph` | Agent 状态图调度 | Phase 3 |
| `chromadb` | 向量库存储 + 检索 | Phase 2 |
| `sentence-transformers` | 本地 Embedding (备选) | Phase 2 |
| `httpx` | HTTP 客户端 (API 测试) | Phase 3 |
| `tqdm` | 进度条 | Phase 2 |
| `python-dotenv` | .env 文件加载 | Phase 0 |

### 3.3 配置环境变量

```bash
# 1. 复制环境变量模板
cp .env.example .env

# 2. 编辑 .env，填入至少一个 LLM API Key
# 必填项: DASHSCOPE_API_KEY 或 DEEPSEEK_API_KEY (二选一)
```

> `.env` 文件已在 `.gitignore` 中排除，不会提交到 Git。

---

## 4. LLM 配置与测试

### 4.1 `config/llm.py` 设计

```
config/llm.py
│
├── PROVIDER_CONFIGS   ← 支持 5 种 provider
│   ├── qwen           (DashScope Qwen3-Max)
│   ├── qwen-flash     (DashScope Qwen3-Flash)
│   ├── deepseek       (DeepSeek V4 Flash)
│   ├── deepseek-pro   (DeepSeek V4 Pro)
│   └── openai         (GPT-4o)
│
├── AGENT_PRESETS      ← 5 种 Agent 角色的温度预设
│   ├── router         (temp=0.0)
│   ├── analysis       (temp=0.15)
│   ├── action         (temp=0.5)
│   ├── reflect        (temp=0.0)
│   └── perception     (temp=0.1)
│
├── get_llm(role)      ← 获取指定角色的 LLM 实例
├── test_one_provider() ← 测试单个 provider 连通性
├── test_all_providers()← 测试全部 provider
└── __main__           ← python -m config.llm 直接测试
```

**关键设计决策**：
- 统一 `langchain_openai.ChatOpenAI` 接口 — 所有 provider 通过 OpenAI 兼容 API 调用，代码零切换成本
- API Key 从环境变量读取 — 不硬编码，支持 `.env` 文件
- 连通性自检 — `python -m config.llm` 快速验证配置是否可用

### 4.2 连通性测试

```bash
# 测试当前默认 provider (qwen)
python -m config.llm

# 测试指定 provider
python config/llm.py deepseek
python config/llm.py qwen

# Python 代码测试
python -c "
from config.llm import test_all_providers
results = test_all_providers(['qwen', 'deepseek'])
for name, r in results.items():
    status = '✅' if r['ok'] else '❌'
    print(f'{status} {name}: {r[\"latency_ms\"]:.0f}ms')
"
```

### 4.3 使用方式

```python
# Agent 中通过角色获取 LLM
from config.llm import get_llm

analysis_llm = get_llm("analysis")       # Qwen3-Max, temp=0.15
action_llm   = get_llm("action")          # Qwen3-Max, temp=0.5

# 临时切换 provider
deepseek_analysis = get_llm("analysis", provider="deepseek")

# 不需要在 Agent 代码中写模型名或 API Key
```

---

## 5. 数据管道验证 (Phase 1 已完成)

### 5.1 快速验证

```bash
# 启动 FastAPI 服务
cd data_pipeline
python webhook_server.py

# 另开终端，发送测试数据
python -m data_pipeline.test_data | curl -X POST http://localhost:8000/api/v1/health/sync \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer medical-health-agent-dev-key-2026" \
  -d @-

# 验证数据
curl "http://localhost:8000/api/v1/health/status"
curl "http://localhost:8000/api/v1/health/daily?date=$(date +%Y-%m-%d)"
```

### 5.2 代码状态

| 文件 | 状态 | 说明 |
|------|------|------|
| `data_pipeline/config.py` | ✅ | 全局配置 (DB / API Key / 聚合白名单) |
| `data_pipeline/models.py` | ✅ | Pydantic + SQLAlchemy 双模型 |
| `data_pipeline/database.py` | ✅ | 引擎 + 会话 + 自动建表 |
| `data_pipeline/webhook_server.py` | ✅ | 7 个 API 端点 |
| `data_pipeline/aggregator.py` | ✅ | 日聚合 + 基线计算 |
| `data_pipeline/test_data.py` | ✅ | Tier 1 全覆盖测试数据 |

---

## 6. RAG 知识库验证 (Phase 2 已完成 ✅)

```bash
# 验证 ChromaDB 知识库
python -c "
from rag.retriever import MedicalRetriever
retriever = MedicalRetriever()
docs = retriever.search('小孩发烧39度怎么办？', k=3)
for i, doc in enumerate(docs, 1):
    print(f'[{i}] score={doc[\"score\"]:.3f} | {doc[\"question\"][:60]}...')
"
```

**已完成状态**：
- ✅ 华佗 27.6 万条数据清洗入库
- ✅ ChromaDB `huatuo_medical_qa` collection
- ✅ `MedicalRetriever.search()` 检索接口
- ✅ `MedicalRetriever.format_context()` LLM context 格式化

---

## 7. 验收清单

### 7.1 必须通过

| # | 验收项 | 验证方法 | 状态 |
|---|--------|---------|------|
| 1 | 目录结构完整 | `ls agents/ config/ rag/ data_pipeline/ memory/ prompts/ frontend/ tests/` | ⬜ |
| 2 | Python 依赖安装成功 | `python -c "import fastapi, langchain, chromadb, sqlalchemy, langgraph"` | ⬜ |
| 3 | .env 文件已配置 | `cat .env` 确认有 API Key | ⬜ |
| 4 | LLM 连通 (Qwen) | `python -m config.llm` → ✅ | ⬜ |
| 5 | 数据管道启动 | `python -m data_pipeline.webhook_server` → 无报错 | ⬜ |
| 6 | RAG 检索可用 | `python -c "from rag.retriever import MedicalRetriever; ..."` → 有结果 | ⬜ |

### 7.2 可选

| # | 验收项 | 验证方法 |
|---|--------|---------|
| 7 | LLM 连通 (DeepSeek) | `python config/llm.py deepseek` |
| 8 | 测试数据发送 | `python -m data_pipeline.test_data \| curl ...` |
| 9 | API 端点测试 | `curl http://localhost:8000/api/v1/health/status` |

---

## 8. 下一步 Phase 3

Phase 0 验收通过后，进入 Phase 3: Agent 系统开发。

### Phase 3 开发顺序

```
1. agents/state.py       — AgentState 定义 (消息列表 + 检索结果 + 健康数据)
2. agents/router.py      — 意图路由 (LangGraph 入口节点)
3. prompts/              — 所有 prompt 模板 (路由/分析/自检/行动)
4. agents/boundary.py    — 硬边界拒答模板
5. agents/analysis.py    — Self-RAG (retrieve→generate→reflect→revise) ⭐
6. agents/perception.py  — 健康数据分析
7. agents/action.py      — 对话/建议生成
8. agents/graph.py       — LangGraph StateGraph 编译 & 主入口
```

### 关键文件依赖链

```
config/llm.py  ──→ agents/*.py   (LLM 实例)
rag/retriever.py ──→ agents/analysis.py  (检索接口)
data_pipeline/   ──→ agents/perception.py (健康数据)
```

---

> **Phase 0 完成标志**：`python -m config.llm` 输出 `✅ 连通成功!`，所有验收项通过。
