"""硬边界检测 — 紧急词短路 + 拒答模板"""
from prompts.boundary import EMERGENCY_PATTERNS, REJECT_TEMPLATES


def check_emergency(query: str) -> tuple[bool, str | None]:
    """
    匹配紧急症状关键词。
    尝试检查主语是否为第一人称（我/本人）。

    返回 (is_emergency, reject_message_or_none)
    """
    has_self = any(w in query for w in ("我", "本人", "自己", "现在", "突然"))

    for kw in EMERGENCY_PATTERNS:
        if kw in query:
            # 心血管/神经/出血等高危词 → 不论主语都触发
            high_risk = any(w in kw for w in (
                "胸痛", "胸闷", "心梗", "意识丧失", "昏迷", "抽搐",
                "大出血", "中风", "脑出血", "窒息", "休克", "濒死",
                "服毒", "自杀", "自残", "溺水", "触电", "坠楼",
            ))
            if high_risk or has_self:
                return True, REJECT_TEMPLATES["emergency"]

    return False, None


def build_reject_response(reason: str, issues: str = "") -> str:
    """根据原因构造拒答消息"""
    template = REJECT_TEMPLATES.get(reason, REJECT_TEMPLATES["diagnosis"])
    return template.format(issues=issues)
