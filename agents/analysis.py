"""
Self-RAG 核心：检索 → 生成 → 自检 → 修正/通过/拒答

节点:
  retrieve — 从 RAG 知识库取回 Top-K
  generate — 基于检索知识生成回答初稿
  reflect  — 自检回答质量 → pass / retry / reject
  revise   — 根据审核反馈修正重生成
"""
import json
import logging
import re

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
        _retriever = MedicalRetriever()
    return _retriever


# ── retrieve ──

def retrieve(state: AgentState) -> dict:
    """RAG 检索 Top-5 相关医疗QA"""
    r = _get_retriever()
    docs = r.search(state["query"], k=5)
    logger.info(f"Retrieved {len(docs)} docs (top score: {docs[0]['score']:.3f})" if docs else "No docs")
    return {"retrieved_docs": docs}


# ── generate ──

def generate(state: AgentState) -> dict:
    """基于检索知识生成回答初稿"""
    r = _get_retriever()
    context = r.format_context(state.get("retrieved_docs") or [])

    llm = get_analysis_llm()
    messages = [
        SystemMessage(content=ANALYSIS_SYSTEM),
        HumanMessage(content=ANALYSIS_USER.format(
            context=context, query=state["query"]
        )),
    ]
    draft = llm.invoke(messages).content
    return {"draft_response": draft, "retry_count": state.get("retry_count", 0)}


# ── reflect ──

def reflect(state: AgentState) -> dict:
    """自检回答质量 → pass / retry / reject"""
    r = _get_retriever()
    context = r.format_context(state.get("retrieved_docs") or [])

    llm = get_reflect_llm()
    messages = [
        SystemMessage(content=REFLECT_SYSTEM),
        HumanMessage(content=REFLECT_USER.format(
            query=state["query"],
            context=context,
            draft=state.get("draft_response", ""),
        )),
    ]
    raw = llm.invoke(messages).content
    result = _parse_reflection(raw)

    # 硬限制：retry ≥ MAX_RETRIES 时强制 pass
    if state.get("retry_count", 0) >= MAX_RETRIES:
        result["action"] = "pass"

    logger.info(f"Reflect: action={result['action']}, score={result['score']}, retry_count={state.get('retry_count', 0)}")
    return {"reflection": result}


def _parse_reflection(raw: str) -> dict:
    """
    鲁棒 JSON 解析。
    策略: ① json.loads ② 正则提取关键字段 ③ fallback pass
    """
    # ① 尝试直接解析
    try:
        result = json.loads(raw)
        if isinstance(result, dict) and "action" in result:
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # ② 尝试提取 JSON 子串
    try:
        match = re.search(r'\{[^{}]*"action"[^{}]*\}', raw, re.DOTALL)
        if match:
            result = json.loads(match.group())
            if isinstance(result, dict) and "action" in result:
                return result
    except (json.JSONDecodeError, TypeError):
        pass

    # ③ 正则回退
    score = 8
    issues = ""
    if m := re.search(r'"score"\s*:\s*(\d+)', raw):
        score = int(m.group(1))

    if "retry" in raw.lower():
        action = "retry"
    elif "reject" in raw.lower():
        action = "reject"
    else:
        action = "pass"

    if m := re.search(r'"issues"\s*:\s*"([^"]+)"', raw):
        issues = m.group(1)

    return {"action": action, "score": score, "issues": issues}


# ── revise ──

def revise(state: AgentState) -> dict:
    """修正重生成"""
    llm = get_analysis_llm()
    messages = [
        SystemMessage(content=REVISE_SYSTEM),
        HumanMessage(content=REVISE_USER.format(
            draft=state.get("draft_response", ""),
            issues=state.get("reflection", {}).get("issues", ""),
        )),
    ]
    revised = llm.invoke(messages).content
    return {
        "draft_response": revised,
        "retry_count": state.get("retry_count", 0) + 1,
    }


# ── 条件边 ──

def should_retry(state: AgentState) -> str:
    """根据 reflection.action 决定流程走向"""
    action = state.get("reflection", {}).get("action", "pass")
    if action == "retry" and state.get("retry_count", 0) < MAX_RETRIES:
        return "revise"
    elif action == "reject":
        return "reject"
    return "accept"
