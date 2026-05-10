"""对话生成节点"""
import logging

from config.llm import get_action_llm
from agents.state import AgentState
from prompts.action import ACTION_SYSTEM, ACTION_USER
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("agent.action")


def action_node(state: AgentState) -> dict:
    """生成最终回答"""

    # 紧急处理
    if state.get("route") == "emergency":
        return {
            "response": state.get("response", ""),
            "source": "rule",
            "safety_level": "emergency",
        }

    # 拼接上下文
    parts = []
    if state.get("draft_response"):
        parts.append(f"[分析结果]\n{state['draft_response']}")
    if state.get("personal_context"):
        parts.append(f"[健康数据]\n{state['personal_context']}")

    context_block = "\n\n".join(parts) if parts else "无额外上下文"
    query = state.get("query", "")

    llm = get_action_llm()
    messages = [
        SystemMessage(content=ACTION_SYSTEM),
        HumanMessage(content=ACTION_USER.format(
            context_block=context_block, query=query,
        )),
    ]
    response = llm.invoke(messages).content

    logger.info(f"Action: generated {len(response)} chars")

    return {
        "response": response,
        "source": "qwen3-max",
        "safety_level": "normal",
    }


def reject_node(state: AgentState) -> dict:
    """Self-RAG reject 分支 — 生成拒答"""
    issues = state.get("reflection", {}).get("issues", "")
    return {
        "response": (
            f"抱歉，我暂时无法充分回答这个问题。{issues}\n"
            "建议您咨询专业医生获取更准确的建议。"
        ),
        "source": "qwen3-max",
        "safety_level": "caution",
    }
