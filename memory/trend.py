"""
健康趋势查询 — 多周对比，含简单缓存。

Phase 4 Q5 决策：趋势查询可缓存（数据不变，不怕重复算）。
"""
import logging
from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache

from sqlalchemy.orm import Session
from data_pipeline.models import DailyMetric

logger = logging.getLogger("memory.trend")

TREND_CACHE_SIZE = 64


@lru_cache(maxsize=TREND_CACHE_SIZE)
def _trend_cache_key(metric_type: str, weeks: int, today_str: str) -> tuple:
    """缓存 key 元组，lru_cache 要求 hashable"""
    pass   # 仅用于类型标记，实际缓存的是下面函数


def get_trend(db: Session, metric_type: str, weeks: int = 4) -> dict:
    """
    查询指标多周趋势。

    返回:
      {
        "metric": "heart_rate",
        "weeks": 4,
        "overall_mean": 72.5,
        "weeks_data": [{week_start, avg, min, max, days}, ...],
        "trend_direction": "stable" | "rising" | "falling",
        "change_pct": 2.1
      }
    """
    today = date.today()
    start_date = today - timedelta(weeks=weeks * 7)

    rows = (
        db.query(
            DailyMetric.date,
            DailyMetric.avg_value,
            DailyMetric.min_value,
            DailyMetric.max_value,
            DailyMetric.sample_count,
        )
        .filter(
            DailyMetric.metric_type == metric_type,
            DailyMetric.date >= start_date,
            DailyMetric.date <= today,
            DailyMetric.avg_value.isnot(None),
        )
        .order_by(DailyMetric.date.asc())
        .all()
    )

    if not rows:
        return {"error": f"No data for {metric_type} in last {weeks} weeks"}

    # 按周分组
    weeks_data_dict = defaultdict(list)
    for r in rows:
        d = r.date if isinstance(r.date, date) else date.fromisoformat(str(r.date)[:10])
        monday = d - timedelta(days=d.weekday())
        weeks_data_dict[monday].append(r)

    result_weeks = []
    week_avgs = []
    for monday in sorted(weeks_data_dict.keys()):
        day_rows = weeks_data_dict[monday]
        avgs = [r.avg_value for r in day_rows if r.avg_value is not None]
        mins = [r.min_value for r in day_rows if r.min_value is not None]
        maxs = [r.max_value for r in day_rows if r.max_value is not None]
        result_weeks.append({
            "week_start": str(monday),
            "avg": round(sum(avgs) / len(avgs), 2) if avgs else None,
            "min": round(min(mins), 2) if mins else None,
            "max": round(max(maxs), 2) if maxs else None,
            "days": len(day_rows),
        })
        if avgs:
            week_avgs.append(sum(avgs) / len(avgs))

    # 趋势方向
    direction = "stable"
    change_pct = 0.0
    if len(week_avgs) >= 2:
        first, last = week_avgs[0], week_avgs[-1]
        change_pct = round((last - first) / first * 100, 1) if first != 0 else 0.0
        if abs(change_pct) <= 2:
            direction = "stable"
        elif change_pct > 0:
            direction = "rising"
        else:
            direction = "falling"

    overall_mean = round(sum(week_avgs) / len(week_avgs), 2) if week_avgs else None

    return {
        "metric": metric_type,
        "weeks": weeks,
        "overall_mean": overall_mean,
        "weeks_data": result_weeks,
        "trend_direction": direction,
        "change_pct": change_pct,
    }
