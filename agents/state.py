"""LangGraph AgentState 类型定义"""
from typing import TypedDict, Optional, Annotated
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # ── 用户输入 ──
    query: str
    messages: Annotated[list, add_messages]

    # ── 路由 ──
    # intent: "health_data" | "medical_qa" | "general_chat" | "emergency"
    intent: Optional[str]
    # route: "perception" | "analysis" | "action" | "emergency"
    route: Optional[str]

    # ── 上下文 ──
    health_metrics: Optional[dict]         # {metric: {avg, baseline_mean, deviation_sigma}, ...}
    personal_context: Optional[str]        # LLM 叙事文本
    retrieved_docs: Optional[list]         # [{"content", "question", "score"}, ...]

    # ── Self-RAG 中间态 ──
    draft_response: Optional[str]
    reflection: Optional[dict]             # {"action": "pass"|"retry"|"reject", "score": int, "issues": str}
    retry_count: int                       # 重试计数器，≥2 时强制 pass

    # ── 输出 ──
    response: Optional[str]
    source: Optional[str]
    safety_level: Optional[str]            # "normal" | "caution" | "emergency"
