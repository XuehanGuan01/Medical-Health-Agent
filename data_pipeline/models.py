"""Pydantic 校验模型 & SQLAlchemy 存储模型"""
from __future__ import annotations

import re
from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, Text
from sqlalchemy.orm import DeclarativeBase


# ============================================================
# Pydantic — 请求校验
# ============================================================

class MetricDataPoint(BaseModel):
    date: Optional[str] = None  # 睡眠分析用 startDate/endDate 代替
    qty: Optional[float] = None
    min: Optional[float] = None
    avg: Optional[float] = None
    max: Optional[float] = None
    value: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    source: Optional[str] = None

    @field_validator("date", mode="before")
    @classmethod
    def normalize_date(cls, v: str) -> str:
        if not isinstance(v, str):
            return v
        return v


class HealthMetric(BaseModel):
    name: str
    units: str
    data: list[MetricDataPoint]


class WorkoutData(BaseModel):
    name: str
    startDate: str
    endDate: str
    duration: Optional[float] = None
    activeEnergy_kJ: Optional[float] = None
    distance_m: Optional[float] = None
    avgHeartRate_bpm: Optional[float] = None
    maxHeartRate_bpm: Optional[float] = None


class HealthExportPayload(BaseModel):
    metrics: list[HealthMetric] = Field(default_factory=list)
    workouts: list[WorkoutData] = Field(default_factory=list)


class HealthSyncRequest(BaseModel):
    data: Optional[HealthExportPayload] = None
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
    extra = Column(Text)


class DailyMetric(Base):
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
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SyncLog(Base):
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    metrics_count = Column(Integer, default=0)
    data_points_count = Column(Integer, default=0)
    workouts_count = Column(Integer, default=0)
    status = Column(String(32), default="success")
    error_message = Column(Text)
