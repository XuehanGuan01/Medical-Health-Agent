"""memory.db 独立数据库连接"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from memory.schema import Base

MEMORY_DB_URL = os.getenv("MEMORY_DB_URL", "sqlite:///data/memory.db")

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        db_path = MEMORY_DB_URL
        if db_path.startswith("sqlite:///"):
            db_path = db_path[len("sqlite:///"):]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            MEMORY_DB_URL,
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _engine


def init_memory_db():
    """首次启动时建表"""
    Base.metadata.create_all(_get_engine())


SessionLocal = sessionmaker(bind=None)  # 绑定延迟到首次调用


def get_memory_db() -> Session:
    """FastAPI 依赖注入"""
    engine = _get_engine()
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield db
    finally:
        db.close()
