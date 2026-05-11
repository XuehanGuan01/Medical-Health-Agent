"""
对话历史 CRUD。

数据存储在独立 SQLite 文件 data/memory.db
session_id 由后端自动生成（8位UUID），前端可切换不同 session
Router 只读当前 query（不读历史），按 Phase4 Q8 决策
"""
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from memory.schema import ChatHistory

logger = logging.getLogger("memory.history")

MAX_HISTORY_TURNS = 5          # 注入对话的最大轮数
SESSION_LIST_LIMIT = 20        # list_sessions 最多返回的 session 数
ARCHIVE_DAYS = 90              # get_recent_history 只返回 N 天内的记录


def save_turn(db: Session, session_id: str, role: str, content: str,
              intent: str = None, safety_level: str = "normal",
              retry_count: int = 0):
    """保存一轮对话（user 或 assistant）"""
    record = ChatHistory(
        session_id=session_id,
        role=role,
        content=content[:2000],   # 截断超长内容
        intent=intent,
        safety_level=safety_level,
        retry_count=retry_count,
    )
    db.add(record)
    db.commit()


def get_recent_history(db: Session, session_id: str, n: int = MAX_HISTORY_TURNS) -> list[dict]:
    """
    读取最近 N 轮对话 → 注入 AgentState.messages。

    只返回最近 ARCHIVE_DAYS 天内的记录（自动归档旧数据）。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=ARCHIVE_DAYS)
    records = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.session_id == session_id,
            ChatHistory.created_at >= cutoff,
        )
        .order_by(ChatHistory.created_at.desc())
        .limit(n * 2)          # N 轮 = N 条 user + N 条 assistant
        .all()
    )
    records.reverse()
    return [
        {"role": r.role, "content": r.content, "intent": r.intent}
        for r in records
    ]


def list_sessions(db: Session, limit: int = SESSION_LIST_LIMIT) -> list[dict]:
    """
    列出最近活跃的 session。

    返回: [{"session_id": str, "last_active": str, "first_query": str, "turns": int}, ...]
    """
    from sqlalchemy import func

    rows = (
        db.query(
            ChatHistory.session_id,
            func.max(ChatHistory.created_at).label("last_active"),
            func.count(ChatHistory.id).label("turns"),
        )
        .group_by(ChatHistory.session_id)
        .order_by(func.max(ChatHistory.created_at).desc())
        .limit(limit)
        .all()
    )

    sessions = []
    for sid, last_active, turns in rows:
        # 获取第一条 query
        first = (
            db.query(ChatHistory.content)
            .filter(
                ChatHistory.session_id == sid,
                ChatHistory.role == "user",
            )
            .order_by(ChatHistory.created_at.asc())
            .first()
        )
        first_query = first[0][:40] if first else ""
        sessions.append({
            "session_id": sid,
            "last_active": last_active.isoformat() if last_active else None,
            "first_query": first_query,
            "turns": turns // 2,     # 轮数 = 消息数 / 2
        })
    return sessions


def clear_session(db: Session, session_id: str):
    """前端清除按钮 → 删除指定 session 的全部记录"""
    count = (
        db.query(ChatHistory)
        .filter(ChatHistory.session_id == session_id)
        .delete()
    )
    db.commit()
    logger.info(f"Cleared session={session_id}, {count} records deleted")
    return count
