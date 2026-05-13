"""意图路由节点 (v2: 关键词快速分类 → 模糊时 LLM 兜底)"""
import logging
from config.llm import get_router_llm
from agents.state import AgentState
from prompts.router import ROUTER_SYSTEM, ROUTER_USER
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("agent.router")

# 关键词快速分类（命中时跳过 LLM）
HEALTH_KEYWORDS = (
    "心率", "hrv", "步数", "睡眠", "能量", "运动", "站立",
    "呼吸", "体温", "体重", "bmi", "血氧", "血压", "距离",
    "今天", "昨天", "前天", "本周", "最近", "这周",
    "健康状况", "身体数据", "健康数据", "指标",
    "heart rate", "steps", "sleep",
)
MEDICAL_KEYWORDS = (
    "怎么", "如何", "什么", "为什么", "原因", "症状",
    "治疗", "吃药", "用药", "药物", "手术", "检查",
    "预防", "饮食", "营养", "锻炼", "运动建议",
    "发烧", "感冒", "头疼", "咳嗽", "腹泻", "过敏",
    "高血压", "糖尿病", "心脏病", "怀孕", "儿童",
    "副作用", "禁忌", "疫苗", "恢复", "康复",
    "怎么办", "是什么病",
)


def router_node(state: AgentState) -> dict:
    """关键词快速四分类；模糊时调用 LLM"""
    query = state["query"]
    q = query.strip()

    # 1. 关键词匹配
    is_health = any(kw in q for kw in HEALTH_KEYWORDS)
    is_medical = any(kw in q for kw in MEDICAL_KEYWORDS)

    # 纯健康数据查询（无医疗关键词）
    if is_health and not is_medical:
        logger.info(f"Router(keyword): health_data — '{q[:40]}'")
        return {"intent": "health_data", "route": "perception"}

    # 纯医疗问答（无健康数据关键词）
    if is_medical and not is_health:
        logger.info(f"Router(keyword): medical_qa — '{q[:40]}'")
        return {"intent": "medical_qa", "route": "analysis"}

    # 简短问候/闲聊
    if len(q) <= 5 and not is_health and not is_medical:
        logger.info(f"Router(keyword): general_chat — '{q[:40]}'")
        return {"intent": "general_chat", "route": "action"}

    # 2. 模糊→LLM
    logger.info(f"Router(LLM): ambiguous — '{q[:40]}'")
    llm = get_router_llm()
    messages = [
        SystemMessage(content=ROUTER_SYSTEM),
        HumanMessage(content=ROUTER_USER.format(query=q)),
    ]
    raw = llm.invoke(messages).content.strip().lower()
    return _parse_llm(raw)


def _parse_llm(raw: str) -> dict:
    r = raw.lower()
    if "emergency" in r or "紧急" in r:
        return {"intent": "emergency", "route": "emergency"}
    elif "health_data" in r or "健康数据" in r:
        return {"intent": "health_data", "route": "perception"}
    elif "medical_qa" in r or "医疗" in r or "医学" in r:
        return {"intent": "medical_qa", "route": "analysis"}
    else:
        return {"intent": "general_chat", "route": "action"}
