"""数据库连接 & 表创建"""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .config import DATABASE_URL
from .models import Base

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},  # SQLite + FastAPI 多线程必需
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    """首次启动时创建数据目录 + 建表（幂等）"""
    db_path = DATABASE_URL
    if db_path.startswith("sqlite:///"):
        db_path = db_path[len("sqlite:///"):]

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


def get_db() -> Session:
    """FastAPI 依赖注入：请求结束时自动关闭会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
