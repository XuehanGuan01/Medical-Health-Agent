"""对话生成节点（含时间上下文）"""
import logging
from datetime import datetime, timezone

from config.llm import get_action_llm
from agents.state import AgentState
from prompts.action import ACTION_SYSTEM, ACTION_USER
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("agent.action")


def _time_greeting() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 9:    return "早上好"
    elif 9 <= hour < 12:  return "上午好"
    elif 12 <= hour < 14: return "中午好"
    elif 14 <= hour < 18: return "下午好"
    else:                 return "晚上好"


def _time_context() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    # 北京时间 = UTC+8
    bj = now.replace(hour=(now.hour + 8) % 24)
    time_str = bj.strftime("%H:%M")
    date_str = bj.strftime("%Y-%m-%d")
    return time_str, date_str


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

    time_now, date_today = _time_context()
    llm = get_action_llm()
    messages = [
        SystemMessage(content=ACTION_SYSTEM.format(
            time_now=time_now, date_today=date_today,
        )),
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
