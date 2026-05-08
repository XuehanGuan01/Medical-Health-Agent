"""数据聚合：原始数据 → 日指标"""
import logging
from datetime import date, datetime, timedelta

import numpy as np
from sqlalchemy.orm import Session

from .config import AGGREGATION_METRICS
from .models import RawHealthSample, DailyMetric

logger = logging.getLogger("aggregator")


def aggregate_daily_metrics(db: Session, target_date: date = None):
    if target_date is None:
        target_date = date.today()

    for metric_type in AGGREGATION_METRICS:
        try:
            _aggregate_one_metric(db, metric_type, target_date)
        except Exception as e:
            logger.error(f"Aggregation failed for {metric_type} on {target_date}: {e}")

    db.commit()


def _aggregate_one_metric(db: Session, metric_type: str, target_date: date):
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
        return

    values = np.array([s.value for s in samples], dtype=np.float64)
    unit = samples[0].unit

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
