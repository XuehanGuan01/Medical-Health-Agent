# Phase 1: Apple Health 数据管道 — 可执行实施方案

> **目标**：实现 Apple Health 数据从 iPhone 到本地数据库的自动同步，构建数据聚合层，为 Phase 2 的 Agent 分析提供结构化输入。
>
> **周期**：1–2 周
>
> **核心原则**：本阶段不涉及任何 LLM，纯粹是数据工程。

---

## 目录

1. [架构总览](#1-架构总览)
2. [iOS 端：数据采集方案](#2-ios-端数据采集方案)
3. [后端实现：FastAPI + SQLite](#3-后端实现fastapi--sqlite)
4. [数据聚合层](#4-数据聚合层)
5. [部署与运行](#5-部署与运行)
6. [测试验证](#6-测试验证)
7. [Phase 2 衔接准备](#7-phase-2-衔接准备)

---

## 1. 架构总览

```
┌──────────────────────┐
│   iPhone (iOS 17+)    │
│                      │
│  Health Auto Export  │  ← 免费版即可，支持 150+ 健康指标
│  App 定时 POST JSON  │
└────────┬─────────────┘
         │ HTTPS (ngrok / 内网穿透)
         ▼
┌──────────────────────┐
│   FastAPI Webhook    │  ← 接收 & 校验 JSON
│   (Pydantic 校验)     │
└────────┬─────────────┘
         │
         ▼
┌──────────────────────┐
│   SQLite 数据库       │  ← Phase 1 用 SQLite，Phase 3 迁移 PG
│                      │
│  raw_health_samples   │  ← 原始数据表（每 5 分钟心率等）
│  daily_metrics        │  ← 日聚合指标表
│  sync_log             │  ← 同步日志
└────────┬─────────────┘
         │
         ▼
┌──────────────────────┐
│   数据聚合层          │  ← 原始数据 → 日/周指标
│   (aggregator.py)    │     (均值、标准差、区间分布、异常次数)
└──────────────────────┘
```

### 数据流

```
Health Auto Export (每 30 分钟定时同步)
  → POST /api/v1/health/sync
  → Pydantic 校验 & 清洗日期格式
  → 写入 raw_health_samples 表
  → 触发增量聚合 → daily_metrics 表
  → API 查询: GET /api/v1/health/daily?date=2026-05-06
```

### 涉及的健康数据类型

| 类别 | 指标 | Health Auto Export 中的名称 |
|------|------|---------------------------|
| 心脏 | 心率 | `heart_rate` |
| 心脏 | 静息心率 | `resting_heart_rate` |
| 心脏 | 心率变异性 (HRV) | `heart_rate_variability` |
| 活动 | 步数 | `step_count` |
| 活动 | 活跃能量 | `active_energy` |
| 活动 | 运动时长 | `exercise_time` |
| 睡眠 | 睡眠分析 | `sleep_analysis` |
| 呼吸 | 血氧饱和度 | `oxygen_saturation` |
| 呼吸 | 呼吸频率 | `respiratory_rate` |
| 身体 | 手腕温度 | `wrist_temperature` |
| 运动 | 训练数据 | `workouts` |

---

## 2. iOS 端：数据采集方案

### 方案对比

| 方案                          | 成本    | 自动化程度          | 指标覆盖             | 推荐度   |
| --------------------------- | ----- | -------------- | ---------------- | ----- |
| **Health Auto Export** (推荐) | 免费版够用 | 后台定时自动         | 150+ 指标          | ⭐⭐⭐⭐⭐ |
| Health Exporter & Shortcuts | $0.99 | 手动 + Shortcuts | 22 类指标           | ⭐⭐⭐   |
| 纯 iOS Shortcuts             | 免费    | 需手动触发 / 定时自动化  | 取决于 Shortcuts 能力 | ⭐⭐    |
| 手动导出 XML                    | 免费    | 手动             | 全部               | ⭐     |

### 2.1 推荐方案：Health Auto Export 配置（5 分钟）

**Step 1 — 安装 App**

从 App Store 下载 **Health Auto Export - JSON+CSV**（开发者：Lybron Sobers，免费版）。

> App Store 链接：搜索 "Health Auto Export JSON CSV"

**Step 2 — 授权 HealthKit 访问**

打开 App → 按提示授权以下数据类型（至少勾选）：
- Heart Rate
- Resting Heart Rate
- Heart Rate Variability
- Steps
- Active Energy
- Sleep Analysis
- Oxygen Saturation
- Respiratory Rate
- Workouts

**Step 3 — 配置 API 导出**

进入 App → **Automations** → **Add Automation** → **API Export**：

| 配置项            | 值                                                          |
| -------------- | ---------------------------------------------------------- |
| URL            | `https://your-ngrok-url.ngrok-free.app/api/v1/health/sync` |
| Format         | JSON                                                       |
| Period         | Last Sync                                                  |
| Interval       | Minutes                                                    |
| Sync           | 30 Minutes                                                 |
| Data Type      | Health Metrics + Workouts                                  |
| Custom Headers | `Authorization: Bearer <your-api-key>` (见下文)               |

**Step 4 — 启用自动化**

将 Automation 设为 **Enabled**，App 会在后台每 30 分钟自动同步一次。

### 2.2 备选方案：纯 iOS Shortcuts（零依赖，免费）

如果不想安装第三方 App，可用原生 Shortcuts 实现。以下是 Shortcut 的构建步骤：

1. 打开 **快捷指令 (Shortcuts)** App
2. 新建快捷指令 → 添加操作：
   - **"查找健康样本" (Find Health Samples)**：选择数据类型（心率），日期范围「今天」
   - **"从列表中获取项目"**：逐个提取
   - **"设定词典值"**：构建 `{"type": "Heart Rate", "dates": [...], "values": [...]}`
   - **"获取 URL 内容"**：方法 POST，URL 填 webhook 地址，正文选 JSON
3. 在 **自动化 (Automation)** 标签中，创建「特定时间」触发器，每天定时执行

> ⚠️ Shortcuts 方案的局限性：
> - 构建 JSON 的过程冗长且容易出错
> - 每种数据类型需要单独写一段逻辑
> - 睡眠数据跨越午夜，处理复杂
> - 后台执行时间受限（约 30 秒）
>
> **强烈建议用 Health Auto Export 替代此方案。**

---

## 3. 后端实现：FastAPI + SQLite

### 3.1 项目结构

```
Medical-Health-Agent/
├── data_pipeline/              # Phase 1 全部代码
│   ├── __init__.py
│   ├── config.py               # 全局配置
│   ├── models.py               # Pydantic + SQLAlchemy 模型
│   ├── database.py             # 数据库连接 & 初始化
│   ├── webhook_server.py       # FastAPI 主应用
│   ├── aggregator.py           # 数据聚合逻辑
│   └── test_data.py            # 模拟测试数据
├── data/                       # 数据目录（自动创建）
│   └── health.db               # SQLite 数据库
├── requirements.txt
└── Phase1-Apple-Health数据管道实施方案.md  # 本文档
```

### 3.2 依赖安装

创建 `requirements.txt`：

```txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy==2.0.36
pydantic==2.10.3
python-dateutil==2.9.0
numpy==2.2.1
```

```bash
cd Medical-Health-Agent
pip install -r requirements.txt
```

### 3.3 配置 `data_pipeline/config.py`

```python
"""全局配置"""
import os

# 数据库
DATABASE_URL = os.getenv("HEALTH_DB_URL", "sqlite:///data/health.db")

# API 鉴权（生产环境务必修改）
API_KEY = os.getenv("HEALTH_API_KEY", "medical-health-agent-dev-key-2026")

# 聚合配置
AGGREGATION_METRICS = [
    "heart_rate",
    "resting_heart_rate",
    "heart_rate_variability",
    "step_count",
    "active_energy",
    "oxygen_saturation",
    "respiratory_rate",
]

# Health Auto Export 的 JSON 顶层包裹键名
# 不同版本可能用 "data" 或直接发送 metrics 数组
WRAPPER_KEY = "data"
```

### 3.4 数据模型 `data_pipeline/models.py`

```python
"""Pydantic 校验模型 & SQLAlchemy 存储模型"""
from __future__ import annotations

import re
from datetime import datetime, date
from typing import Optional, Union

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, Text
from sqlalchemy.orm import DeclarativeBase


# ============================================================
# Pydantic — 请求校验（接收 Health Auto Export 的 JSON）
# ============================================================

class MetricDataPoint(BaseModel):
    """单个健康数据点"""
    date: str  # ISO 8601 或 "2024-01-01 12:00:00 +0000"
    qty: Optional[float] = None
    min: Optional[float] = None
    avg: Optional[float] = None
    max: Optional[float] = None
    value: Optional[str] = None      # 睡眠分析用: "inBed", "asleepREM" 等
    startDate: Optional[str] = None  # 睡眠分析用
    endDate: Optional[str] = None    # 睡眠分析用
    source: Optional[str] = None

    @field_validator("date", mode="before")
    @classmethod
    def normalize_date(cls, v: str) -> str:
        """将 iOS 多种日期格式统一为 ISO 8601"""
        if not isinstance(v, str):
            return v
        # "2024-01-01 12:00:00 +0000" → "2024-01-01T12:00:00+00:00"
        v = re.sub(r"(\d{2}:\d{2}:\d{2}) \+0(\d{3})", r"\1+0\2:00", v)
        v = v.replace(" ", "T", 1)
        return v


class HealthMetric(BaseModel):
    """Health Auto Export 的单个指标组"""
    name: str
    units: str
    data: list[MetricDataPoint]


class WorkoutData(BaseModel):
    """训练数据（简化版）"""
    name: str
    startDate: str
    endDate: str
    duration: Optional[float] = None       # 秒
    activeEnergy_kJ: Optional[float] = None
    distance_m: Optional[float] = None
    avgHeartRate_bpm: Optional[float] = None
    maxHeartRate_bpm: Optional[float] = None


class HealthExportPayload(BaseModel):
    """Health Auto Export 发送的完整 JSON 结构"""
    metrics: list[HealthMetric] = Field(default_factory=list)
    workouts: list[WorkoutData] = Field(default_factory=list)


class HealthSyncRequest(BaseModel):
    """最外层包裹 — Health Auto Export 有时用 {"data": {...}} 包裹"""
    data: Optional[HealthExportPayload] = None
    # 也兼容直接发送 metrics/workouts 的情况
    metrics: Optional[list[HealthMetric]] = None
    workouts: Optional[list[WorkoutData]] = None

    def get_payload(self) -> HealthExportPayload:
        if self.data:
            return self.data
        return HealthExportPayload(
            metrics=self.metrics or [],
            workouts=self.workouts or [],
        )


# ============================================================
# SQLAlchemy — 数据库表
# ============================================================

class Base(DeclarativeBase):
    pass


class RawHealthSample(Base):
    """原始健康数据点 —— 每一行 = 一条 Apple Health 记录"""
    __tablename__ = "raw_health_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_type = Column(String(64), nullable=False, index=True)
    value = Column(Float)
    unit = Column(String(32))
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime)
    source = Column(String(128))
    device = Column(String(128))
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # 额外字段 — 存 JSON 字符串，用于 HRV/睡眠等复杂类型
    extra = Column(Text)


class DailyMetric(Base):
    """日聚合指标"""
    __tablename__ = "daily_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    metric_type = Column(String(64), nullable=False, index=True)
    avg_value = Column(Float)
    min_value = Column(Float)
    max_value = Column(Float)
    stddev_value = Column(Float)
    total_value = Column(Float)     # 累积量（步数、卡路里）
    sample_count = Column(Integer)
    unit = Column(String(32))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SyncLog(Base):
    """同步日志"""
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    metrics_count = Column(Integer, default=0)
    data_points_count = Column(Integer, default=0)
    workouts_count = Column(Integer, default=0)
    status = Column(String(32), default="success")  # success / partial / error
    error_message = Column(Text)
```

### 3.5 数据库初始化 `data_pipeline/database.py`

```python
"""数据库连接 & 表创建"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .config import DATABASE_URL
from .models import Base

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """创建所有表"""
    import os
    db_path = DATABASE_URL.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(db_path) or "data", exist_ok=True)
    Base.metadata.create_all(engine)


def get_db() -> Session:
    """FastAPI 依赖注入"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### 3.6 Webhook 服务 `data_pipeline/webhook_server.py`

```python
"""FastAPI Webhook — 接收 Apple Health 数据"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .config import API_KEY
from .database import init_db, get_db
from .models import (
    HealthSyncRequest,
    HealthMetric,
    WorkoutData,
    RawHealthSample,
    SyncLog,
)
from .aggregator import aggregate_daily_metrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("health-webhook")

app = FastAPI(title="Medical-Health-Agent Data Pipeline", version="1.0.0")


def verify_api_key(authorization: Optional[str] = Header(None)):
    """API Key 鉴权"""
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.replace("Bearer ", "")
    if token != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return token


@app.on_event("startup")
def startup():
    init_db()
    logger.info("Database initialized")


# ============================================================
# POST /api/v1/health/sync  — 核心接口
# ============================================================

@app.post("/api/v1/health/sync")
def receive_health_data(
    payload: HealthSyncRequest,
    target: Optional[str] = Query(None, description="用户标识"),
    db: Session = Depends(get_db),
    _token: str = Depends(verify_api_key),
):
    """
    接收 Health Auto Export 推送的健康数据。

    请求体格式（Health Auto Export）:
    {
      "data": {
        "metrics": [
          {
            "name": "heart_rate",
            "units": "bpm",
            "data": [
              {"date": "2026-05-06T08:00:00+00:00", "min": 68, "avg": 72, "max": 85},
              ...
            ]
          }
        ],
        "workouts": [...]
      }
    }
    """
    export = payload.get_payload()
    metrics_count = len(export.metrics)
    data_points_count = 0
    workouts_count = len(export.workouts)

    # ---- 处理 metrics ----
    for metric in export.metrics:
        try:
            inserted = _insert_metric_samples(db, metric, target)
            data_points_count += inserted
        except Exception as e:
            logger.error(f"Failed to insert metric '{metric.name}': {e}")
            _log_sync(db, metrics_count, data_points_count, workouts_count, "partial", str(e))
            return JSONResponse(
                {"status": "partial", "error": f"Metric '{metric.name}' failed: {e}"},
                status_code=207,
            )

    # ---- 处理 workouts ----
    for workout in export.workouts:
        try:
            _insert_workout(db, workout, target)
        except Exception as e:
            logger.error(f"Failed to insert workout: {e}")

    # ---- 增量聚合 ----
    try:
        aggregate_daily_metrics(db)
    except Exception as e:
        logger.error(f"Aggregation failed: {e}")

    # ---- 记录同步日志 ----
    _log_sync(db, metrics_count, data_points_count, workouts_count, "success")

    return {
        "status": "success",
        "metrics_received": metrics_count,
        "data_points_inserted": data_points_count,
        "workouts_received": workouts_count,
    }


def _insert_metric_samples(db: Session, metric: HealthMetric, target: Optional[str]) -> int:
    """将单个 HealthMetric 的 data 数组写入 raw_health_samples"""
    count = 0
    for dp in metric.data:
        # 提取数值
        value = _extract_value(dp, metric.name)

        # 解析时间
        start_time = _parse_datetime(dp.date)
        end_time = _parse_datetime(dp.endDate) if dp.endDate else None

        # 对于睡眠分析，使用 startDate/endDate
        if dp.startDate:
            start_time = _parse_datetime(dp.startDate)
        if dp.endDate:
            end_time = _parse_datetime(dp.endDate)

        sample = RawHealthSample(
            metric_type=metric.name,
            value=value,
            unit=metric.units,
            start_time=start_time,
            end_time=end_time,
            source=dp.source,
            device=target,
            received_at=datetime.utcnow(),
            extra=_build_extra(dp),
        )
        db.add(sample)
        count += 1

    db.commit()
    return count


def _extract_value(dp, metric_name: str) -> Optional[float]:
    """从不同的 Health Metric 格式中提取核心数值"""
    # 优先 avg（心率等聚合数据）
    if dp.avg is not None:
        return dp.avg
    # qty（步数、距离等）
    if dp.qty is not None:
        return dp.qty
    # 睡眠分析 —— 用时长（秒）
    if dp.value and dp.startDate and dp.endDate:
        try:
            start = _parse_datetime(dp.startDate)
            end = _parse_datetime(dp.endDate)
            if start and end:
                return (end - start).total_seconds() / 60.0  # 返回分钟
        except Exception:
            pass
    return None


def _build_extra(dp) -> Optional[str]:
    """将非标准字段存入 extra JSON"""
    import json
    extra_fields = {}
    for key in ("min", "max", "value"):
        val = getattr(dp, key, None)
        if val is not None:
            extra_fields[key] = val
    return json.dumps(extra_fields, ensure_ascii=False) if extra_fields else None


def _insert_workout(db: Session, workout: WorkoutData, target: Optional[str]):
    """将训练数据写入 raw_health_samples（以 workout_* 为 metric_type）"""
    import json
    start = _parse_datetime(workout.startDate)
    end = _parse_datetime(workout.endDate)

    workout_data = {
        "duration_sec": workout.duration,
        "active_energy_kJ": workout.activeEnergy_kJ,
        "distance_m": workout.distance_m,
        "avg_heart_rate_bpm": workout.avgHeartRate_bpm,
        "max_heart_rate_bpm": workout.maxHeartRate_bpm,
    }

    sample = RawHealthSample(
        metric_type=f"workout_{workout.name.lower().replace(' ', '_')}",
        value=workout.duration,  # 主值 = 时长（秒）
        unit="seconds",
        start_time=start,
        end_time=end,
        source="Apple Watch",
        device=target,
        received_at=datetime.utcnow(),
        extra=json.dumps({k: v for k, v in workout_data.items() if v is not None}),
    )
    db.add(sample)
    db.commit()


def _log_sync(db: Session, metrics_count: int, data_points: int,
              workouts_count: int, status: str, error_msg: str = None):
    log = SyncLog(
        received_at=datetime.utcnow(),
        metrics_count=metrics_count,
        data_points_count=data_points,
        workouts_count=workouts_count,
        status=status,
        error_message=error_msg,
    )
    db.add(log)
    db.commit()


# ============================================================
# 日期解析工具
# ============================================================

def _parse_datetime(s: Optional[str]) -> Optional[datetime]:
    """解析 iOS 端的各种日期格式 → datetime"""
    if not s:
        return None
    from dateutil import parser as dt_parser
    try:
        return dt_parser.parse(s)
    except Exception:
        # 最后尝试：手动处理 "2024-01-01 12:00:00 +0000"
        import re
        try:
            cleaned = re.sub(r"(\d{2}:\d{2}:\d{2}) \+0(\d{3})", r"\1+0\2:00", s)
            cleaned = cleaned.replace(" ", "T", 1)
            return datetime.fromisoformat(cleaned)
        except Exception:
            return None


# ============================================================
# 查询 API（供 Phase 2 使用）
# ============================================================

@app.get("/api/v1/health/daily")
def get_daily_metrics(
    date: str = Query(..., description="日期 YYYY-MM-DD"),
    metric: Optional[str] = Query(None, description="指标名，不传则返回全部"),
    db: Session = Depends(get_db),
):
    """查询某一天的聚合指标"""
    from .models import DailyMetric

    q = db.query(DailyMetric).filter(DailyMetric.date == date)
    if metric:
        q = q.filter(DailyMetric.metric_type == metric)

    results = q.all()
    return {
        "date": date,
        "metrics": [
            {
                "metric_type": r.metric_type,
                "avg_value": r.avg_value,
                "min_value": r.min_value,
                "max_value": r.max_value,
                "stddev_value": r.stddev_value,
                "total_value": r.total_value,
                "sample_count": r.sample_count,
                "unit": r.unit,
            }
            for r in results
        ],
    }


@app.get("/api/v1/health/raw")
def get_raw_samples(
    metric_type: str = Query(...),
    date_from: str = Query(..., description="起始日期 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(1000, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    """查询原始健康数据"""
    from datetime import datetime as dt

    start = dt.strptime(date_from, "%Y-%m-%d")
    end = dt.strptime(date_to, "%Y-%m-%d") if date_to else None

    q = db.query(RawHealthSample).filter(
        RawHealthSample.metric_type == metric_type,
        RawHealthSample.start_time >= start,
    )
    if end:
        q = q.filter(RawHealthSample.start_time <= end)

    results = q.order_by(RawHealthSample.start_time.asc()).limit(limit).all()

    return {
        "metric_type": metric_type,
        "count": len(results),
        "samples": [
            {
                "value": r.value,
                "unit": r.unit,
                "start_time": r.start_time.isoformat(),
                "source": r.source,
            }
            for r in results
        ],
    }


@app.get("/api/v1/health/status")
def get_status(db: Session = Depends(get_db)):
    """查看同步状态 & 数据库概览"""
    from sqlalchemy import func

    total_raw = db.query(func.count(RawHealthSample.id)).scalar()
    total_daily = db.query(func.count(DailyMetric.id)).scalar()
    last_sync = db.query(SyncLog).order_by(SyncLog.received_at.desc()).first()

    # 各类指标的数据量
    metric_counts = (
        db.query(RawHealthSample.metric_type, func.count(RawHealthSample.id))
        .group_by(RawHealthSample.metric_type)
        .all()
    )

    return {
        "total_raw_samples": total_raw,
        "total_daily_metrics": total_daily,
        "metric_types": {m: c for m, c in metric_counts},
        "last_sync": {
            "time": last_sync.received_at.isoformat() if last_sync else None,
            "status": last_sync.status if last_sync else None,
            "data_points": last_sync.data_points_count if last_sync else 0,
        } if last_sync else None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 3.7 数据聚合层 `data_pipeline/aggregator.py`

```python
"""数据聚合：原始数据 → 日指标"""
import logging
from datetime import date, datetime, timedelta

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import AGGREGATION_METRICS
from .models import RawHealthSample, DailyMetric

logger = logging.getLogger("aggregator")


def aggregate_daily_metrics(db: Session, target_date: date = None):
    """
    将 raw_health_samples 聚合为 daily_metrics。

    对于每种指标，计算：
    - avg / min / max / stddev（对心率、HRV 等连续型）
    - total（对步数、卡路里等累积型）
    - sample_count
    """
    if target_date is None:
        target_date = date.today()

    for metric_type in AGGREGATION_METRICS:
        try:
            _aggregate_one_metric(db, metric_type, target_date)
        except Exception as e:
            logger.error(f"Aggregation failed for {metric_type} on {target_date}: {e}")

    db.commit()


def _aggregate_one_metric(db: Session, metric_type: str, target_date: date):
    """聚合单个指标类型某天的数据"""
    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    samples = (
        db.query(RawHealthSample.value, RawHealthSample.unit)
        .filter(
            RawHealthSample.metric_type == metric_type,
            RawHealthSample.start_time >= day_start,
            RawHealthSample.start_time < day_end,
            RawHealthSample.value.isnot(None),
        )
        .all()
    )

    if not samples:
        return  # 当天无数据

    values = np.array([s.value for s in samples], dtype=np.float64)
    unit = samples[0].unit

    # 删除旧聚合（幂等）
    db.query(DailyMetric).filter(
        DailyMetric.date == target_date,
        DailyMetric.metric_type == metric_type,
    ).delete()

    daily = DailyMetric(
        date=target_date,
        metric_type=metric_type,
        avg_value=float(np.mean(values)),
        min_value=float(np.min(values)),
        max_value=float(np.max(values)),
        stddev_value=float(np.std(values)),
        total_value=float(np.sum(values)),
        sample_count=len(values),
        unit=unit,
    )
    db.add(daily)


def compute_baseline(db: Session, metric_type: str, days: int = 30) -> dict:
    """
    计算个人基线（30 天均值 ± 2σ）。
    用于 Phase 2 的异常检测。

    返回: {"mean": ..., "std": ..., "upper": ..., "lower": ..., "n_days": ...}
    """
    cutoff = date.today() - timedelta(days=days)
    rows = (
        db.query(DailyMetric.avg_value)
        .filter(
            DailyMetric.metric_type == metric_type,
            DailyMetric.date >= cutoff,
            DailyMetric.avg_value.isnot(None),
        )
        .all()
    )

    values = [r.avg_value for r in rows if r.avg_value is not None]
    if len(values) < 3:
        return {"mean": None, "std": None, "n_days": len(values),
                "error": "Insufficient data (need ≥3 days)"}

    arr = np.array(values)
    mean = float(np.mean(arr))
    std = float(np.std(arr))

    return {
        "mean": mean,
        "std": std,
        "upper": mean + 2 * std,
        "lower": mean - 2 * std,
        "n_days": len(values),
    }
```

### 3.8 测试数据生成 `data_pipeline/test_data.py`

```python
"""模拟 Health Auto Export 发送的测试数据，用于本地调试"""
import json
import random
from datetime import datetime, timedelta

def generate_test_payload(days_back: int = 1, samples_per_hour: int = 12) -> dict:
    """
    生成模拟 Health Auto Export JSON。

    参数:
        days_back: 模拟多少天前的数据
        samples_per_hour: 每小时几个采样点（心率约每 5 分钟 = 12）
    """
    now = datetime.utcnow()
    start = now - timedelta(days=days_back)
    end = now

    def gen_heart_rate():
        data = []
        t = start
        while t < end:
            # 静息心率 + 随机波动
            hr = round(random.gauss(72, 8), 1)
            ts = t.strftime("%Y-%m-%d %H:%M:%S +0000")
            data.append({
                "date": ts,
                "min": round(hr - 5, 1),
                "avg": hr,
                "max": round(hr + 8, 1),
                "source": "Apple Watch Series 7",
            })
            t += timedelta(seconds=3600 // samples_per_hour)
        return data

    def gen_steps():
        data = []
        t = start
        while t < end:
            steps = max(0, round(random.gauss(200, 100)))
            data.append({
                "date": t.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "qty": steps,
                "source": "Apple Watch Series 7",
            })
            t += timedelta(hours=1)
        return data

    def gen_hrv():
        data = []
        t = start
        while t < end:
            hrv = max(10, round(random.gauss(45, 12), 1))
            data.append({
                "date": t.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "qty": hrv,
                "source": "Apple Watch Series 7",
            })
            t += timedelta(hours=1)
        return data

    def gen_sleep():
        sleep_start = (now - timedelta(days=days_back)).replace(hour=23, minute=0, second=0)
        sleep_end = sleep_start + timedelta(hours=7, minutes=30)
        return [
            {
                "startDate": sleep_start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "endDate": sleep_end.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "value": "inBed",
                "source": "Apple Watch Series 7",
            },
            {
                "startDate": sleep_start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "endDate": sleep_end.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "value": "asleepREM",
                "qty": 2.5 * 3600,  # 2.5h REM
                "source": "Apple Watch Series 7",
            },
        ]

    payload = {
        "data": {
            "metrics": [
                {"name": "heart_rate", "units": "bpm", "data": gen_heart_rate()},
                {"name": "resting_heart_rate", "units": "bpm", "data": [
                    {"date": start.strftime("%Y-%m-%d %H:%M:%S +0000"), "qty": round(random.gauss(58, 3), 1)}
                ]},
                {"name": "heart_rate_variability", "units": "ms", "data": gen_hrv()},
                {"name": "step_count", "units": "count", "data": gen_steps()},
                {"name": "sleep_analysis", "units": "minutes", "data": gen_sleep()},
                {"name": "active_energy", "units": "kJ", "data": [
                    {"date": start.strftime("%Y-%m-%d %H:%M:%S +0000"), "qty": round(random.uniform(800, 2500), 1)}
                ]},
            ],
            "workouts": [
                {
                    "name": "Outdoor Walk",
                    "startDate": start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                    "endDate": (start + timedelta(minutes=35)).strftime("%Y-%m-%d %H:%M:%S +0000"),
                    "duration": 2100,
                    "activeEnergy_kJ": 650,
                    "distance_m": 3200,
                    "avgHeartRate_bpm": 115,
                    "maxHeartRate_bpm": 142,
                }
            ],
        }
    }
    return payload


if __name__ == "__main__":
    payload = generate_test_payload()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\n生成 {sum(len(m['data']) for m in payload['data']['metrics'])} 条数据点 + 1 条训练记录")
```

---

## 4. 数据聚合层

### 4.1 聚合逻辑

```
原始数据（raw_health_samples）
    │  心率: 每 5 分钟一条，一天 ~288 条
    │  HRV:   每 1 小时一条，一天 ~24 条
    │  步数:  每 1 小时一条，一天 ~24 条
    │
    ▼  日聚合 (aggregate_daily_metrics)
    │
    ▼
日指标（daily_metrics）
    │  avg_value    — 日平均值
    │  min_value    — 日最低值
    │  max_value    — 日最高值
    │  stddev_value — 日标准差（反映波动性）
    │  total_value  — 日累积值（步数、卡路里）
    │  sample_count — 有效采样数
```

### 4.2 个人基线计算（Phase 2 前置）

`compute_baseline(metric_type, days=30)` 返回前 30 天的均值和标准差，用于：
- 异常检测：「今日静息心率 78，偏离个人基线 2.3σ」
- 趋势判断：「HRV 连续 5 天低于 30 天均值」

### 4.3 聚合触发时机

- **自动**：每次 `/sync` webhook 收到新数据后，增量聚合当天指标
- **手动**：可通过 API 触发历史数据全量聚合

---

## 5. 部署与运行

### 5.1 本地开发测试

```bash
# 1. 安装依赖
cd Medical-Health-Agent
pip install -r requirements.txt

# 2. 启动 FastAPI
cd data_pipeline
python webhook_server.py
# 服务启动在 http://0.0.0.0:8000

# 3. 验证服务
curl http://localhost:8000/api/v1/health/status
```

### 5.2 使用 ngrok 暴露公网 URL（iOS 需要公网可达）

```bash
# 安装 ngrok（从 https://ngrok.com 下载）
# 注册免费账号获取 authtoken

ngrok config add-authtoken <your-token>
ngrok http 8000

# 获得类似: https://abc123.ngrok-free.app
# Health Auto Export 的 URL 配为:
# https://abc123.ngrok-free.app/api/v1/health/sync
```

### 5.3 发送测试数据

```bash
# 在另一个终端，发送模拟数据到 webhook
python data_pipeline/test_data.py > /tmp/test_health.json

curl -X POST http://localhost:8000/api/v1/health/sync \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer medical-health-agent-dev-key-2026" \
  -d @/tmp/test_health.json

# 查看结果
curl http://localhost:8000/api/v1/health/status
curl "http://localhost:8000/api/v1/health/daily?date=2026-05-06"
```

### 5.4 生产化部署（可选）

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "uvicorn", "data_pipeline.webhook_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t health-pipeline .
docker run -d -p 8000:8000 -v $(pwd)/data:/app/data health-pipeline
```

### 5.5 安全配置（上线前必做）

1. **修改 API Key**：环境变量 `HEALTH_API_KEY`，不要用默认值
2. **HTTPS**：生产环境必须用 nginx + Let's Encrypt（iOS 对自签名证书敏感）
3. **nginx 配置**：`client_max_body_size 50M;`（Health payload 可能包含 GPS 数据）

---

## 6. 测试验证

### 6.1 功能测试清单

| # | 测试项 | 方法 | 预期结果 |
|---|--------|------|---------|
| 1 | 服务启动 | `curl /api/v1/health/status` | 200, `total_raw_samples: 0` |
| 2 | API Key 鉴权 | 不带 `Authorization` header POST | 401 |
| 3 | 接收测试数据 | `test_data.py` → POST | 200, 返回 data_points 数量 |
| 4 | 数据写入 | 查 `/status` | total_raw_samples > 0 |
| 5 | 日聚合 | 查 `/daily?date=...` | 返回各指标的 avg/min/max/stddev |
| 6 | 重复同步幂等 | 同一条数据 POST 两次 | 不报错，daily_metrics 不重复 |
| 7 | 日期格式兼容 | 测试多种格式 `2024-01-01T12:00:00Z`, `2024-01-01 12:00:00 +0000` | 全部正确解析 |

### 6.2 真实 iOS 数据测试

1. 在 iPhone 上安装 **Health Auto Export**
2. 配置 Automation → API Export → URL 指向 ngrok 地址
3. 手动触发一次同步（点 Automation 旁边的 ▶️ 按钮）
4. 检查服务日志和数据

### 6.3 端到端验证脚本

```bash
#!/bin/bash
# e2e_test.sh

BASE="http://localhost:8000"
AUTH="Authorization: Bearer medical-health-agent-dev-key-2026"

echo "=== 1. 服务状态 ==="
curl -s $BASE/api/v1/health/status | python -m json.tool

echo -e "\n=== 2. 发送模拟数据 ==="
python data_pipeline/test_data.py > /tmp/health_test.json
curl -s -X POST $BASE/api/v1/health/sync \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d @/tmp/health_test.json | python -m json.tool

echo -e "\n=== 3. 再次查看状态 ==="
curl -s $BASE/api/v1/health/status | python -m json.tool

echo -e "\n=== 4. 查询今日聚合 ==="
TODAY=$(date +%Y-%m-%d)
curl -s "$BASE/api/v1/health/daily?date=$TODAY" | python -m json.tool

echo -e "\n=== 5. 查询原始心率数据 ==="
curl -s "$BASE/api/v1/health/raw?metric_type=heart_rate&date_from=$TODAY&limit=5" | python -m json.tool

echo -e "\n✅ E2E 测试完成"
```

---

## 7. Phase 2 衔接准备

Phase 1 完成后，以下数据将直接供 Phase 2 的 Agent 使用：

### 7.1 感知 Agent 输入格式

```python
# Phase 2 中，感知节点将这样读取数据：
from data_pipeline.aggregator import compute_baseline
from data_pipeline.database import SessionLocal

db = SessionLocal()

# 获取今日指标
today_metrics = db.query(DailyMetric).filter(date=date.today()).all()

# 获取个人基线
hr_baseline = compute_baseline(db, "heart_rate", days=30)

# 生成结构化摘要 → 发送给 LLM
summary = {
    "date": str(date.today()),
    "heart_rate": {"avg": 72, "baseline_mean": 68, "deviation_pct": 5.8},
    "hrv": {"avg": 48, "baseline_mean": 45, "deviation_pct": 6.7},
    "steps": {"total": 8500, "baseline_mean": 7200, "deviation_pct": 18.1},
    "sleep": {"total_hours": 7.2, "deep_hours": 1.5, "rem_hours": 2.1},
}
```

### 7.2 Prompt 模板参照

Phase 2 的分析 Agent 将使用如下模板（Phase 1 只是输出数据，不调用 LLM）：

```
你是私人健康顾问。基于以下今日数据给出分析：

- 心率: 均值 {avg} bpm，范围 {min}–{max}，标准差 {std}，偏离基线 {delta}%
- HRV: 今日 {avg} ms，30天基线 {baseline_mean} ± {baseline_std} ms
- 步数: 今日 {total} 步
- 睡眠: 总时长 {total}h，深度 {deep}h，REM {rem}h
- 运动: 活跃能量 {energy} kJ，运动时长 {exercise} min

请输出:
1. 今日状态总结 (1句话)
2. 需要关注的点 (如有)
3. 饮食建议
4. 明日运动建议
```

### 7.3 数据积累时间线

| 时间 | 数据量 | 可用功能 |
|------|--------|---------|
| 第 1 天 | 1 天原始数据 | 日聚合 |
| 第 7 天 | 7 天聚合数据 | 周趋势 |
| 第 30 天 | 30 天基线 | 个人基线 + 异常检测 |

---

## 附录 A：Health Auto Export JSON 完整示例

```json
{
  "data": {
    "metrics": [
      {
        "name": "heart_rate",
        "units": "bpm",
        "data": [
          {
            "date": "2026-05-06 08:05:00 +0000",
            "min": 68,
            "avg": 72,
            "max": 85,
            "source": "Apple Watch Series 7"
          }
        ]
      },
      {
        "name": "step_count",
        "units": "count",
        "data": [
          {"date": "2026-05-06 08:00:00 +0000", "qty": 245, "source": "Apple Watch"}
        ]
      },
      {
        "name": "sleep_analysis",
        "units": "hr",
        "data": [
          {
            "startDate": "2026-05-05 23:15:00 +0000",
            "endDate": "2026-05-06 06:45:00 +0000",
            "value": "inBed",
            "source": "Apple Watch Series 7"
          }
        ]
      }
    ],
    "workouts": [
      {
        "name": "Outdoor Walk",
        "startDate": "2026-05-06 07:30:00 +0000",
        "endDate": "2026-05-06 08:05:00 +0000",
        "duration": 2100,
        "activeEnergy_kJ": 650,
        "distance_m": 3200,
        "avgHeartRate_bpm": 115,
        "maxHeartRate_bpm": 142
      }
    ]
  }
}
```

## 附录 B：常见问题排查

| 问题 | 可能原因 | 解决 |
|------|---------|------|
| iOS 端同步失败 | ngrok URL 过期 / 证书问题 | 重启 ngrok，更新 URL |
| `401 Unauthorized` | API Key 不匹配 | 检查 environment variable 和 Shortcuts 里的 Authorization header |
| `400 Bad Request` | JSON 格式不符合 Pydantic 模型 | 查看服务端日志，对比实际 payload |
| 日期为 None | 日期格式解析失败 | 在 `_parse_datetime` 中添加新的格式规则 |
| 聚合数据为空 | metric_type 不在 `AGGREGATION_METRICS` 中 | 将新类型添加到 `config.py` |

---

> ~~**下一步 Phase 2**：LangGraph 构建 `HealthAnalysisGraph`，感知 Agent 读取聚合数据，分析 Agent 调用 DeepSeek/Qwen3-Max API 生成健康报告。~~

更新Phase2正确版：医疗RAG知识库构建方案