# Medical-Health-Agent 方案 v2.2

> 2026-05-07 | 纯 API 架构 | Qwen3-Max + RAG + LangGraph | ChromaDB | App 前端
    注：Qwen3-Max后续换成DeepSeek V4
---

## 零、版本变更

| 变更点       | v2.1                    | v2.2                                  | 理由                                |
| --------- | ----------------------- | ------------------------------------- | --------------------------------- |
| 主力 LLM    | DeepSeek V4 Flash       | **Qwen3-Max** (有额度)                   | 先消耗 Qwen 额度，配置分离可随时切              |
| RAG 数据集   | 华佗 + medical finetune   | **仅华佗 27.6 万条**                       | 质量极高 (0.002%废数据)，单数据集够用           |
| Embedding | bge-small-zh-v1.5       | **DashScope text-embedding-v4 (API)** | 已确认，见 Phase2 文档                   |
| 向量库       | ChromaDB (默认)           | **ChromaDB** (含 FAISS 对比)             | 见 §四 对比                           |
| Self-RAG  | 未明确                     | **LangGraph 节点内实现**                   | 意图路由 + 检索 + 生成 + 自检 = 事实 Self-RAG |
| 审查制度      | 分析 Agent 内 safety check | **v2 暂不内置**                           | 附录保留方案供后续迭代                       |
| 对话持久化     | 未定                      | **v2 不实现**                            | 附录保留方案                            |
| 多用户       | 未定                      | **不考虑**                               | 单用户先跑通                            |
| 前端        | Gradio / Telegram       | **React Native Expo App**             | 上一个项目是网页，这次做 App                  |
| 边界策略      | 加免责声明                   | **硬边界：拒绝诊断，建议就医**                     | 产品定位明确                            |

---

## 一、架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                   LangGraph 调度层 (StateGraph)                │
│              意图路由 → Self-RAG 检索增强 → 回答生成           │
│                    全部 LLM 调用: Qwen3-Max API               │
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
              │   Embedding: 本地/API │
              └─────────────────────┘
```

### 关键变化说明

- **LLM 统一用 Qwen3-Max**：你有大量额度，且 Qwen3-Max 中文医疗表现不输 DeepSeek V4 Flash。配置集中在 `config/llm.py`，后续一键切回 DeepSeek
- **Self-RAG**：不是引入第三方库，而是在分析 Agent 内部增加「检索→生成→自检→修正」的循环，LangGraph 的 conditional edge 天然支持
- **硬边界**：凡涉及诊断、处方、症状确诊的问题，直接模板回复："这超出了我的能力范围，建议您前往正规医疗机构就诊。"

---

## 二、数据集处理方案（审核后执行）

### 2.1 源数据

`shibing624/huatuo_medical_qa_sharegpt` — 已缓存在 HF datasets cache

### 2.2 数据格式

```json
{
  "conversations": [
    {"from": "human", "value": "小孩发烧39度怎么办？"},
    {"from": "gpt", "value": "小孩发烧39度属于高热，需要引起重视。以下是建议：\n1. ..."}
  ]
}
```

### 2.3 清洗流程（四步）

```
原始 276,042 条
  │
  ├─ Step 1: 格式校验
  │   丢弃 conversations 为空 / 不包含 human+gpt 的记录
  │   预计: ~0 条丢弃 (huatuo 格式完美)
  │
  ├─ Step 2: 内容质量过滤
  │   丢弃: 回答 < 10 字符 (仅 5 条)
  │   丢弃: 问题或回答包含乱码 / 纯英文 (仅 ~12 条)
  │   预计: ~17 条丢弃
  │
  ├─ Step 3: 去重
  │   相同"问题文本"保留第一条
  │   预计: 少量丢弃 (医学问题重复度低)
  │
  └─ Step 4: 可选截断
       是否截断到 12-15 万条？
       理由 1: 27.6 万条 ChromaDB ≈ 1GB, 检索 ~20ms → 完全可以接受
       理由 2: 更多数据覆盖更多罕见医学问题
       ★ 建议: 先不截断，全量入库。如果检索 > 30ms 再截到 15 万
```

### 2.4 RAG 文档构建策略

```python
# 每条 QA 对构建为一个 ChromaDB document
{
    "id": "huatuo_000001",
    "embedding_text": "小孩发烧39度怎么办？",  # ← 仅用问题做向量化
    "document": "问：小孩发烧39度怎么办？\n答：小孩发烧39度属于高热...",
    "metadata": {
        "question": "小孩发烧39度怎么办？",
        "answer_length": 350,
        "source": "huatuo"
    }
}
```

**为什么只 embed 问题而不是问题+回答？**
- 用户查询是问题 → 用问题检索问题，语义匹配更精准
- 答案中的医学术语噪声会干扰检索方向
- 检索到匹配问题后，完整 QA 作为 context 喂给 LLM

### 2.5 执行脚本设计 (`rag/build_vectordb.py`)

```python
# 伪代码
def build_huatuo_vectordb():
    ds = load_dataset("shibing624/huatuo_medical_qa_sharegpt", split="train")
    records = clean_and_deduplicate(ds)       # Step 1-3
    embedder = get_embedding_model()           # Step: embedding 初始化
    collection = chroma_client.create_collection("huatuo_medical_qa")

    batch_size = 1000
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        questions = [r["question"] for r in batch]
        embeddings = embedder.encode(questions)
        collection.add(
            embeddings=embeddings,
            documents=[r["full_qa"] for r in batch],
            metadatas=[r["metadata"] for r in batch],
            ids=[r["id"] for r in batch],
        )

    print(f"Done: {len(records)} records in ChromaDB")
```

### 2.6 验证标准

| 检查项 | 方法 | 通过标准 |
|--------|------|----------|
| 检索命中 | 用 20 条测试问题查询 | Top-5 至少有 1 条明显相关 |
| 检索延迟 | `time.perf_counter()` 测试 | 均值 < 30ms |
| 入库完整性 | `collection.count()` | = 清洗后记录数 |
| LLM 集成 | 取检索结果 + prompt → Qwen3-Max | 回答引用检索内容 |

> **审核要点**：请确认 (1) 是否全量入库 vs 截断 (2) "仅用问题做 embedding"的策略是否认可 (3) 清洗规则是否足够。

---

## 三、Embedding 选型分析

### 3.1 候选方案

| 方案  | 模型                                | 维度   | 大小     | 推理  | 中文效果  | 延迟     |
| --- | --------------------------------- | ---- | ------ | --- | ----- | ------ |
| A   | DashScope text-embedding-v4 (API) | 1024 | 0 MB   | API | ⭐⭐⭐⭐⭐ | ~100ms |
| B   | BAAI/bge-small-zh-v1.5 (本地 CPU)   | 512  | 24 MB  | CPU | ⭐⭐⭐⭐  | ~30ms  |
| C   | BAAI/bge-base-zh-v1.5 (本地 CPU)    | 768  | 400 MB | CPU | ⭐⭐⭐⭐⭐ | ~80ms  |
| D   | Qwen3-Embedding-0.6B (本地 GPU)     | 1024 | 1.2 GB | GPU | ⭐⭐⭐⭐⭐ | ~20ms  |

### 3.2 适配性分析

**关于 Qwen text-embedding-v4**：这是阿里云 DashScope 的 API 模型（`text-embedding-v4`），不是开源 Qwen 系列。适配方式：

```python
# DashScope text-embedding-v4 调用
import dashscope
dashscope.TextEmbedding.call(
    model="text-embedding-v4",
    input="小孩发烧怎么办？",
)
# 返回 1024 维向量
```

**问题**：
- 每次查询需要一次网络往返 (~100ms)，27.6 万条入库需要 27.6 万次 API 调用 → **不可行**（耗时 + 费用）
- 入库可以用批量 API，但查询时延迟不可接受（检索本身 20ms + API 嵌入 100ms = 120ms）

**修正建议**：入库用 DashScope API（批量），查询用本地模型（实时）。但这样语义空间不统一，不同 embedding 模型不可互换。

### 3.3 推荐方案

```
推荐: 方案 B — BAAI/bge-small-zh-v1.5 (本地 CPU)

理由:
  1. 24MB, pip install 一行搞定，零配置
  2. CPU 推理 ~30ms，比 API 调用快 3 倍
  3. 512 维，27.6 万条向量 ≈ 0.5GB，检索 ~20ms
  4. 中文医疗文本效果足够好 (MTEB Chinese leaderboard 前列)
  5. 完全离线，不消耗 API 额度

如果检索质量不满意 → 升级到方案 C (bge-base-zh, 768维, 400MB)
Qwen3-Embedding (方案 D) 虽然强但 1.2GB 占用太多 CPU/RAM，不推荐用于本地 RAG
```

### 3.4 验证方法

入库后用 20 条测试查询评估 Top-5 召回的相关性。如果不满意，换 bge-base-zh 重建向量库（换 embedding 只需重跑 `build_vectordb.py`，约 15 分钟）。

---

## 四、向量库选型：ChromaDB vs FAISS

### 4.1 对比矩阵

| 维度 | FAISS | ChromaDB |
|------|-------|----------|
| 开发语言 | C++ (Python binding) | Python + Rust |
| 索引类型 | 极丰富 (Flat, IVF, HNSW, PQ...) | HNSW (内置) |
| 持久化 | **需手动实现** (write_index + read_index) | **开箱即用** (自动 persist 到磁盘) |
| 元数据过滤 | 需自建映射表 | **内置** `where` 过滤 |
| 分布式 | 支持 (GPU 加速) | 单机 (Client-Server 模式开发中) |
| 安装 | `pip install faiss-cpu` | `pip install chromadb` |
| 学习曲线 | 中等 (需理解索引类型) | 低 (类 ORM API) |
| 内存占用 | 低 (纯向量) | 中等 (向量 + 元数据 + 文档) |
| 本项目适配 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

### 4.2 关键差异

**FAISS 的优势**：
- 纯向量检索，极致速度（百万级向量 < 10ms）
- 索引类型灵活，可根据场景调优（IVF 牺牲精度换速度）
- GPU 加速支持

**FAISS 的劣势**（对本项目致命）：
- **没有内置持久化**：需手动 `faiss.write_index()` + 自建 ID→文档映射表
- **没有元数据过滤**：无法做 `where source='huatuo'` 这类查询
- 每次重启服务需手动加载索引 + 映射表，代码量大

**ChromaDB 的优势**（对本项目刚好）：
- **自动持久化**：`persist_directory="./data/chroma"` 一行搞定
- **元数据过滤**：`collection.query(where={"answer_length": {"$gt": 100}})` 原生支持
- API 简洁：`add`, `query`, `delete`, `update` 语义清晰
- 嵌入函数内置：可集成 sentence-transformers，自动向量化

### 4.3 结论

```
推荐: ChromaDB

理由:
  1. 你上一个项目用过 FAISS → 这次用 ChromaDB 展示技术多样性 (简历加分)
  2. 持久化开箱即用，不用造轮子 (FAISS 持久化需要写 ~100 行胶水代码)
  3. 元数据过滤让你后续可以做 "按疾病科室过滤" 等高级检索
  4. 27.6 万条量级，ChromaDB HNSW 性能完全够 (~20ms)
  5. Python 原生，跟 LangGraph/FastAPI 技术栈统一

FAISS 更适合的场景: 亿级向量、纯速度优先、需要 GPU 加速
ChromaDB 更适合的场景: 10万-100万级、需要元数据、快速原型
```

---

## 五、Self-RAG 设计（LangGraph 内实现）

### 5.1 什么是 Self-RAG

Self-RAG = 检索 (Retrieve) + 生成 (Generate) + 自我检查 (Self-Critique) + 修正循环。不需要第三方库，LangGraph 的 `conditional_edge` 天然支持。

### 5.2 分析 Agent 的 Self-RAG 流程

```
用户问题
  │
  ▼
┌─────────────────┐
│ Node 1: Router  │  意图识别 → "medical_qa"
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Node 2: Retrieve│  ChromaDB 检索 Top-5
│ (RAG 检索)       │  输出: retrieved_docs
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Node 3: Generate│  Prompt: 问题 + 检索知识 → Qwen3-Max
│ (生成回答)        │  输出: draft_response
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Node 4: Reflect │  对草稿做自检:
│ (自我检查)        │  1. 答案是否有检索依据？ → 是/否
│                  │  2. 是否有编造/幻觉？   → 是/否
│                  │  3. 是否越界诊断？      → 是/否
└────────┬────────┘
         │
    ┌────┴────┐
    │ 条件判断  │
    └────┬────┘
         │
    ┌────┴─────────────┐
    │                  │
    ▼                  ▼
 通过              需要修正
    │                  │
    ▼                  ▼
┌──────────┐   ┌──────────────┐
│ 直接输出  │   │ Node 5: Revise│  针对性修正
└──────────┘   │ 重新生成       │
               └──────┬───────┘
                      │
                      ▼
               ┌──────────────┐
               │ 输出 + 免责    │
               └──────────────┘
```

### 5.3 Graph 实现要点

```python
# agents/graph.py
def build_analysis_graph():
    graph = StateGraph(AnalysisState)

    graph.add_node("retrieve", retrieve_medical_knowledge)
    graph.add_node("generate", generate_response)       # Qwen3-Max
    graph.add_node("reflect", self_reflection)           # Qwen3-Max (轻量 prompt)
    graph.add_node("revise", revise_response)            # Qwen3-Max

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "reflect")

    graph.add_conditional_edges("reflect", check_reflection, {
        "pass": END,              # 通过 → 直接输出
        "retry": "revise",        # 需修正 → 修正后输出
        "reject": "reject_handler" # 越界 → 拒答模板
    })

    graph.add_edge("revise", END)
    return graph.compile()
```

### 5.4 Self-Reflection Prompt

```
你是医疗回答的质检员。请审查以下回答：

## 检索到的参考知识
{retrieved_knowledge}

## AI 生成的回答
{draft_response}

请判断：
1. 回答是否基于参考知识？（回答是/否，如否，指出哪里编造了）
2. 回答是否涉及明确诊断或处方？（回答是/否，如是，指出具体语句）
3. 回答是否遗漏了就医建议？（回答是/否）

仅输出 JSON: {"pass": true/false, "issues": "...", "action": "pass|retry|reject"}
```

### 5.5 硬边界模板

```python
# agents/boundary.py
REJECT_TEMPLATES = {
    "diagnosis": "我无法进行医学诊断。{issue_description}建议您前往正规医疗机构就诊，由专业医生进行评估。",
    "prescription": "我无法开具处方或推荐具体药物剂量。用药方案需要医生根据您的具体情况制定。",
    "emergency": "您描述的症状可能需要紧急医疗处理。请立即拨打120或前往最近的急诊科。",
}
```

---

## 六、LLM 配置分离设计

### 6.1 文件结构

```
config/
├── __init__.py
└── llm.py          # 所有 LLM 配置集中管理，Agent 代码不直接写模型名
```

### 6.2 `config/llm.py` 设计

```python
"""LLM 配置中心 — 切换模型只需改这个文件"""
from langchain_qwen import ChatQwen  # 或 langchain_deepseek

# ── 切换开关 ──────────────────────────────────────────
CURRENT_PROVIDER = "qwen"  # "qwen" | "deepseek"

# ── 模型配置 ──────────────────────────────────────────
LLM_CONFIGS = {
    "qwen": {
        "chat_model": ChatQwen,
        "model_name": "qwen3-max",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "env_key": "DASHSCOPE_API_KEY",
    },
    "deepseek": {
        "chat_model": "langchain_deepseek.ChatDeepSeek",
        "model_name": "deepseek-chat",  # V4 Flash
        "api_base": "https://api.deepseek.com/v1",
        "env_key": "DEEPSEEK_API_KEY",
    },
}

# ── 各 Agent 的 LLM 实例 ─────────────────────────────
import os

cfg = LLM_CONFIGS[CURRENT_PROVIDER]

# 路由 Agent — 极低温度，只做分类
router_llm = cfg["chat_model"](
    model=cfg["model_name"],
    temperature=0.0,
    max_tokens=50,
    api_key=os.getenv(cfg["env_key"]),
)

# 分析 Agent — 低温度，需要可靠性
analysis_llm = cfg["chat_model"](
    model=cfg["model_name"],
    temperature=0.15,
    max_tokens=2048,
    api_key=os.getenv(cfg["env_key"]),
)

# 行动 Agent — 中等温度，需要自然对话
action_llm = cfg["chat_model"](
    model=cfg["model_name"],
    temperature=0.5,
    max_tokens=2048,
    api_key=os.getenv(cfg["env_key"]),
)

# 自检 Agent — 极低温度，只做校验
reflect_llm = cfg["chat_model"](
    model=cfg["model_name"],
    temperature=0.0,
    max_tokens=200,
    api_key=os.getenv(cfg["env_key"]),
)
```

### 6.3 切换方式

```bash
# .env 文件
QWEN_API_KEY=sk-xxx
# 或
DEEPSEEK_API_KEY=sk-xxx

# 切模型只需改 config/llm.py 的一行: CURRENT_PROVIDER = "deepseek"
```

### 6.4 Qwen3-Max 适配注意

Qwen3-Max 通过 DashScope 兼容 OpenAI API 格式，`langchain-qwen` 或直接用 `ChatOpenAI` 均可：

```bash
pip install langchain-qwen dashscope
```

```python
# 备选：直接用 OpenAI 兼容接口
from langchain_openai import ChatOpenAI

qwen_llm = ChatOpenAI(
    model="qwen3-max",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
)
```

---

## 七、前端 App 方案对比

### 7.1 候选方案

| 方案 | 语言 | 跨平台 | 热更新 | 学习曲线 | 包体积 | 生态 |
|------|------|--------|--------|----------|--------|------|
| **React Native (Expo)** | JS/TS | iOS + Android | ✅ OTA | 低 (你熟悉JS) | ~15MB | ⭐⭐⭐⭐⭐ |
| Flutter | Dart | iOS + Android + Web | ❌ | 中 | ~20MB | ⭐⭐⭐⭐ |
| Kotlin Multiplatform | Kotlin | iOS + Android | ❌ | 高 | ~10MB | ⭐⭐⭐ |
| PWA (渐进式Web) | JS/TS | 全平台 | ✅ 天然 | 极低 | 0 | ⭐⭐⭐⭐⭐ |

### 7.2 推荐：React Native (Expo)

**理由**：
- 你上一个项目做网页 → JS/TS 技能直接复用
- Expo 提供开箱即用的路由、通知、健康数据集成
- 与 FastAPI 后端通过 REST API 通信，架构清晰
- 社区成熟，Chat UI 组件现成 (react-native-gifted-chat)

### 7.3 App 架构

```
┌──────────────────────┐
│   React Native App    │
│   (Expo Router)       │
├──────────────────────┤
│  Screens:             │
│  ├── ChatScreen       │  ← 主对话界面
│  ├── HealthDashboard  │  ← 健康数据图表
│  ├── WeeklyReport     │  ← 周报展示
│  └── SettingsScreen   │  ← LLM 切换 / 通知设置
├──────────────────────┤
│  Services:            │
│  ├── api.ts           │  ← FastAPI 通信
│  ├── chat.ts          │  ← 对话状态管理
│  └── health.ts        │  ← 健康数据获取
└──────────────────────┘
         │ HTTP
         ▼
┌──────────────────────┐
│   FastAPI 后端         │
│   localhost:8000      │
└──────────────────────┘
```

### 7.4 PWA 作为快速启动选项

如果不想立刻投入 App 开发，可以先用 PWA（`next-pwa` + Vercel），体验接近原生 App（可添加到主屏幕、离线缓存），后续再迁移到 React Native。架构层面 FastAPI 后端不变。

---

## 八、Phase 规划总览

### Phase 0 — 项目搭建 (Day 1)

```
├── git init, .gitignore
├── 目录结构创建 (agents/, rag/, config/, data_pipeline/, frontend/)
├── pip install 依赖
├── config/llm.py (Qwen3-Max 配置)
└── .env (API Key)
```

### Phase 1 — 数据管道 (Week 1-2)

```
├── data_pipeline/ (Apple Health webhook + 聚合)
│   复用 Phase1-Apple-Health数据管道实施方案.md 全部代码
└── 本次不修改，独立推进
```

### Phase 2 — RAG 知识库 (Week 2)

> **详细方案**：见 [`Phase2-医疗RAG知识库构建方案.md`](./Phase2-医疗RAG知识库构建方案.md)

```
├── 审核 §二 的数据清洗方案
├── rag/build_vectordb.py (合并两文件 + 清洗 + DashScope v4 嵌入 + ChromaDB)
├── rag/retriever.py (MedicalRetriever 检索接口)
└── rag/test_retrieval.py (20 条测试查询，评估召回质量)
```

### Phase 3 — Agent 系统 (Week 2-4) ⭐ 核心

```
├── agents/state.py (AgentState 定义)
├── agents/router.py (意图路由)
├── agents/analysis.py (Self-RAG 流程: retrieve→generate→reflect→revise)
├── agents/perception.py (健康数据分析)
├── agents/action.py (对话/建议生成)
├── agents/graph.py (LangGraph StateGraph 编译)
├── agents/boundary.py (硬边界拒答)
└── prompts/ (所有 prompt 模板)
```

### Phase 4 — 长期记忆 (Week 4-5)

```
├── memory/vector_store.py (ChromaDB 摘要记忆)
├── memory/weekly_summary.py (周报生成)
└── memory/trend.py (趋势查询)
```

### Phase 5 — App 前端 (Week 5-7)

```
├── React Native Expo 项目初始化
├── ChatScreen (对话界面)
├── HealthDashboard (健康图表)
├── SettingsScreen
└── 与 FastAPI 后端联调
```

### Phase 6 — 集成测试 (Week 7-8)

```
├── 端到端测试
├── RAG 检索质量评估 (50 条医学问题)
├── Self-RAG 修正率统计
└── 性能优化 (检索延迟、API 超时处理)
```

---

## 九、成本估算

| 阶段 | 费用来源 | 金额 |
|------|----------|------|
| Phase 0-2 | Qwen Embedding API (入库27.6万次) 或本地免费 | 0 元 |
| Phase 3 开发 | Qwen3-Max API 测试调用 | < 10 元 (有额度) |
| Phase 4-5 | Qwen3-Max API 测试调用 | < 10 元 (有额度) |
| 上线后 | Qwen3-Max API (~100次/天) | ~0 元 (额度覆盖) |
| 上线后 (切 DeepSeek) | DeepSeek V4 Flash (~100次/天) | ~26 元/月 |

---

## 十、当前目录结构

```
Medical-Health-Agent/
├── Medical-Health-Agent方案v1.1.md          ← 保留 (架构起源)
├── Medical-Health-Agent方案v1.2-本地RAG方案分析.md ← 保留 (RAG参考)
├── Medical-Health-Agent方案v1.3-MedicalGPT训练部署方案.md ← 保留 (训练方案, 已弃用)
├── Medical-Health-Agent方案v2.0.md          ← 保留 (v2.0, 已更新)
├── Medical-Health-Agent方案v2.2.md          ← ★ 当前版本
├── Phase1-Apple-Health数据管道实施方案.md     ← 保留 (Phase 1 执行)
├── sft微调对话全记录-2026-05-07.md           ← 保留 (训练日志)
├── 算力问题汇总.md                            ← 保留 (问题记录)
├── prepare_data.py                           ← SFT 数据准备 (本方案不再使用)
├── rag/
│   ├── analyze_datasets.py                  ← 数据集分析脚本
│   ├── build_vectordb.py                    ← (待创建) 向量库构建
│   └── retriever.py                         ← (待创建) 检索接口
├── agents/                                   ← (待创建)
├── config/
│   └── llm.py                               ← (待创建) LLM 配置中心
├── data_pipeline/                            ← (复用 Phase 1)
├── memory/                                   ← (待创建)
└── frontend/                                 ← (待创建) React Native
```

---

## 十一、附录：未来迭代方案

### A. 对话历史持久化方案

| 方案 | 实现 | 优点 | 缺点 |
|------|------|------|------|
| A1: SQLite 存聊天记录 | 每条对话存 `(session_id, role, content, timestamp)` | 简单，已有 SQLite | 无语义检索 |
| A2: ChromaDB 对话记忆 | 对话 embed 后存 ChromaDB，检索相关历史 | 语义检索，技术栈统一 | 额外存储 |
| A3: LangGraph SqliteSaver | `graph.compile(checkpointer=SqliteSaver(conn))` | 框架原生，自动管理 | 灵活性低 |

**v3 建议**：A1 + A2 混合。SQLite 存全量对话（按时间拉取），ChromaDB 存近期对话摘要（语义检索）。

### B. 安全审查制度方案

| 方案 | 实现 | 开销 | 效果 |
|------|------|------|------|
| B1: 关键词硬过滤 | regex 检测 "确诊"、"处方"、"吃药" → 拒答 | 0 延迟 | 60% 覆盖 |
| B2: 同模型 Self-Reflection | 当前 Self-RAG 的 reflect 步骤 | 1 次额外 API 调用 | 85% 覆盖 |
| B3: 独立 QA 审查模型 | 用另一个 LLM 专门做安全性审查 | 1 次额外 API 调用 | 95% 覆盖 |
| B4: 内容安全 API | 阿里云/腾讯云内容安全 API | ~0.01 元/次 | 98% 覆盖 |

**v3 建议**：B1 (实时, 0 成本) + B2 (已有, 不增加调用)。敏感场景用 B4 做兜底。

### C. 模型切换方案

当前 `config/llm.py` 已支持 Qwen ↔ DeepSeek 一键切换。未来可扩展：
- 按 Agent 角色用不同模型（路由用 Flash，行动用 Pro）
- 按场景降级（API 超时 → 本地轻量 prompt 兜底）
- 成本追踪（各 Agent token 用量统计）

---

> **下一步**：请审阅 §二 的数据处理方案和 §五 的 Self-RAG 设计。确认后我开始写 `rag/build_vectordb.py` 和 `config/llm.py` 的执行代码。
