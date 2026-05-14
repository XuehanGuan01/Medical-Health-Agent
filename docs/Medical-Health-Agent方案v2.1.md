# Medical-Health-Agent 方案 v2.1

> 2026-05-07 | 纯 API 架构 | DeepSeek V4 Flash + RAG + LangGraph | 无本地模型依赖

---

## 零、v2.0 → v2.1 变更说明

| 变更点 | v2.0 | v2.1 |
|--------|------|------|
| 本地模型 | Qwen3.5-4B Q4_K_M 兜底 | **完全移除**，全部走 DeepSeek API |
| SFT 训练 | 2×4090 双卡训练 | **移除**（时间/算力/本地表现不划算） |
| OPD 蒸馏 | 可选 | **移除** |
| 量化部署 | GGUF + Ollama | **移除** |
| 隐私/离线 | 本地模型兜底 | 隐私模式 → 不记录数据；离线 → 降级提示 |
| RAG | ChromaDB (本地) | **保留** — CPU embedding，零 GPU 依赖 |
| Agent 架构 | 3 层 Agent | **保留** — 全部走 DeepSeek API |

**核心思路**：RAG 检索本地跑（CPU 即可），LLM 推理全部走 DeepSeek API。去掉模型训练/部署的全链路复杂度，聚焦 Agent 逻辑和用户体验。

---

## 一、架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                   LangGraph 调度层 (StateGraph)                │
│               Router → 意图识别 → 路由分发 → 结果聚合           │
└──────┬─────────────────┬─────────────────┬───────────────────┘
       │                 │                 │
       ▼                 ▼                 ▼
┌──────────────┐ ┌───────────────┐ ┌───────────────┐
│  感知 Agent   │ │  分析 Agent    │ │  行动 Agent    │
│              │ │               │ │               │
│ Apple Health │ │ 医疗问答       │ │ 对话/提醒/     │
│ 数据分析     │ │ + RAG 检索     │ │ 建议推送      │
│              │ │               │ │               │
│ DS V4 Flash  │ │ DS V4 Flash    │ │ DS V4 Pro     │
│ temp=0.1     │ │ temp=0.15      │ │ temp=0.3-0.7  │
└──────┬───────┘ └───────┬───────┘ └───────┬───────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │   共享 RAG 知识库     │
              │   ChromaDB (本地)    │
              │   22万条 医疗 QA     │
              │   Embedding: CPU 运行 │
              └─────────────────────┘
```

### 模型分工

| Agent    | 模型                | temperature | 职责                    |
| -------- | ----------------- | ----------- | --------------------- |
| 感知 Agent | DeepSeek V4 Flash | 0.1         | 结构化数据 → 异常报告，低温度保一致性  |
| 分析 Agent | DeepSeek V4 Flash | 0.15        | 医疗问答 + RAG 上下文，低温度防幻觉 |
| 行动 Agent | DeepSeek V4 Pro   | 0.3-0.7     | 对话生成、建议拟人化、叙事输出       |

**为什么分析 Agent 也用 Flash 而不是 Pro？** 医疗问答场景 RAG 召回的知识已经提供了事实锚点，Flash 的推理能力足够完成知识整合和问答。Pro 留给需要长文本理解和对话连贯性的行动 Agent。

---

## 二、Phase 0：项目基础搭建

**周期**：1-2 天 | **费用**：0 元

### 2.1 技术栈确定

| 层级 | 技术 | 版本 | 用途 |
|------|------|------|------|
| Agent 编排 | LangGraph | ≥0.2.0 | StateGraph 构建 |
| LLM 调用 | langchain + langchain-deepseek | latest | DeepSeek API 封装 |
| 向量库 | ChromaDB | ≥0.5.0 | 医疗知识 RAG |
| Embedding | BAAI/bge-small-zh-v1.5 | — | CPU 本地向量化 |
| 后端 | FastAPI | ≥0.115 | API 服务 |
| 数据存储 | SQLite | — | Phase 1 数据；后续迁移 PG |
| 前端 | Gradio | ≥4.0 | 初期 UI |
| Python | 3.11+ | — | |

### 2.2 项目目录结构

```
Medical-Health-Agent/
├── agents/                      # LangGraph Agent 定义
│   ├── __init__.py
│   ├── state.py                 # AgentState 状态定义
│   ├── graph.py                 # StateGraph 主图构建
│   ├── perception.py            # 感知 Agent 节点
│   ├── analysis.py              # 分析 Agent 节点
│   ├── action.py                # 行动 Agent 节点
│   └── router.py                # 意图识别 + 路由
├── rag/                         # RAG 知识库
│   ├── __init__.py
│   ├── build_vectordb.py        # 构建向量库
│   ├── retriever.py             # 检索接口
│   └── download_data.py         # 数据集下载
├── data_pipeline/               # Phase 1: Apple Health 数据管道
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── database.py
│   ├── webhook_server.py
│   ├── aggregator.py
│   └── test_data.py
├── prompts/                     # Prompt 模板
│   ├── perception.yaml
│   ├── analysis.yaml
│   ├── action.yaml
│   └── safety.yaml
├── memory/                      # Phase 4: 长期记忆
│   ├── __init__.py
│   ├── vector_store.py
│   └── weekly_summary.py
├── frontend/                    # Phase 5: UI
│   └── gradio_app.py
├── config.py                    # 全局配置 (API Key, DB URL 等)
├── requirements.txt
└── README.md
```

### 2.3 依赖清单 (`requirements.txt`)

```txt
fastapi>=0.115
uvicorn[standard]>=0.34
sqlalchemy>=2.0
pydantic>=2.10
python-dateutil>=2.9
numpy>=2.2
langgraph>=0.2.0
langchain>=0.3
langchain-deepseek>=0.1
chromadb>=0.5
sentence-transformers>=3.0
datasets>=3.0
requests>=2.32
gradio>=4.0
```

---

## 三、Phase 1：Apple Health 数据管道

**周期**：1-2 周 | **依赖**：Phase 0 | **费用**：0 元（本地运行）

### 3.1 目标

实现 Apple Health 数据从 iPhone → 本地数据库的自动同步，构建数据聚合层，为感知 Agent 提供结构化输入。本阶段不涉及任何 LLM。

### 3.2 数据流

```
Health Auto Export App (iOS, 每 30min)
  → POST /api/v1/health/sync (ngrok 内网穿透)
  → FastAPI Webhook (Pydantic 校验)
  → SQLite: raw_health_samples 表
  → 触发器: aggregate_daily_metrics()
  → SQLite: daily_metrics 表 (日聚合)
  → API: GET /api/v1/health/daily?date=2026-05-07
```

### 3.3 涉及的健康指标

| 类别 | 指标 | 采集频率 |
|------|------|----------|
| 心脏 | 心率 (heart_rate) | ~每 5 分钟 |
| 心脏 | 静息心率 (resting_heart_rate) | 每日 |
| 心脏 | 心率变异性 HRV (heart_rate_variability) | ~每小时 |
| 活动 | 步数 (step_count) | ~每小时 |
| 活动 | 活跃能量 (active_energy) | 每日 |
| 睡眠 | 睡眠分析 (sleep_analysis) | 每日 |
| 呼吸 | 血氧 (oxygen_saturation) | 间歇 |
| 运动 | 训练记录 (workouts) | 按次 |

### 3.4 数据库表设计

```sql
-- 原始数据表
raw_health_samples (
    id, metric_type, value, unit,
    start_time, end_time, source, device,
    received_at, extra
)

-- 日聚合表
daily_metrics (
    id, date, metric_type,
    avg_value, min_value, max_value,
    stddev_value, total_value,
    sample_count, unit, created_at
)

-- 同步日志
sync_log (
    id, received_at,
    metrics_count, data_points_count,
    workouts_count, status, error_message
)
```

### 3.5 聚合逻辑

```
心率 (每 5 分钟, ~288 条/天) → 日: avg/min/max/stddev
HRV  (每 1 小时, ~24 条/天)   → 日: avg/min/max/stddev
步数 (每 1 小时, ~24 条/天)   → 日: total(总和)
睡眠 (1-2 条/天)              → 日: total_hours, deep_hours, rem_hours
```

### 3.6 iOS 端配置

- 安装 **Health Auto Export** (免费版，150+ 指标)
- 配置 Automation → API Export → POST JSON
- URL 指向 ngrok 暴露的公网地址
- 30 分钟自动同步一次

### 3.7 关键产出

| 产出 | 说明 |
|------|------|
| `data_pipeline/webhook_server.py` | FastAPI 接收端点 |
| `data_pipeline/aggregator.py` | 聚合 + `compute_baseline()` 个人基线计算 |
| `data_pipeline/test_data.py` | 模拟数据生成器（无 iPhone 时调试用） |
| `data/health.db` | SQLite 数据库 |

> **详细实现代码**参见 `Phase1-Apple-Health数据管道实施方案.md`，该文档已包含完整的 Pydantic 模型、FastAPI 路由、聚合逻辑和测试脚本。

---

## 四、Phase 2：RAG 知识库

**周期**：3-5 天 | **依赖**：Phase 0 | **费用**：0 元（本地 CPU）

### 4.1 目标

构建本地医疗知识向量库，为分析 Agent 提供检索增强能力。**全部在 CPU 上运行，不占用 GPU。**

### 4.2 数据集

| 数据集 | 大小 | 用途 |
|--------|------|------|
| `shibing624/huatuo_medical_qa_sharegpt` | 22 万条中文医疗 QA | 主力 RAG 知识源 |
| `shibing624/medical` (finetune 子集) | ~70 万条 | 可选扩充（如检索质量不够） |

**推荐先用 22 万条华佗数据集**，质量高、格式统一、量级适中。

### 4.3 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 向量库 | ChromaDB (persistent) | 轻量，HNSW 索引，< 50ms 检索 |
| Embedding | BAAI/bge-small-zh-v1.5 | 24MB，512 维，CPU < 50ms |
| 文档构建 | 仅用问题做 embedding | 用问题检索问题，避免答案噪声干扰 |

### 4.4 检索策略

```python
# 双阶段检索：粗筛 → 精排
def retrieve_medical_knowledge(query: str, k: int = 5) -> list[Document]:
    # Stage 1: 向量相似度粗筛 top-K×3
    candidates = collection.query(query_embedding, n_results=k*3)

    # Stage 2: 用 Cross-Encoder 精排（可选，初期跳过）
    # 直接用 ChromaDB 的 distance score，阈值过滤
    results = [c for c in candidates if c["distance"] < threshold]

    return results[:k]
```

### 4.5 存储评估

```
22万条 × 512维 × 4字节(float32) = 450MB （向量）
22万条 × 平均500字符 × 3字节   = 330MB （文本）
ChromaDB HNSW 索引               ≈ 150MB
─────────────────────────────────────────
磁盘总计                          ≈ 1GB
运行时内存                        ≈ 600-800MB
```

**16GB RAM 绰绰有余**。

### 4.6 关键产出

| 产出 | 说明 |
|------|------|
| `rag/download_data.py` | 从 HF 下载华佗数据集 |
| `rag/build_vectordb.py` | 构建 ChromaDB 向量库 |
| `rag/retriever.py` | 检索接口 + 格式化 RAG context |
| `data/chroma/` | 持久化向量库目录 |

---

## 五、Phase 3：LangGraph Agent 系统

**周期**：2-3 周 | **依赖**：Phase 2 (RAG 可先 mock) | **费用**：DeepSeek API 调用（开发期 < 10 元）

### 5.1 目标

用 LangGraph StateGraph 构建三层 Agent 协作系统，实现从用户输入 → 意图识别 → Agent 路由 → RAG 检索 → LLM 推理 → 结果返回的完整链路。

### 5.2 AgentState 设计

```python
# agents/state.py
from typing import TypedDict, Optional, Annotated
from langgraph.graph.message import add_messages

class HealthMetrics(TypedDict):
    """Phase 1 输出的日聚合数据"""
    date: str
    heart_rate: dict       # {avg, min, max, stddev, baseline_mean, deviation_pct}
    hrv: dict
    steps: dict
    sleep: dict
    active_energy: dict

class AgentState(TypedDict):
    # 用户输入
    query: str
    messages: Annotated[list, add_messages]  # 对话历史

    # 路由
    intent: str            # "health_data" | "medical_qa" | "general_chat" | "emergency"
    route: str             # "perception" | "analysis" | "action"

    # 上下文
    health_metrics: Optional[HealthMetrics]
    retrieved_docs: Optional[list[str]]
    personal_context: Optional[str]  # 个人基线、历史趋势

    # 输出
    response: str
    source: str            # "deepseek_flash" | "deepseek_pro"
    safety_level: str      # "normal" | "caution" | "emergency"
```

### 5.3 Graph 拓扑

```python
# agents/graph.py
from langgraph.graph import StateGraph, END

def build_health_agent_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("router", intent_router)           # 意图识别
    graph.add_node("perception", perception_agent)    # 健康数据分析
    graph.add_node("analysis_retrieve", retrieve_rag) # RAG 检索
    graph.add_node("analysis", analysis_agent)        # 医疗问答
    graph.add_node("action", action_agent)            # 对话/建议
    graph.add_node("emergency", emergency_handler)    # 紧急处理

    # 入口
    graph.set_entry_point("router")

    # 条件路由
    graph.add_conditional_edges("router", route_by_intent, {
        "health_data": "perception",
        "medical_qa":  "analysis_retrieve",
        "general_chat": "action",
        "emergency":   "emergency",
    })

    # 边
    graph.add_edge("perception", "action")            # 分析完 → 生成建议
    graph.add_edge("analysis_retrieve", "analysis")   # RAG → LLM
    graph.add_edge("analysis", "action")
    graph.add_edge("action", END)
    graph.add_edge("emergency", END)

    return graph.compile()
```

### 5.4 各节点详细设计

#### Router 节点（意图识别）

```python
# agents/router.py
INTENT_PROMPT = """你是一个医疗 Agent 系统的意图路由器。
分析用户输入，判断意图属于以下哪一类：

1. health_data — 用户询问自己的 Apple Health 健康数据（心率、睡眠、运动等）
2. medical_qa — 用户提出医疗/健康相关问题（症状、药物、疾病等）
3. general_chat — 日常对话、问候、非医疗话题
4. emergency — 用户描述紧急症状（胸痛、呼吸困难、严重外伤、意识丧失等）

仅回复意图标签，不要有其他内容。"""

def intent_router(state: AgentState) -> AgentState:
    response = deepseek_flash(INTENT_PROMPT, state["query"], temperature=0.0)
    state["intent"] = response.strip()
    return state

def route_by_intent(state: AgentState) -> str:
    mapping = {
        "health_data": "health_data",
        "medical_qa": "medical_qa",
        "general_chat": "general_chat",
        "emergency": "emergency",
    }
    return mapping.get(state["intent"], "general_chat")
```

#### 感知 Agent 节点

```python
# agents/perception.py
PERCEPTION_PROMPT = """你是私人健康顾问。基于以下今日数据给出分析：

## 今日健康数据
- 心率: 均值 {hr_avg} bpm，范围 {hr_min}-{hr_max}，标准差 {hr_std}
  偏离个人30天基线 {hr_deviation}%
- HRV: 今日 {hrv_avg} ms，基线 {hrv_baseline_mean} ± {hrv_baseline_std} ms
- 步数: 今日 {steps_total} 步
- 睡眠: 总时长 {sleep_total}h，深度睡眠 {sleep_deep}h，REM {sleep_rem}h
- 运动: 活跃能量 {energy} kJ，运动时长 {exercise} min

## 个人基线参考
{baseline_context}

请输出:
1. 今日状态总结 (1句话)
2. 需要关注的点 (如有，列出具体指标偏离)
3. 饮食建议 (基于今日消耗)
4. 明日运动建议

重要: 你的分析仅供参考，不能替代专业医疗诊断。"""

def perception_agent(state: AgentState) -> AgentState:
    # 1. 从 DB 拉今日指标 + 基线
    metrics = fetch_daily_metrics(date.today())
    baseline = compute_baselines(days=30)

    # 2. 组装 prompt
    prompt = PERCEPTION_PROMPT.format(
        hr_avg=metrics["heart_rate"]["avg"],
        # ... 其他字段
        baseline_context=format_baseline(baseline),
    )

    # 3. 调 DeepSeek V4 Flash
    analysis = deepseek_flash(prompt, temperature=0.1)

    state["health_metrics"] = metrics
    state["response"] = analysis
    state["source"] = "deepseek_flash"
    return state
```

#### 分析 Agent 节点（RAG + 医疗问答）

```python
# agents/analysis.py
ANALYSIS_SYSTEM = """你是专业的医疗健康助手。请基于以下检索到的医学知识回答用户问题。

## 参考知识
{retrieved_knowledge}

## 回答准则
1. 回答应基于参考知识，不要编造
2. 如果参考知识不足，诚实说明
3. 强调回答仅供参考，不能替代专业医生诊断
4. 遇到紧急症状，优先建议立即就医
5. 不要开具处方或推荐具体药物剂量
6. 保持专业、温和、共情的语气"""

MEDICAL_SAFETY_CHECK = """检查以下回复是否存在风险：
1. 是否包含明确的药物处方或剂量？
2. 是否可能被误解为诊断结论？
3. 是否遗漏了就医建议？
如有风险，请修正回复。"""

def analysis_agent(state: AgentState) -> AgentState:
    # 1. RAG 检索
    docs = retriever.search(state["query"], k=5)
    knowledge = format_rag_context(docs)

    # 2. LLM 生成
    response = deepseek_flash(
        system=ANALYSIS_SYSTEM.format(retrieved_knowledge=knowledge),
        user=state["query"],
        temperature=0.15,
    )

    # 3. 安全审查（轻量，同一模型快速校验）
    safety_check = deepseek_flash(MEDICAL_SAFETY_CHECK + response, temperature=0.0)
    if "风险" in safety_check or "修正" in safety_check:
        response = safety_check  # 或用修正版

    state["retrieved_docs"] = [d.content for d in docs]
    state["response"] = response
    state["source"] = "deepseek_flash"
    state["safety_level"] = assess_safety(response)
    return state
```

#### 行动 Agent 节点

```python
# agents/action.py
ACTION_SYSTEM = """你是一个温暖、专业的私人健康管家。

## 你的能力
- 基于健康数据给出生活化建议
- 将医学分析转化为人性化的日常语言
- 维护用户长期健康档案和趋势追踪
- 适时提醒和鼓励

## 对话风格
- 像朋友一样亲切但不失专业
- 用"你"称呼用户
- 积极正面，但不过度承诺
- 涉及医疗问题时始终提醒专业边界

## 当前上下文
用户健康数据摘要: {health_summary}
上一轮分析结果: {analysis_result}"""

def action_agent(state: AgentState) -> AgentState:
    # 用 Pro 模型获得更好的对话体验
    response = deepseek_pro(
        system=ACTION_SYSTEM.format(
            health_summary=summarize_metrics(state.get("health_metrics")),
            analysis_result=state.get("response", ""),
        ),
        messages=state["messages"],
        temperature=0.5,
    )

    state["response"] = response
    state["source"] = "deepseek_pro"
    return state
```

### 5.5 安全机制

| 机制 | 实现 | 触发条件 |
|------|------|----------|
| 紧急词检测 | 关键词匹配 (regex) → 直接走 emergency handler | "胸痛"、"呼吸困难"、"大出血" 等 |
| 安全审查 | 分析 Agent 输出后用同模型做 safety check | 所有 medical_qa 回复 |
| 免责声明 | 强制追加后缀 | 所有医疗相关输出 |
| 处方拒绝 | Prompt 约束 + 输出检测 | 检测到药物名称 + 剂量模式 |

### 5.6 关键产出

| 产出 | 说明 |
|------|------|
| `agents/state.py` | AgentState 定义 |
| `agents/graph.py` | StateGraph 构建 + 编译 |
| `agents/router.py` | 意图识别 + 路由 |
| `agents/perception.py` | 感知 Agent (健康数据) |
| `agents/analysis.py` | 分析 Agent (医疗 QA + RAG + safety) |
| `agents/action.py` | 行动 Agent (对话/建议) |
| `prompts/*.yaml` | Prompt 模板集中管理 |

---

## 六、Phase 4：长期记忆与健康趋势

**周期**：1-2 周 | **依赖**：Phase 3 基础可用 | **费用**：API 调用

### 6.1 目标

让 Agent 记住用户的健康历史，实现趋势追踪和周报/月报生成。

### 6.2 多层记忆设计

```
┌─────────────────────────────────────┐
│  Layer 1: 对话记忆 (LangGraph Memory) │
│  最近 N 轮对话上下文                  │
│  存储: LangGraph MemorySaver         │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Layer 2: 健康摘要记忆 (Vector Store) │
│  每周生成一次健康摘要 → embedding     │
│  "用户张三 2026年5月第一周 HRV偏低"    │
│  存储: ChromaDB (独立 collection)    │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Layer 3: 结构化趋势 (SQL)            │
│  月度/季度统计指标                     │
│  存储: daily_metrics 表的聚合查询     │
└─────────────────────────────────────┘
```

### 6.3 周报生成

```python
# memory/weekly_summary.py
def generate_weekly_report(db, user_id, week_start, week_end):
    """用 DeepSeek 生成一周健康叙事"""
    # 1. 从 DB 拉 7 天聚合数据
    week_data = fetch_week_metrics(db, week_start, week_end)

    # 2. 组装数据 → Prompt
    prompt = WEEKLY_NARRATIVE_PROMPT.format(data=week_data)

    # 3. DeepSeek V4 Pro 生成叙事
    narrative = deepseek_pro(prompt, temperature=0.6)

    # 4. Embedding → 存入向量库（供未来查询）
    narrative_embedding = embedding_model.encode(narrative)
    memory_collection.add(
        embeddings=[narrative_embedding],
        documents=[narrative],
        metadatas=[{"week": week_start, "type": "weekly_summary"}],
    )

    return narrative
```

### 6.4 趋势查询

```python
def query_health_trend(query: str):
    """查询长期趋势：'我这三个月的压力水平变化趋势是什么？'"""
    # 1. 从向量库检索相关周报
    relevant_summaries = memory_collection.query(query, n_results=5)

    # 2. 从 SQL 拉结构化趋势数据
    trend_data = compute_trend(db, metric="hrv", months=3)

    # 3. 合并 → LLM 生成答案
    return deepseek_pro(prompt_with_context(query, relevant_summaries, trend_data))
```

### 6.5 关键产出

| 产出 | 说明 |
|------|------|
| `memory/vector_store.py` | ChromaDB 摘要记忆 |
| `memory/weekly_summary.py` | 周报生成 + embedding 存储 |
| `memory/trend.py` | 趋势查询 |

---

## 七、Phase 5：前端与交互

**周期**：1-2 周 | **依赖**：Phase 3 可调用 | **费用**：0 元

### 7.1 初期方案：Gradio

```python
# frontend/gradio_app.py
import gradio as gr
from agents.graph import build_health_agent_graph

graph = build_health_agent_graph()

def chat(message, history):
    state = {"query": message, "messages": history}
    result = graph.invoke(state)
    return result["response"]

with gr.Blocks(title="Medical-Health-Agent") as demo:
    gr.Markdown("# 私人健康管家")
    chatbot = gr.Chatbot()
    msg = gr.Textbox(label="输入你的问题...")

    msg.submit(chat, [msg, chatbot], [chatbot, msg])

demo.launch(server_name="127.0.0.1", server_port=7860)
```

### 7.2 进阶：Telegram Bot

```python
# 用 python-telegram-bot
# 优势：推送通知（健康异常主动提醒）、移动端原生体验
```

### 7.3 仪表盘（可选）

用 Gradio 的 `gr.Plot` 组件渲染健康数据趋势图（心率曲线、睡眠质量柱状图等）。

---

## 八、Phase 6：测试与上线

**周期**：1 周 | **依赖**：Phase 3-5

### 8.1 测试清单

| # | 测试项 | 方法 |
|---|--------|------|
| 1 | 意图路由准确率 | 50 条标注样本，对比路由结果 |
| 2 | RAG 检索质量 | 20 条医学问题，人工评估召回相关性 |
| 3 | 幻觉检查 | 故意问不存在的问题，检查是否编造 |
| 4 | 紧急词触发 | 输入 "胸痛"，验证 emergency handler |
| 5 | 安全审查覆盖 | 所有 medical_qa 路径是否过 safety check |
| 6 | 对话连贯性 | 5 轮多轮对话，检查上下文保持 |
| 7 | API 故障降级 | 断网后检查错误提示是否友好 |

### 8.2 API 成本估算

| 场景 | 模型 | Token/次 | 单价 (元/1M token) | 单次成本 | 月预估 (100次/天) |
|------|------|----------|-------------------|----------|-------------------|
| 意图路由 | Flash | ~200 | 1 元 | < 0.001 元 | < 0.3 元 |
| 健康分析 | Flash | ~1,500 | 1 元 | ~0.0015 元 | ~4.5 元 |
| 医疗问答+RAG | Flash | ~3,000 | 1 元 | ~0.003 元 | ~9 元 |
| 对话生成 | Pro | ~2,000 | 2 元 | ~0.004 元 | ~12 元 |
| 周报生成 | Pro | ~4,000 | 2 元 | ~0.008 元 | ~0.03 元 (4次/月) |
| **月合计** | | | | | **~26 元** |

> DeepSeek V4 Flash 当前定价约 1 元/1M token，Pro 约 2 元/1M token。以上为上限估计，实际更省（缓存 + 短回复）。

---

## 九、总时间线

```
Week 1-2    Phase 0: 项目搭建 + Phase 1: Apple Health 数据管道
Week 2-3    Phase 2: RAG 知识库构建
Week 3-5    Phase 3: LangGraph Agent 系统 (核心)
Week 5-7    Phase 4: 长期记忆 (可与 Phase 5 并行)
Week 6-7    Phase 5: 前端 Gradio/Telegram
Week 8      Phase 6: 测试 + 优化 + 上线
```

**总计：约 8 周，可压缩到 6 周（Phase 1/2 并行，Phase 4/5 并行）。**

---

## 十、成本总览

| 阶段 | 费用来源 | 金额 |
|------|----------|------|
| Phase 0-2 | 0 | 0 元 |
| Phase 3 开发 | DeepSeek API 测试调用 | < 10 元 |
| Phase 4-5 开发 | DeepSeek API 测试调用 | < 10 元 |
| 上线后 | DeepSeek API 月费 (100次/天) | ~26 元/月 |

**总开发成本 < 50 元，月运营成本 ~26 元。对比 v2.0 的 SFT 训练就要 45 元 + 本地部署的显存痛苦，纯 API 方案性价比极高。**

---

## 十一、待讨论与确认的问题

> 以下是我在规划过程中发现的开放问题，请你在后续对话中逐步确认，我会据此迭代方案。

### Q1：RAG 深度
目前设计是"检索 + 给 LLM 做 context"。有没有考虑过更高级的 RAG 范式（如 HyDE、Multi-hop、Self-RAG）？还是初期简单够用即可？

### Q2：多用户支持
当前设计是单用户。如果要支持多用户（家人共享），需要在 AgentState 中加入 `user_id`，数据隔离、个人基线都要按用户分。是否现在规划多用户，还是先单用户跑通？

### Q3：疾病诊断边界
分析 Agent 目前拒绝开处方、加免责声明。但用户如果问"我是不是得了XX病"——是直接拒绝回答，还是做"基于知识的科普但不做诊断"？这个边界在 Prompt 设计和产品定位上需要明确。

### Q4：Apple Health 数据隐私
数据存在本地 SQLite，但如果将来想部署到服务器（不用 ngrok），健康数据的传输加密和存储加密需要考虑。现阶段本地部署是否可以接受？

### Q5：对话历史持久化
LangGraph MemorySaver 默认在内存中，重启后丢失。是否需要持久化到 SQLite？还是初期不保留历史（每次独立对话）？

### Q6：是否需要「自我怀疑/多Agent辩论」机制
v1.1 方案中提出了"本地模型初稿 + 云端模型审查"的双重校验。去掉本地模型后，可以用 Flash 出初稿 + Pro 做审查（同一 API 但不同模型）。但这样成本翻倍。是否需要？

### Q7：前端形态优先级
Gradio（Web UI）和 Telegram Bot，先做哪个？Telegram Bot 的优势是推送通知（检测到异常指标主动提醒），Gradio 的优势是图表展示健康趋势。

### Q8：安全审查深度
目前设计是"同模型快速过一遍"。是否需要更严格的流程（如独立的安全审查 prompt、输出格式校验正则）？你是否有特定的安全红线需要在系统级硬编码？

---

> **下一步**：请你针对以上 8 个问题给出倾向，以及你对 Phase 顺序/优先级是否有调整意见。我会据此产出 Phase 的详细执行 Spec。
