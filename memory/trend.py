"""
健康趋势查询 — 支持按周(default)或按天 granularity。
"""
import logging
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session
from data_pipeline.models import DailyMetric

logger = logging.getLogger("memory.trend")

CUMULATIVE = {
    "step_count", "active_energy", "basal_energy_burned",
    "apple_exercise_time", "apple_stand_time", "apple_stand_hour",
    "walking_running_distance", "flights_climbed",
    "sleep_analysis", "cycling_distance", "handwashing",
    "environmental_audio_exposure", "headphone_audio_exposure",
    "time_in_daylight", "mindful_minutes", "running_power", "running_speed",
}


def get_trend(db: Session, metric_type: str, weeks: int = 4,
              granularity: str = "day") -> dict:
    """
    查询指标趋势。

    granularity="day"  → 最近 N 天的每日数据点 (适合 Dashboard 折线图)
    granularity="week" → 按自然周聚合 (适合周报)
    """
    today = date.today()

    if granularity == "day":
        start_date = today - timedelta(days=weeks - 1)
    else:
        start_date = today - timedelta(days=weeks * 7)

    rows = (
        db.query(
            DailyMetric.date,
            DailyMetric.avg_value,
            DailyMetric.total_value,
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
        return {"error": f"No data for {metric_type} since {start_date}"}

    use_total = metric_type in CUMULATIVE

    if granularity == "day":
        # 每日一个点
        data_points = []
        values = []
        for r in rows:
            d = r.date if isinstance(r.date, date) else date.fromisoformat(str(r.date)[:10])
            val = r.total_value if use_total else r.avg_value
            if val is not None:
                data_points.append({
                    "date": str(d),
                    "value": round(val, 2),
                    "min": round(r.min_value, 2) if r.min_value else None,
                    "max": round(r.max_value, 2) if r.max_value else None,
                })
                values.append(val)

        direction = "stable"
        change_pct = 0.0
        if len(values) >= 2:
            first, last = values[0], values[-1]
            change_pct = round((last - first) / first * 100, 1) if first else 0.0
            if abs(change_pct) <= 3: direction = "stable"
            elif change_pct > 0: direction = "rising"
            else: direction = "falling"

        return {
            "metric": metric_type,
            "granularity": "day",
            "days": len(data_points),
            "overall_mean": round(sum(values) / len(values), 2) if values else None,
            "data_points": data_points,
            "trend_direction": direction,
            "change_pct": change_pct,
        }

    # granularity="week": 按周一聚合
    weeks_dict = defaultdict(list)
    for r in rows:
        d = r.date if isinstance(r.date, date) else date.fromisoformat(str(r.date)[:10])
        monday = d - timedelta(days=d.weekday())
        weeks_dict[monday].append(r)

    result_weeks = []
    week_avgs = []
    for monday in sorted(weeks_dict.keys()):
        day_rows = weeks_dict[monday]
        vals = [(r.total_value if use_total else r.avg_value)
                for r in day_rows
                if (r.total_value if use_total else r.avg_value) is not None]
        mins = [r.min_value for r in day_rows if r.min_value is not None]
        maxs = [r.max_value for r in day_rows if r.max_value is not None]
        result_weeks.append({
            "week_start": str(monday),
            "avg": round(sum(vals) / len(vals), 2) if vals else None,
            "min": round(min(mins), 2) if mins else None,
            "max": round(max(maxs), 2) if maxs else None,
            "days": len(day_rows),
        })
        if vals:
            week_avgs.append(sum(vals) / len(vals))

    direction = "stable"
    change_pct = 0.0
    if len(week_avgs) >= 2:
        first, last = week_avgs[0], week_avgs[-1]
        change_pct = round((last - first) / first * 100, 1) if first else 0.0
        if abs(change_pct) <= 2: direction = "stable"
        elif change_pct > 0: direction = "rising"
        else: direction = "falling"

    return {
        "metric": metric_type,
        "granularity": "week",
        "weeks": len(result_weeks),
        "overall_mean": round(sum(week_avgs) / len(week_avgs), 2) if week_avgs else None,
        "weeks_data": result_weeks,
        "trend_direction": direction,
        "change_pct": change_pct,
    }
