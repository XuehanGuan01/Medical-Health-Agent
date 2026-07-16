"""
Phase 4 数据模型 — 独立 SQLite 文件 data/memory.db

表:
  chat_history     — 每次 chat() 自动写入一行
  weekly_reports   — 周报（LLM 叙事 + JSON 指标）
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, Date
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ChatHistory(Base):
    """对话历史"""
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    role = Column(String(16), nullable=False)           # "user" | "assistant"
    content = Column(Text, nullable=False)
    intent = Column(String(32))                          # health_data | medical_qa | general_chat | emergency
    safety_level = Column(String(16), default="normal")
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class WeeklyReport(Base):
    """周报"""
    __tablename__ = "weekly_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    week_start = Column(Date, nullable=False, index=True)
    week_end = Column(Date, nullable=False)
    narrative = Column(Text)                             # LLM 叙事全文
    metrics_json = Column(Text)                          # 各项指标 JSON
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class DailyAnalysis(Base):
    """单日健康分析"""
    __tablename__ = "daily_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    target_date = Column(Date, nullable=False, unique=True, index=True)
    narrative = Column(Text)                             # LLM 叙事全文
    metrics_json = Column(Text)                          # 当日指标 JSON
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
