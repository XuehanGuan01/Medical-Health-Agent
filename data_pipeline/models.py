"""Pydantic 校验模型 & SQLAlchemy 存储模型"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, Text
from sqlalchemy.orm import DeclarativeBase


# ============================================================
# Pydantic — 请求校验
# ============================================================

class MetricDataPoint(BaseModel):
    """
    健康数据点（兼容 Health Auto Export JSON 的多种格式）。

    字段组合因类型而异：
      - 简单型:  {date, qty}                     — 步数、能量、血氧等
      - 心率型:  {date, Min=, Avg=, Max=}        — ⚠️ 官方使用首字母大写
      - 血压型:  {date, systolic, diastolic}
      - 睡眠非聚合: {startDate, endDate, qty, value} — value 为阶段标签
      - 睡眠聚合:  {date, totalSleep, core, deep, rem, ...}
      - 血糖型:  {date, qty, mealTime}
    """
    model_config = ConfigDict(populate_by_name=True)

    date: Optional[str] = None
    qty: Optional[float] = None
    value: Optional[str] = None          # 睡眠阶段标签 / 洗手、刷牙等
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    source: Optional[str] = None

    # 心率字段 — 官方用首字母大写 "Min"/"Avg"/"Max"
    min: Optional[float] = Field(default=None, alias="Min")
    avg: Optional[float] = Field(default=None, alias="Avg")
    max: Optional[float] = Field(default=None, alias="Max")

    # 血压
    systolic: Optional[float] = None
    diastolic: Optional[float] = None

    # 血糖
    mealTime: Optional[str] = None       # "Before Meal" / "After Meal" / "Unspecified"

    # 胰岛素给药
    reason: Optional[str] = None         # "Bolus" / "Basal"

    # 睡眠聚合模式字段
    totalSleep: Optional[float] = None
    asleep: Optional[float] = None
    core: Optional[float] = None
    deep: Optional[float] = None
    rem: Optional[float] = None
    sleepStart: Optional[str] = None
    sleepEnd: Optional[str] = None
    inBed: Optional[float] = None
    inBedStart: Optional[str] = None
    inBedEnd: Optional[str] = None

    @field_validator("date", "startDate", "endDate", "sleepStart", "sleepEnd",
                     "inBedStart", "inBedEnd", mode="before")
    @classmethod
    def normalize_datetime(cls, v: Optional[str]) -> Optional[str]:
        """统一 iOS 多种日期格式 → ISO 8601: 2024-02-06 14:30:00 -0800 → 2024-02-06T14:30:00-08:00"""
        if not isinstance(v, str):
            return v
        # 替换 " +0000" → "+00:00"
        v = re.sub(r" \+(\d{2})(\d{2})$", r"+\1:\2", v)
        # 日期与时间之间的空格 → T
        if "T" not in v:
            v = v.replace(" ", "T", 1)
        return v


class HealthMetric(BaseModel):
    """Health Auto Export 的单个指标组"""
    name: str
    units: str
    data: list[MetricDataPoint]


class WorkoutData(BaseModel):
    """
    训练数据（V2 格式兼容）。

    必需字段: id, name, start, end, duration
    可选字段: location, activeEnergyBurned, distance, heartRate 等
    """
    id: Optional[str] = None
    name: str
    start: Optional[str] = None          # V2 用 "start"
    end: Optional[str] = None            # V2 用 "end"
    duration: Optional[float] = None

    # V1 兼容字段（Health Auto Export 实测用 camelCase）
    startDate: Optional[str] = None
    endDate: Optional[str] = None

    # 能量 / 强度
    activeEnergy_kJ: Optional[float] = None

    # 距离 / 速度
    distance_m: Optional[float] = None

    # 心率
    avgHeartRate_bpm: Optional[float] = None
    maxHeartRate_bpm: Optional[float] = None

    # 位置
    location: Optional[str] = None       # "Indoor" / "Outdoor" / "Pool" / "Open Water"


class HealthExportPayload(BaseModel):
    """Health Auto Export 发送的完整 JSON 结构（data 内部）"""
    metrics: list[HealthMetric] = Field(default_factory=list)
    workouts: list[WorkoutData] = Field(default_factory=list)


class HealthSyncRequest(BaseModel):
    """
    最外层请求包装。
    兼容 {"data": {metrics: [...], workouts: [...]}} 和直接发送两种方式。
    """
    data: Optional[HealthExportPayload] = None
    metrics: Optional[list[HealthMetric]] = None
    workouts: Optional[list[WorkoutData]] = None

    def get_payload(self) -> HealthExportPayload:
        """解包：优先取 data 内的 payload，否则用顶层字段"""
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
    """原始健康数据点"""
    __tablename__ = "raw_health_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_type = Column(String(64), nullable=False, index=True)
    value = Column(Float)
    unit = Column(String(32))
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime)
    source = Column(String(128))
    device = Column(String(128))
    received_at = Column(DateTime, nullable=False)               # 由 webhook_server 显式赋值
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
    total_value = Column(Float)
    sample_count = Column(Integer)
    unit = Column(String(32))
    created_at = Column(DateTime, nullable=False)                # 由 webhook_server 显式赋值


class SyncLog(Base):
    """同步日志"""
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    received_at = Column(DateTime, nullable=False)               # 由 webhook_server 显式赋值
    metrics_count = Column(Integer, default=0)
    data_points_count = Column(Integer, default=0)
    workouts_count = Column(Integer, default=0)
    status = Column(String(32), default="success")               # success / partial / error
    error_message = Column(Text)
