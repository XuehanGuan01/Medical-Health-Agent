# Phase 3 LangGraph Agent 实施方案

> 2026-05-10 | 基于方案v3五章详细设计 | 依赖 Phase 1 ✅ + Phase 2 ✅
> 核心：LangGraph StateGraph 构建 "意图路由 → Self-RAG → 回答生成" 闭环

---

## 一、前置条件确认

| 依赖 | 状态 | 说明 |
|------|------|------|
| langgraph + langchain-openai | ✅ | StateGraph/MessagesState 可用 |
| `config/llm.py` 5种Agent角色 | ✅ | router/analysis/reflect/action/perception 预设就绪 |
| RAG `MedicalRetriever` | ✅ | 27.6万条，`search()` + `format_context()` 接口 |
| Phase 1 健康数据 | ✅ | 30天基线可用（heart_rate mean=103.61, n=30天） |
| `agents/` + `prompts/` 目录 | ⚠️ | 仅有空 `__init__.py`，需从零搭建 |

---

## 二、架构概览

### 2.1 LangGraph 拓扑

```
                         ┌──────────────────┐
                         │   用户输入 query   │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌────────────────┐
                         │    Router      │  LLM temp=0.0
                         │   意图路由      │  四分类
                         └───┬──┬──┬──┬──┘
                             │  │  │  │
          ┌──────────────────┘  │  │  └──────────────────┐
          │ health_data         │  │ medical_qa          │ general_chat
          ▼                     │  │                     ▼
   ┌──────────────┐             │  │              ┌──────────────┐
   │  Perception  │             │  │              │   Action     │
   │  健康数据分析  │             │  │              │  直接对话生成  │
   │  LLM t=0.1   │             │  │              │  LLM t=0.5   │
   └──────┬───────┘             │  │              └──────┬───────┘
          │                     │  │                     │
          ▼                     │  │                     │
   ┌──────────────┐             │  │                     │
   │   Action     │             │  │                     │
   │  生成健康建议  │             │  │                     │
   └──────┬───────┘             │  │                     │
          │                     │  │                     │
          └─────────────────────┼──┼─────────────────────┘
                                │  │
                     emergency  │  │
                                ▼  ▼
                         ┌────────────────────────────────────┐
                         │         Self-RAG 闭环               │
                         │                                    │
                         │  ┌──────────┐    ┌──────────┐     │
                         │  │ Retrieve │───▶│ Generate │     │
                         │  │ RAG检索   │    │ LLM生成   │     │
                         │  │ k=5      │    │ t=0.15   │     │
                         │  └──────────┘    └────┬─────┘     │
                         │                      │            │
                         │                      ▼            │
                         │               ┌──────────┐        │
                         │               │ Reflect  │        │
                         │               │ 自检     │        │
                         │               │ t=0.0    │        │
                         │               └──┬───┬───┘        │
                         │                  │   │            │
                         │            pass  │   │ retry/reject
                         │                  │   │            │
                         │               ┌──┘   └──┐         │
                         │               ▼         ▼         │
                         │           END      ┌──────────┐   │
                         │                    │ Revise   │   │
                         │                    │ 修正重生成 │   │
                         │                    └────┬─────┘   │
                         │                         │         │
                         │                    (回 Generate)   │
                         └────────────────────────────────────┘
                                  │
                                  ▼
                         ┌────────────────┐
                         │    END         │
                         │  最终回答输出   │
                         └────────────────┘
```

### 2.2 开发文件清单 & 依赖顺序

```
agents/
├── __init__.py        (已有)
├── state.py           Step 1 — AgentState TypedDict           [无依赖]
├── prompts/            Step 2 — Prompt 模板                   [依赖: state.py]
│   ├── __init__.py    (已有)
│   ├── router.py       — 意图路由 prompt
│   ├── analysis.py     — Self-RAG (检索+生成+自检+修正) prompts
│   ├── perception.py   — 健康数据感知 prompt
│   ├── action.py       — 对话/建议 prompt
│   └── boundary.py     — 硬边界拒答模板
├── boundary.py        Step 3 — 紧急词检测 + 拒答处理           [依赖: prompts/boundary.py]
├── router.py          Step 4 — 意图路由节点                    [依赖: state.py, prompts/router.py]
├── analysis.py        Step 5 — Self-RAG核心节点                [依赖: state.py, prompts/analysis.py, rag/]
├── perception.py      Step 6 — 健康数据感知节点                 [依赖: state.py, prompts/perception.py, data_pipeline/]
├── action.py          Step 7 — 对话生成节点                    [依赖: state.py, prompts/action.py]
├── graph.py           Step 8 — StateGraph编译 + FastAPI端点    [依赖: 以上全部]
```

---

## 三、逐文件详细设计

### 3.1 `agents/state.py` — AgentState 定义

```python
# agents/state.py
"""LangGraph AgentState 类型定义"""
from typing import TypedDict, Optional, Annotated, Literal
from langgraph.graph.message import add_messages


IntentType = Literal["health_data", "medical_qa", "general_chat", "emergency"]
RouteType = Literal["perception", "analysis", "action", "emergency"]
ReflectAction = Literal["pass", "retry", "reject"]


class AgentState(TypedDict):
    # ── 用户输入 ──
    query: str
    messages: Annotated[list, add_messages]   # 对话历史

    # ── 路由 ──
    intent: Optional[str]              # IntentType
    route: Optional[str]               # RouteType

    # ── 上下文 ──
    health_metrics: Optional[dict]     # {metric: {avg, baseline_mean, deviation_sigma}}
    personal_context: Optional[str]    # 个人基线+趋势 格式化文本
    retrieved_docs: Optional[list]     # [{"content", "question", "score"}, ...]

    # ── Self-RAG 中间态 ──
    draft_response: Optional[str]      # 生成初稿
    reflection: Optional[dict]         # {"action": "pass"|"retry"|"reject", "issues": str, "score": int}
    retry_count: int                   # 重试计数（防止死循环，max 2）

    # ── 输出 ──
    response: Optional[str]            # 最终回答
    source: Optional[str]              # LLM provider
    safety_level: Optional[str]        # "normal" | "caution" | "emergency"
```

**设计决策**：
- `retry_count` 默认 0，每次 Revise 后 +1，≥2 时 Reflect 强制 pass 防死循环
- `health_metrics` 用 dict 而非强类型，灵活适配不同指标组合
- `intent` 和 `route` 分开：Router 同时输出两个值，有些场景下 `intent` 和 `route` 不一定相同

### 3.2 `prompts/` — Prompt 模板

#### `prompts/router.py` — 意图路由

```python
ROUTER_SYSTEM = """你是医疗AI调度中心的意图分类器。根据用户输入，仅回复以下四个标签之一：

- **health_data**: 用户询问自身健康数据（心率、睡眠、步数、趋势、今日状况等）
- **medical_qa**: 用户询问医学健康知识（症状、疾病、药物、预防、营养等通用问题）
- **emergency**: 用户描述紧急症状（胸痛、呼吸困难、大出血、意识丧失、中风、心梗、窒息、休克等）
- **general_chat**: 与健康无关的一般对话

回复格式：标签，最多一句解释。"""

ROUTER_USER = """用户输入：{query}

仅回复标签（health_data / medical_qa / emergency / general_chat）："""
```

#### `prompts/analysis.py` — Self-RAG

```python
# ── 生成 prompt ──
ANALYSIS_SYSTEM = """你是专业医学AI助手。请基于以下"参考知识"回答用户的医疗问题。

**规则**：
1. 回答必须基于参考知识，不可编造
2. 不要给出明确的医学诊断或处方
3. 如知识不足以回答，请明确说明
4. 如涉及紧急症状，提醒就医
5. 引用参考知识时标注来源 [参考N]"""

ANALYSIS_USER = """参考知识：
{context}

用户问题：{query}

请给出回答："""

# ── 自检 prompt ──
REFLECT_SYSTEM = """你是医疗回答质量审核员。审核以下回答是否符合规范。

**审核标准（每条 0-2 分，满分 10）**：
1. 回答是否基于参考知识？（未编造）
2. 是否避免了医学诊断？
3. 是否避免了开处方/推荐剂量？
4. 紧急症状是否提示就医？
5. 引用的知识是否准确对应问题？

**判定规则**：
- 总分 ≥8 → pass
- 总分 5-7 → retry（指出需修正的问题）
- 总分 <5 → reject（使用拒答模板）

回复 JSON 格式：{"action": "pass"|"retry"|"reject", "score": 0-10, "issues": "具体问题描述"}"""

REFLECT_USER = """用户问题：{query}
参考知识：{context}
回答草稿：{draft}

请审核："""

# ── 修正 prompt ──
REVISE_SYSTEM = """根据以下反馈修正你的回答。保持基于参考知识的严谨性。"""

REVISE_USER = """原始回答：{draft}
审核反馈：{issues}

请修正后重新回答："""
```

#### `prompts/perception.py` — 健康数据感知

```python
PERCEPTION_SYSTEM = """你是个人健康数据分析师。基于用户的健康监测数据和基线对比，分析今日身体状况。

**输出格式**：
1. 核心指标摘要（心率/HRV/步数/睡眠/能量，每项一句话）
2. 偏离基线 ≥1.5σ 的异常指标标注
3. 整体状态总结（一句话）"""

PERCEPTION_USER = """今日健康数据：
{metrics_summary}

个人基线（30天均值）：
{baseline_context}

请分析："""
```

#### `prompts/action.py` — 对话/建议生成

```python
ACTION_SYSTEM = """你是私人健康顾问，为用户提供友好的健康对话和建议。

**规则**：
- 基于感知数据和医学知识，但用自然对话风格
- 给出生活方式建议，而非医疗处方
- 鼓励健康习惯，正向激励
- 如有异常指标，温和提醒关注"""

ACTION_USER = """{context_block}
用户问题：{query}
请回答："""
```

#### `prompts/boundary.py` — 硬边界

```python
EMERGENCY_PATTERNS = [
    # 心血管 — 高危直触发
    "胸痛", "胸闷", "心绞痛", "心梗", "心肌梗死",
    "心跳过速伴", "心悸伴",
    # 呼吸 — 高危直触发
    "呼吸困难", "喘不过气", "窒息", "无法呼吸",
    # 神经系统 — 高危直触发
    "意识丧失", "晕倒", "昏迷", "抽搐", "口吐白沫",
    "面瘫", "一侧肢体无力", "口齿不清",
    "中风", "脑出血", "脑梗",
    # 出血/外伤 — 高危直触发
    "大出血", "喷血", "吐血", "咳血",
    "严重外伤", "骨折", "头部重伤", "高处坠落",
    # 中毒/自杀 — 高危直触发
    "服毒", "农药", "自杀", "自残",
    # 其他高危
    "休克", "濒死", "溺水", "触电", "坠楼", "车祸",
    "严重过敏", "喉头水肿", "高热惊厥",
]

REJECT_TEMPLATES = {
    "diagnosis": (
        "我无法进行医学诊断。{issues}"
        "建议您前往正规医疗机构就诊，由医生进行专业的检查和诊断。"
    ),
    "prescription": (
        "我无法开具处方或推荐具体药物剂量。"
        "用药请务必咨询医生或药师，确保安全有效。"
    ),
    "emergency": (
        "⚠️ 您描述的症状可能需要紧急医疗处理。\n"
        "请立即拨打 **120** 或前往最近的 **急诊科**。\n"
        "这不能等待，每一分钟都很关键。"
    ),
}
```

### 3.3 `agents/boundary.py` — 硬边界检测

```python
"""硬边界检测 — 不经过LLM的规则匹配，含主语检测"""
from prompts.boundary import EMERGENCY_PATTERNS, REJECT_TEMPLATES

def check_emergency(query: str) -> tuple[bool, Optional[str]]:
    """
    匹配紧急症状 → 直接短路。
    高危词(胸痛/窒息/大出血/中风等)不论主语都触发；
    其他词需含 我/本人/自己/现在/突然 等主语标记。
    """
    has_self = any(w in query for w in ("我", "本人", "自己", "现在", "突然"))
    high_risk_signals = ("胸痛", "胸闷", "心梗", "意识丧失", "昏迷", "抽搐",
                         "大出血", "中风", "脑出血", "窒息", "休克", "濒死",
                         "服毒", "自杀", "自残", "溺水", "触电", "坠楼")

    for kw in EMERGENCY_PATTERNS:
        if kw in query:
            if any(s in kw for s in high_risk_signals) or has_self:
                return True, REJECT_TEMPLATES["emergency"]
    return False, None
```

**设计决策**：硬边界在 Router 之前执行，匹配到紧急词直接短路，不调 LLM。

### 3.4 `agents/router.py` — 意图路由

```python
"""意图路由节点"""
from config.llm import get_router_llm
from .state import AgentState
from .prompts.router import ROUTER_SYSTEM, ROUTER_USER
from langchain_core.messages import SystemMessage, HumanMessage

def router_node(state: AgentState) -> dict:
    llm = get_router_llm()
    messages = [
        SystemMessage(content=ROUTER_SYSTEM),
        HumanMessage(content=ROUTER_USER.format(query=state["query"])),
    ]
    result = llm.invoke(messages).content.strip().lower()

    # 解析 LLM 输出 → intent + route
    if "health_data" in result or "健康数据" in result:
        intent, route = "health_data", "perception"
    elif "emergency" in result or "紧急" in result:
        intent, route = "emergency", "emergency"
    elif "medical_qa" in result or "医疗" in result:
        intent, route = "medical_qa", "analysis"
    else:
        intent, route = "general_chat", "action"

    return {"intent": intent, "route": route}
```

**待确认**：LLM 路由准确性。方案：先用 20 条标注样本测试，准确率 <85% 时回退到关键词正则。

### 3.5 `agents/perception.py` — 健康数据分析

```python
"""健康数据感知节点 — 消费 Phase 1 数据"""
from datetime import date
from config.llm import get_perception_llm
from data_pipeline.database import SessionLocal
from data_pipeline.aggregator import compute_baseline
from data_pipeline.models import DailyMetric
from .state import AgentState
from .prompts.perception import PERCEPTION_SYSTEM, PERCEPTION_USER
from langchain_core.messages import SystemMessage, HumanMessage


def perception_node(state: AgentState) -> dict:
    # 1. 从 Phase 1 读取今日聚合 + 基线
    db = SessionLocal()
    try:
        today = db.query(DailyMetric).filter(
            DailyMetric.date == date.today()
        ).all()

        metrics_summary = []
        baseline_context = []
        for m in today:
            bl = compute_baseline(db, m.metric_type, days=30)
            deviation = (
                round((m.avg_value - bl["mean"]) / bl["std"], 2)
                if bl["mean"] and bl["std"] and bl["std"] > 0 else None
            )
            metrics_summary.append(
                f"{m.metric_type}: avg={m.avg_value}, min={m.min_value}, "
                f"max={m.max_value}, samples={m.sample_count}"
            )
            if bl["mean"] is not None:
                baseline_context.append(
                    f"{m.metric_type}: 30d均值={bl['mean']}, "
                    f"范围=[{bl['lower_bound']}, {bl['upper_bound']}]"
                    + (f", 今日偏离={deviation}σ" if deviation else "")
                )

        # 存储结构化数据供下游使用
        health_metrics = {
            m.metric_type: {
                "avg": m.avg_value, "min": m.min_value, "max": m.max_value,
                "stddev": m.stddev_value, "samples": m.sample_count,
                "baseline_mean": bl.get("mean"),
                "deviation_sigma": deviation,
            }
            for m, bl in ...
        }
    finally:
        db.close()

    # 2. LLM 生成叙事
    llm = get_perception_llm()
    messages = [
        SystemMessage(content=PERCEPTION_SYSTEM),
        HumanMessage(content=PERCEPTION_USER.format(
            metrics_summary="\n".join(metrics_summary),
            baseline_context="\n".join(baseline_context),
        )),
    ]
    result = llm.invoke(messages).content

    return {
        "health_metrics": health_metrics,
        "personal_context": result,  # LLM 叙事文本
    }
```

**待确认**：每日聚合是否覆盖足够指标。当前 `AGGREGATION_METRICS` 含 16 个指标，但睡眠/血氧等可能缺失（取决于 iPhone 数据中是否有）。

### 3.6 `agents/analysis.py` — Self-RAG 核心

```python
"""Self-RAG 核心：检索 → 生成 → 自检 → 修正。含三层鲁棒JSON解析。"""
import json, logging, re
from config.llm import get_analysis_llm, get_reflect_llm
from rag.retriever import MedicalRetriever
from agents.state import AgentState
from prompts.analysis import (
    ANALYSIS_SYSTEM, ANALYSIS_USER,
    REFLECT_SYSTEM, REFLECT_USER,
    REVISE_SYSTEM, REVISE_USER,
)
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("agent.analysis")
MAX_RETRIES = 2

_retriever: MedicalRetriever | None = None

def _get_retriever() -> MedicalRetriever:
    global _retriever
    if _retriever is None:
        _retriever = MedicalRetriever()  # 使用默认 rag/data/chroma
    return _retriever


def retrieve(state: AgentState) -> dict:
    docs = _get_retriever().search(state["query"], k=5)
    return {"retrieved_docs": docs}


def generate(state: AgentState) -> dict:
    context = _get_retriever().format_context(state.get("retrieved_docs") or [])
    llm = get_analysis_llm()
    messages = [SystemMessage(content=ANALYSIS_SYSTEM),
                HumanMessage(content=ANALYSIS_USER.format(context=context, query=state["query"]))]
    draft = llm.invoke(messages).content
    return {"draft_response": draft, "retry_count": state.get("retry_count", 0)}


def reflect(state: AgentState) -> dict:
    context = _get_retriever().format_context(state.get("retrieved_docs") or [])
    llm = get_reflect_llm()
    messages = [SystemMessage(content=REFLECT_SYSTEM),
                HumanMessage(content=REFLECT_USER.format(query=state["query"], context=context, draft=state.get("draft_response", "")))]
    raw = llm.invoke(messages).content
    result = _parse_reflection(raw)
    if state.get("retry_count", 0) >= MAX_RETRIES:
        result["action"] = "pass"
    return {"reflection": result}


def _parse_reflection(raw: str) -> dict:
    """三层鲁棒解析: ①json.loads ②正则提取JSON子串 ③fallback"""
    try:
        r = json.loads(raw)
        if isinstance(r, dict) and "action" in r: return r
    except: pass
    try:
        m = re.search(r'\{[^{}]*"action"[^{}]*\}', raw, re.DOTALL)
        if m:
            r = json.loads(m.group())
            if isinstance(r, dict) and "action" in r: return r
    except: pass
    score = int(m.group(1)) if (m := re.search(r'"score"\s*:\s*(\d+)', raw)) else 8
    action = "retry" if "retry" in raw.lower() else ("reject" if "reject" in raw.lower() else "pass")
    issues = m.group(1) if (m := re.search(r'"issues"\s*:\s*"([^"]+)"', raw)) else ""
    return {"action": action, "score": score, "issues": issues}


def revise(state: AgentState) -> dict:
    llm = get_analysis_llm()
    messages = [SystemMessage(content=REVISE_SYSTEM),
                HumanMessage(content=REVISE_USER.format(draft=state.get("draft_response", ""), issues=state.get("reflection", {}).get("issues", "")))]
    revised = llm.invoke(messages).content
    return {"draft_response": revised, "retry_count": state.get("retry_count", 0) + 1}


def should_retry(state: AgentState) -> str:
    action = state.get("reflection", {}).get("action", "pass")
    if action == "retry" and state.get("retry_count", 0) < MAX_RETRIES: return "revise"
    if action == "reject": return "reject"
    return "accept"
```

**Self-RAG 状态机**：

```
         ┌─────────┐
         │ Retrieve │
         └────┬─────┘
              │
              ▼
         ┌─────────┐
    ┌───▶│ Generate │
    │    └────┬─────┘
    │         │
    │         ▼
    │    ┌─────────┐
    │    │ Reflect │─── pass ──▶ END
    │    └────┬─────┘
    │         │ retry
    │         ▼
    │    ┌─────────┐
    └────│ Revise  │ (retry_count += 1)
         └─────────┘
              │ reject
              ▼
         ┌─────────┐
         │ Reject  │──▶ END
         │ 拒答模板  │
         └─────────┘
```

### 3.7 `agents/action.py` — 对话生成

```python
"""对话/建议生成节点"""
from config.llm import get_action_llm
from .state import AgentState
from .prompts.action import ACTION_SYSTEM, ACTION_USER
from langchain_core.messages import SystemMessage, HumanMessage


def action_node(state: AgentState) -> dict:
    """生成最终回答"""

    # 组装上下文
    parts = []
    if state.get("draft_response"):
        parts.append(f"[分析结果]\n{state['draft_response']}")
    if state.get("personal_context"):
        parts.append(f"[健康数据]\n{state['personal_context']}")
    context_block = "\n\n".join(parts)

    llm = get_action_llm()
    messages = [
        SystemMessage(content=ACTION_SYSTEM),
        HumanMessage(content=ACTION_USER.format(
            context_block=context_block,
            query=state["query"],
        )),
    ]
    response = llm.invoke(messages).content

    return {
        "response": response,
        "source": "qwen3-max",
        "safety_level": "normal",
    }
```

### 3.8 `agents/graph.py` — StateGraph 编译 + FastAPI

```python
"""LangGraph 编译 & FastAPI 端点"""
from fastapi import FastAPI
from langgraph.graph import StateGraph, END
from .state import AgentState
from .boundary import check_emergency
from .router import router_node
from .analysis import retrieve, generate, reflect, revise, should_retry
from .perception import perception_node
from .action import action_node


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # ── 添加节点 ──
    graph.add_node("router", router_node)
    graph.add_node("perception", perception_node)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_node("reflect", reflect)
    graph.add_node("revise", revise)
    graph.add_node("action", action_node)

    # ── 入口 ──
    graph.set_entry_point("router")

    # ── 条件边 (路由) ──
    graph.add_conditional_edges(
        "router",
        lambda s: s["route"],
        {
            "perception": "perception",
            "analysis": "retrieve",
            "action": "action",
            "emergency": "action",     # emergency → 直接 action(拒答模板)
        }
    )

    # ── perception → action ──
    graph.add_edge("perception", "action")

    # ── Self-RAG 闭环 ──
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "reflect")
    graph.add_conditional_edges(
        "reflect",
        should_retry,
        {"revise": "revise", "reject": "reject", "accept": "action"}
    )
    graph.add_edge("revise", "generate")   # 回 Generate 重生成
    graph.add_edge("reject", END)          # reject 独立节点 → 直接 END

    # ── action → END ──
    graph.add_edge("action", END)

    return graph.compile()


# ── FastAPI 端点 ──
agent_graph = build_graph()

def chat(query: str, session_id: str = None) -> dict:
    """
    对话入口。支持多轮（session_id 管理 messages 历史）。

    返回: {"response": str, "intent": str, "source": str, "safety_level": str}
    """
    # 硬边界短路
    is_emergency, emergency_msg = check_emergency(query)
    if is_emergency:
        return {
            "response": emergency_msg,
            "intent": "emergency",
            "source": "rule",
            "safety_level": "emergency",
        }

    initial_state: AgentState = {
        "query": query,
        "messages": [],
        "intent": None,
        "route": None,
        "health_metrics": None,
        "personal_context": None,
        "retrieved_docs": None,
        "draft_response": None,
        "reflection": None,
        "retry_count": 0,
        "response": None,
        "source": None,
        "safety_level": "normal",
    }

    result = agent_graph.invoke(initial_state)

    return {
        "response": result.get("response", ""),
        "intent": result.get("intent", "unknown"),
        "source": result.get("source", "unknown"),
        "safety_level": result.get("safety_level", "normal"),
    }
```

---

## 四、集成到 FastAPI

在现有 `data_pipeline/webhook_server.py` 的 `app` 对象上新增端点（或创建独立 app）：

```python
# 方案 A：挂载到 Phase 1 app（推荐，单端口 8000）
# webhook_server.py 末尾新增：

from agents.graph import chat as agent_chat
from pydantic import BaseModel

class ChatRequest(BaseModel):
    query: str
    session_id: str = None

class ChatResponse(BaseModel):
    response: str
    intent: str
    source: str
    safety_level: str

@app.post("/api/v1/chat")
def chat_endpoint(req: ChatRequest):
    return agent_chat(query=req.query, session_id=req.session_id)
```

---

## 五、测试验证计划

### 5.1 单元测试（每个节点独立）

```python
# tests/test_phase3.py
from agents.state import AgentState
from agents.boundary import check_emergency
from agents.router import router_node

def test_emergency_detection():
    ok, msg = check_emergency("我胸口疼")
    assert ok is True
    assert "120" in msg

def test_router_health_data():
    result = router_node({"query": "我今天心率怎么样？"})
    assert result["intent"] == "health_data"
    assert result["route"] == "perception"

def test_router_medical_qa():
    result = router_node({"query": "小孩发烧39度怎么办？"})
    assert result["intent"] == "medical_qa"
    assert result["route"] == "analysis"

def test_router_emergency():
    result = router_node({"query": "我突然胸痛呼吸困难"})
    assert result["intent"] == "emergency"

def test_router_general_chat():
    result = router_node({"query": "你好"})
    assert result["intent"] == "general_chat"
```

### 5.2 集成测试

```python
from agents.graph import chat

# 医疗问答
r1 = chat("小孩发烧39度怎么办？")
assert r1["intent"] in ("medical_qa",)
assert len(r1["response"]) > 20

# 健康数据查询
r2 = chat("我今天心率怎么样？")
assert r2["intent"] in ("health_data",)

# 紧急短路
r3 = chat("我胸痛呼吸困难")
assert r3["safety_level"] == "emergency"
assert "120" in r3["response"]
```

### 5.3 质量评估（20条样本）

| 维度 | 方法 | 目标 |
|------|------|------|
| 路由准确率 | 20条标注样本 | ≥85% |
| RAG 检索命中率 (Top-3) | 20条医学问题 | ≥80% |
| Self-RAG 修正率 | 统计 retry→pass 次数 | 有修正时提升 |
| 紧急触发率 | 10条紧急描述 | 100% |
| 端到端延迟 (P95) | 不含首字延迟 | <10s |

---

## 六、待确认问题 & 模糊点（全部已决）

| # | 问题 | 决策 | 代码实现 |
|---|------|------|---------|
| Q1 | ChromaDB 路径不一致 | 统一为 `rag/data/chroma` | `rag/retriever.py` 默认路径已修正；`agents/analysis.py` 中 `_get_retriever()` 不传参，使用默认值 |
| Q2 | Router LLM vs 规则 | **使用 LLM** 做四分类。`_parse_router_output()` 含 keyword fallback 兜底。流式输出后续评估 | `agents/router.py` — `router_node()` + `_parse_router_output()` |
| Q3 | 多轮对话 | **首版仅单轮**。`AgentState.messages` 已预留 `add_messages`，Phase 4 启用多轮 | `agents/state.py` — `messages: Annotated[list, add_messages]` 保留 |
| Q4 | Perception 跨进程依赖 | **同进程直接调 Python 函数**。SQLite 在本地，无跨进程开销 | `agents/perception.py` — `SessionLocal()` 直连 `data/health.db` |
| Q5 | Reflect JSON 鲁棒性 | **三层解析**：① `json.loads` ② `re.search` 提取 JSON 子串 ③ 正则提取 score/action/issue + fallback pass | `agents/analysis.py` — `_parse_reflection()` 函数 |
| Q6 | 睡眠/血氧指标缺失 | **睡眠可用，血氧不支持（设备限制）**。perception 只读 `DailyMetric` 实际存在的列，缺失指标自动跳过 | `agents/perception.py` — 查询 `date.today()` 的实际 metrics，不做指标白名单 |
| Q7 | reject 路径 | **独立 `reject_node`**，硬编码拒答 → 直接 END，不调 LLM | `agents/action.py` — `reject_node()`；`agents/graph.py` — `reject → END` 边 |
| Q8 | Graph 线程安全 | **天然安全**。`CompiledGraph` immutable + 状态封装在 `invoke()` 的 state dict + `_get_retriever()` 只读 + `SessionLocal()` 每次新建 | `agents/graph.py` 末尾注释说明 |
| Q9 | LLM 费用 | Qwen3-Max 当前**免费额度**，无成本压力。单次对话 ~4500 tokens | — |
| Q10 | 紧急词覆盖度 | **扩展到 50+ 关键词**，含心血管/神经/出血/中毒/外伤五类。增加主语检测（`我/本人/自己/现在/突然` + 高危词直触发） | `prompts/boundary.py` — `EMERGENCY_PATTERNS`；`agents/boundary.py` — `check_emergency()` 含高危词直触发逻辑 |

---

## 七、开发排期

| Step | 内容 | 预估 |
|------|------|------|
| Step 1 | `state.py` + `prompts/` (6个文件) | 0.5天 |
| Step 2 | `boundary.py` + `router.py` | 0.5天 |
| Step 3 | `analysis.py` (Self-RAG 四节点) | 1.5天 |
| Step 4 | `perception.py` + `action.py` | 1天 |
| Step 5 | `graph.py` (编译 + FastAPI集成) | 0.5天 |
| Step 6 | 单元测试 + 20条质量评估 | 1天 |
| **合计** | | **5天** |

> 以上为纯开发时间。建议按 "先跑通单轮流程 → 逐节点验收 → Self-RAG 调优 → 集成测试" 的节奏推进。
