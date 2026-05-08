"""FastAPI Webhook — 接收 Apple Health 数据"""
import logging
import re
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
    DailyMetric,
)
from .aggregator import aggregate_daily_metrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("health-webhook")

app = FastAPI(title="Medical-Health-Agent Data Pipeline", version="1.0.0")


def verify_api_key(authorization: Optional[str] = Header(None)):
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
# POST /api/v1/health/sync
# ============================================================

@app.post("/api/v1/health/sync")
def receive_health_data(
    payload: HealthSyncRequest,
    target: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _token: str = Depends(verify_api_key),
):
    export = payload.get_payload()
    metrics_count = len(export.metrics)
    data_points_count = 0
    workouts_count = len(export.workouts)

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

    for workout in export.workouts:
        try:
            _insert_workout(db, workout, target)
        except Exception as e:
            logger.error(f"Failed to insert workout: {e}")

    try:
        aggregate_daily_metrics(db)
    except Exception as e:
        logger.error(f"Aggregation failed: {e}")

    _log_sync(db, metrics_count, data_points_count, workouts_count, "success")

    return {
        "status": "success",
        "metrics_received": metrics_count,
        "data_points_inserted": data_points_count,
        "workouts_received": workouts_count,
    }


def _insert_metric_samples(db: Session, metric: HealthMetric, target: Optional[str]) -> int:
    count = 0
    for dp in metric.data:
        value = _extract_value(dp, metric.name)
        # 优先用 startDate（睡眠分析等），其次用 date
        start_time = _parse_datetime(dp.startDate) if dp.startDate else _parse_datetime(dp.date)
        end_time = _parse_datetime(dp.endDate) if dp.endDate else None

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
    if dp.avg is not None:
        return dp.avg
    if dp.qty is not None:
        return dp.qty
    if dp.value and dp.startDate and dp.endDate:
        try:
            start = _parse_datetime(dp.startDate)
            end = _parse_datetime(dp.endDate)
            if start and end:
                return (end - start).total_seconds() / 60.0
        except Exception:
            pass
    return None


def _build_extra(dp) -> Optional[str]:
    import json
    extra_fields = {}
    for key in ("min", "max", "value"):
        val = getattr(dp, key, None)
        if val is not None:
            extra_fields[key] = val
    return json.dumps(extra_fields, ensure_ascii=False) if extra_fields else None


def _insert_workout(db: Session, workout: WorkoutData, target: Optional[str]):
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
        value=workout.duration,
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
# 日期解析
# ============================================================

def _parse_datetime(s: Optional[str]) -> Optional[datetime]:
    """解析 iOS 端各种日期格式 → datetime"""
    if not s:
        return None
    from dateutil import parser as dt_parser
    try:
        return dt_parser.parse(s)
    except Exception:
        pass
    # Fallback: manual fix-up "YYYY-MM-DD HH:MM:SS +0000" → ISO 8601
    try:
        cleaned = re.sub(r" \+(\d{2})(\d{2})$", r"T+\1:\2", s)
        if "T" not in cleaned:
            cleaned = cleaned.replace(" ", "T", 1)
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


# ============================================================
# 查询 API
# ============================================================

@app.get("/api/v1/health/daily")
def get_daily_metrics(
    date: str = Query(...),
    metric: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
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
    date_from: str = Query(...),
    date_to: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
    db: Session = Depends(get_db),
):
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
            {"value": r.value, "unit": r.unit, "start_time": r.start_time.isoformat(), "source": r.source}
            for r in results
        ],
    }


@app.get("/api/v1/health/status")
def get_status(db: Session = Depends(get_db)):
    from sqlalchemy import func
    total_raw = db.query(func.count(RawHealthSample.id)).scalar()
    total_daily = db.query(func.count(DailyMetric.id)).scalar()
    last_sync = db.query(SyncLog).order_by(SyncLog.received_at.desc()).first()
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
