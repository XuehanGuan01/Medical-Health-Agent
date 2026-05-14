"""数据聚合：raw_health_samples → daily_metrics + 基线计算"""
import logging
from datetime import date, datetime, timedelta, timezone

import numpy as np
from sqlalchemy.orm import Session

from .config import AGGREGATION_METRICS
from .models import RawHealthSample, DailyMetric

logger = logging.getLogger("aggregator")


def aggregate_daily_metrics(db: Session, target_date: date = None):
    """日聚合（增量、幂等）"""
    if target_date is None:
        target_date = date.today()

    day_start = datetime(target_date.year, target_date.month, target_date.day,
                         tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    for metric_type in AGGREGATION_METRICS:
        try:
            _aggregate_one_metric(db, metric_type, target_date, day_start, day_end)
        except Exception as e:
            logger.error(f"Aggregation failed for {metric_type} on {target_date}: {e}",
                         exc_info=True)

    db.commit()
    logger.info(f"Aggregation completed for {target_date}")


def _aggregate_one_metric(db: Session, metric_type: str, target_date: date,
                          day_start: datetime, day_end: datetime):
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

    # 幂等：先删后插
    db.query(DailyMetric).filter(
        DailyMetric.date == target_date,
        DailyMetric.metric_type == metric_type,
    ).delete()

    # 重叠摘要型指标: 同一事件的多条重叠记录 → MAX 代替 SUM/MEAN
    OVERLAP_METRICS = {"sleep_analysis"}
    is_overlap = metric_type in OVERLAP_METRICS

    daily = DailyMetric(
        date=target_date,
        metric_type=metric_type,
        avg_value=round(float(np.max(values)), 2) if is_overlap else round(float(np.mean(values)), 2),
        min_value=round(float(np.min(values)), 2),
        max_value=round(float(np.max(values)), 2),
        stddev_value=round(float(np.std(values)), 2) if len(values) > 1 and not is_overlap else 0.0,
        total_value=round(float(np.max(values)), 2) if is_overlap else round(float(np.sum(values)), 2),
        sample_count=len(values),
        unit=unit,
        created_at=datetime.now(timezone.utc),
    )
    db.add(daily)


def compute_baseline(db: Session, metric_type: str, days: int = 30) -> dict:
    """计算个人基线（前N天日平均值的均值 ± 2σ），供 Phase 3 异常检测使用"""
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

    values = [r.avg_value for r in rows]
    if len(values) < 3:
        return {
            "mean": None,
            "std": None,
            "upper_bound": None,
            "lower_bound": None,
            "n_days": len(values),
            "error": f"Insufficient data: need >= 3 days, got {len(values)}",
        }

    arr = np.array(values, dtype=np.float64)
    mean = float(np.mean(arr))
    std = float(np.std(arr))

    return {
        "mean": round(mean, 2),
        "std": round(std, 2),
        "upper_bound": round(mean + 2 * std, 2),
        "lower_bound": round(mean - 2 * std, 2),
        "n_days": len(values),
    }
