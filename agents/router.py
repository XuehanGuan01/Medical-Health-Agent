"""意图路由节点"""
import logging
from config.llm import get_router_llm
from agents.state import AgentState
from prompts.router import ROUTER_SYSTEM, ROUTER_USER
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("agent.router")


def router_node(state: AgentState) -> dict:
    """LLM 四分类意图路由 → health_data / medical_qa / general_chat / emergency"""
    query = state["query"]

    llm = get_router_llm()
    messages = [
        SystemMessage(content=ROUTER_SYSTEM),
        HumanMessage(content=ROUTER_USER.format(query=query)),
    ]
    raw = llm.invoke(messages).content.strip().lower()

    intent, route = _parse_router_output(raw)
    logger.info(f"Router: '{query[:40]}...' → intent={intent}, route={route}")
    return {"intent": intent, "route": route}


def _parse_router_output(raw: str) -> tuple[str, str]:
    """解析 LLM 输出 → (intent, route)"""
    raw_lower = raw.lower()

    if "emergency" in raw_lower or "紧急" in raw_lower:
        return "emergency", "emergency"
    elif "health_data" in raw_lower or "健康数据" in raw_lower:
        return "health_data", "perception"
    elif "medical_qa" in raw_lower or "医疗" in raw_lower or "医学" in raw_lower:
        return "medical_qa", "analysis"
    else:
        return "general_chat", "action"
