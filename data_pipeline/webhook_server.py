"""
FastAPI Webhook — 接收 Apple Health 数据 & 提供查询 API。

端点:
  POST /api/v1/health/sync     — 核心: 接收 Health Auto Export 推送
  GET  /api/v1/health/daily    — 查询日聚合指标
  GET  /api/v1/health/raw      — 查询原始健康数据
  GET  /api/v1/health/baseline — 查询个人基线（Phase 3 消费）
  GET  /api/v1/health/status   — 数据库概览 & 同步状态
"""
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Header, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .config import API_KEY, HOST, PORT
from .database import init_db, get_db
from .models import (
    HealthSyncRequest,
    HealthMetric,
    WorkoutData,
    RawHealthSample,
    DailyMetric,
    SyncLog,
)
from .aggregator import aggregate_daily_metrics, compute_baseline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("health-webhook")


# ============================================================
# 生命周期
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Phase 4: 初始化 memory.db
    from memory.database import init_memory_db
    init_memory_db()
    # 周报表放 health.db（与 DailyMetric 同库）
    from data_pipeline.database import engine as health_engine
    from memory.schema import WeeklyReport, DailyAnalysis
    from sqlalchemy import inspect
    if not inspect(health_engine).has_table("weekly_reports"):
        WeeklyReport.__table__.create(bind=health_engine)
    if not inspect(health_engine).has_table("daily_analyses"):
        DailyAnalysis.__table__.create(bind=health_engine)
    logger.info("Database initialized successfully (health + memory + weekly_report + daily_analysis)")
    yield

app = FastAPI(
    title="Medical-Health-Agent Data Pipeline",
    version="2.0.0",
    description="Phase 1: Apple Health 数据采集与聚合",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 鉴权
# ============================================================

def verify_api_key(authorization: Optional[str] = Header(None)):
    """校验 Bearer Token"""
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.replace("Bearer ", "").strip()
    if token != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return token


# ============================================================
# 日期解析
# ============================================================

def _parse_datetime(s: Optional[str]) -> Optional[datetime]:
    """解析 iOS 端各种日期格式 → timezone-aware datetime (UTC)"""
    if not s:
        return None

    from dateutil import parser as dt_parser

    try:
        parsed = dt_parser.parse(s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        pass

    # Fallback: 手动修正 "YYYY-MM-DD HH:MM:SS +0000" → ISO 8601
    try:
        cleaned = re.sub(r" \+(\d{2})(\d{2})$", r"+\1:\2", s)
        if "T" not in cleaned:
            cleaned = cleaned.replace(" ", "T", 1)
        return datetime.fromisoformat(cleaned)
    except Exception:
        logger.warning(f"Failed to parse datetime: {s!r}")
        return None


# ============================================================
# POST /api/v1/health/sync — 核心接口
# ============================================================

@app.post("/api/v1/health/sync")
def receive_health_data(
    payload: HealthSyncRequest,
    target: Optional[str] = Query(None, description="用户标识（预留多用户）"),
    automation_name: Optional[str] = Header(None, alias="automation-name"),
    session_id: Optional[str] = Header(None, alias="session-id"),
    db: Session = Depends(get_db),
    _token: str = Depends(verify_api_key),
):
    """
    接收 Health Auto Export 推送的健康数据。
    Health Auto Export 自动在请求头中添加 automation-name 和 session-id。
    """
    now = datetime.now(timezone.utc)
    export = payload.get_payload()
    metrics_count = len(export.metrics)
    data_points_count = 0
    workouts_count = len(export.workouts)

    if automation_name or session_id:
        logger.info(f"Sync from automation='{automation_name}' session='{session_id}'")

    # ── 处理 metrics ──
    agg_errors = []
    for metric in export.metrics:
        try:
            inserted = _insert_metric_samples(db, metric, target, now)
            data_points_count += inserted
        except Exception as e:
            logger.error(f"Failed to insert metric '{metric.name}': {e}", exc_info=True)
            _log_sync(db, metrics_count, data_points_count, workouts_count,
                      "partial", str(e), now)
            return JSONResponse(
                content={
                    "status": "partial",
                    "error": f"Metric '{metric.name}' failed: {str(e)}",
                    "metrics_received": metrics_count,
                    "data_points_inserted": data_points_count,
                    "workouts_received": workouts_count,
                },
                status_code=207,
            )

    # ── 处理 workouts ──
    for workout in export.workouts:
        try:
            _insert_workout(db, workout, target, now)
        except Exception as e:
            logger.error(f"Failed to insert workout '{workout.name}': {e}", exc_info=True)

    # ── 增量聚合 ──
    try:
        aggregate_daily_metrics(db, date.today())
    except Exception as e:
        logger.error(f"Aggregation failed: {e}", exc_info=True)
        agg_errors.append(str(e))

    # ── 记录同步日志 ──
    _log_sync(db, metrics_count, data_points_count, workouts_count, "success", None, now)

    return {
        "status": "success",
        "metrics_received": metrics_count,
        "data_points_inserted": data_points_count,
        "workouts_received": workouts_count,
        "aggregation_errors": agg_errors if agg_errors else None,
    }


# ============================================================
# 内部辅助函数
# ============================================================

def _insert_metric_samples(db: Session, metric: HealthMetric, target: Optional[str],
                           received_at: datetime) -> int:
    """将单个 HealthMetric 的 data[] 数组批量写入 raw_health_samples"""
    count = 0
    for dp in metric.data:
        value = _extract_value(dp, metric.name)

        # 解析时间：优先 startDate（睡眠分析/训练），否则 date
        start_time = (
            _parse_datetime(dp.startDate) if dp.startDate
            else _parse_datetime(dp.date)
        )
        if start_time is None:
            logger.warning(f"Skipping data point: no parseable time for metric={metric.name}")
            continue

        end_time = _parse_datetime(dp.endDate) if dp.endDate else None

        sample = RawHealthSample(
            metric_type=metric.name,
            value=value,              # 可为 None（如睡眠 inBed 标签）
            unit=metric.units,
            start_time=start_time,
            end_time=end_time,
            source=dp.source,
            device=target,
            received_at=received_at,
            extra=_build_extra(dp),
        )
        db.add(sample)
        count += 1

    db.commit()
    return count


def _extract_value(dp, metric_name: str) -> Optional[float]:
    """
    从不同格式的 MetricDataPoint 中提取核心数值。

    优先级:
      1. avg  — 心率等聚合型数据
      2. qty  — 步数、距离、HRV 等单值型数据
      3. totalSleep — 睡眠聚合模式的睡眠总时长（小时→分钟）
      4. 睡眠时长 — 从 startDate/endDate 计算（分钟）
    """
    if dp.avg is not None:
        return float(dp.avg)
    if dp.qty is not None:
        return float(dp.qty)
    if dp.totalSleep is not None:
        return round(float(dp.totalSleep) * 60, 1)   # 小时 → 分钟
    if dp.startDate and dp.endDate:
        try:
            start = _parse_datetime(dp.startDate)
            end = _parse_datetime(dp.endDate)
            if start and end:
                return round((end - start).total_seconds() / 60.0, 1)  # 分钟
        except Exception:
            pass
    return None


def _build_extra(dp) -> Optional[str]:
    """将 Pydantic 模型中不在主列中的字段序列化为 extra JSON"""
    extra_fields = {}

    # 心率 min/max
    for key in ("min", "max", "value"):
        val = getattr(dp, key, None)
        if val is not None:
            extra_fields[key] = val

    # 睡眠聚合模式特有字段
    for key in ("totalSleep", "asleep", "core", "deep", "rem",
                "sleepStart", "sleepEnd", "inBed", "inBedStart", "inBedEnd"):
        val = getattr(dp, key, None)
        if val is not None:
            extra_fields[key] = val

    # 血压
    if dp.systolic is not None:
        extra_fields["systolic"] = dp.systolic
    if dp.diastolic is not None:
        extra_fields["diastolic"] = dp.diastolic

    # 血糖
    if dp.mealTime is not None:
        extra_fields["mealTime"] = dp.mealTime

    if extra_fields:
        return json.dumps(extra_fields, ensure_ascii=False)
    return None


def _insert_workout(db: Session, workout: WorkoutData, target: Optional[str],
                    received_at: datetime):
    """将训练数据写入 raw_health_samples"""
    # 兼容 V1 和 V2: V2 用 start/end, V1 用 startDate/endDate
    start = _parse_datetime(workout.start or workout.startDate)
    end = _parse_datetime(workout.end or workout.endDate)

    if not start:
        logger.warning(f"Skipping workout '{workout.name}': no parseable time")
        return

    workout_data = {
        "duration_sec": workout.duration,
        "active_energy_kJ": workout.activeEnergy_kJ,
        "distance_m": workout.distance_m,
        "avg_heart_rate_bpm": workout.avgHeartRate_bpm,
        "max_heart_rate_bpm": workout.maxHeartRate_bpm,
        "location": workout.location,
    }

    metric_type = f"workout_{workout.name.lower().replace(' ', '_')}"

    sample = RawHealthSample(
        metric_type=metric_type,
        value=workout.duration,
        unit="seconds",
        start_time=start,
        end_time=end,
        source="Apple Watch",
        device=target,
        received_at=received_at,
        extra=json.dumps({k: v for k, v in workout_data.items() if v is not None},
                         ensure_ascii=False),
    )
    db.add(sample)
    db.commit()


def _log_sync(db: Session, metrics_count: int, data_points: int,
              workouts_count: int, status: str, error_msg: Optional[str],
              received_at: datetime):
    """写入同步日志"""
    log = SyncLog(
        received_at=received_at,
        metrics_count=metrics_count,
        data_points_count=data_points,
        workouts_count=workouts_count,
        status=status,
        error_message=error_msg,
    )
    db.add(log)
    db.commit()


# ============================================================
# 查询 API
# ============================================================

@app.get("/api/v1/health/daily")
def get_daily_metrics(
    date: str = Query(..., description="日期 YYYY-MM-DD（兼容 2026-5-11）"),
    metric: Optional[str] = Query(None, description="指标名，不传返回全部"),
    db: Session = Depends(get_db),
):
    """查询某一天的聚合指标"""
    # 标准化日期格式（2026-5-11 → 2026-05-11）
    from dateutil import parser as dt_parser
    try:
        parsed = dt_parser.parse(date)
        normalized = parsed.strftime("%Y-%m-%d")
    except Exception:
        normalized = date  # fallback
    q = db.query(DailyMetric).filter(DailyMetric.date == normalized)
    if metric:
        q = q.filter(DailyMetric.metric_type == metric)

    results = q.all()
    return {
        "date": date,
        "count": len(results),
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
    metric_type: str = Query(..., description="指标名"),
    date_from: str = Query(..., description="起始日期 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD（不含）"),
    limit: int = Query(1000, ge=1, le=10000, description="返回上限"),
    db: Session = Depends(get_db),
):
    """查询原始健康数据点"""
    from dateutil import parser as dt_parser
    start = dt_parser.parse(date_from)
    end = dt_parser.parse(date_to) if date_to else None

    q = db.query(RawHealthSample).filter(
        RawHealthSample.metric_type == metric_type,
        RawHealthSample.start_time >= start,
    )
    if end:
        q = q.filter(RawHealthSample.start_time < end)

    results = (
        q.order_by(RawHealthSample.start_time.asc())
        .limit(limit)
        .all()
    )

    return {
        "metric_type": metric_type,
        "date_from": date_from,
        "date_to": date_to,
        "count": len(results),
        "truncated": len(results) >= limit,
        "samples": [
            {
                "value": r.value,
                "unit": r.unit,
                "start_time": r.start_time.isoformat() if r.start_time else None,
                "end_time": r.end_time.isoformat() if r.end_time else None,
                "source": r.source,
                "extra": json.loads(r.extra) if r.extra else None,
            }
            for r in results
        ],
    }


@app.get("/api/v1/health/baseline")
def get_baseline(
    metric_type: str = Query(..., description="指标名"),
    days: int = Query(30, ge=7, le=90, description="基线窗口（天）"),
    db: Session = Depends(get_db),
):
    """
    查询个人基线（30 天均值 ± 2σ），供 Phase 3 感知 Agent 消费。

    返回: {"mean": ..., "std": ..., "upper_bound": ..., "lower_bound": ..., "n_days": ...}
    """
    result = compute_baseline(db, metric_type, days)
    return {
        "metric_type": metric_type,
        "window_days": days,
        **result,
    }


@app.get("/api/v1/health/status")
def get_status(db: Session = Depends(get_db)):
    """查看数据库概览 & 最近同步状态"""
    from sqlalchemy import func

    total_raw = db.query(func.count(RawHealthSample.id)).scalar() or 0
    total_daily = db.query(func.count(DailyMetric.id)).scalar() or 0
    last_sync = db.query(SyncLog).order_by(SyncLog.received_at.desc()).first()

    # 各指标数据量 Top 20
    metric_counts = (
        db.query(RawHealthSample.metric_type, func.count(RawHealthSample.id))
        .group_by(RawHealthSample.metric_type)
        .order_by(func.count(RawHealthSample.id).desc())
        .limit(20)
        .all()
    )

    # 空值比例
    null_count = (
        db.query(func.count(RawHealthSample.id))
        .filter(RawHealthSample.value.is_(None))
        .scalar() or 0
    )

    return {
        "database": {
            "total_raw_samples": total_raw,
            "null_value_samples": null_count,
            "null_ratio": round(null_count / total_raw, 4) if total_raw > 0 else 0,
            "total_daily_metrics": total_daily,
        },
        "metric_types_top20": {m: c for m, c in metric_counts},
        "last_sync": {
            "time": last_sync.received_at.isoformat() if last_sync else None,
            "status": last_sync.status if last_sync else None,
            "data_points_count": last_sync.data_points_count if last_sync else 0,
            "workouts_count": last_sync.workouts_count if last_sync else 0,
        } if last_sync else None,
    }


# ============================================================
# 模型设置 — 运行时动态切换 LLM
# ============================================================

from pydantic import BaseModel as PydanticBaseModel


class ChangeModelRequest(PydanticBaseModel):
    provider: str  # PROVIDER_CONFIGS 中的 key，如 "qwen3.7-max", "deepseek-v4-pro"


@app.get("/api/v1/settings/models")
def list_models():
    """
    获取所有可用模型列表（前端下拉菜单数据源）。

    返回按 series 分组的模型列表，标记当前选中的模型和 API Key 可用性。
    """
    from config.llm import model_manager
    providers = model_manager.list_available_providers()
    current = model_manager.get_provider()

    # 按 series 分组
    grouped = {}
    for p in providers:
        series = p["series"]
        if series not in grouped:
            grouped[series] = []
        grouped[series].append({
            "key": p["key"],
            "model_name": p["model_name"],
            "desc": p["desc"],
            "available": p["available"],
            "is_current": p["key"] == current,
        })

    return {
        "current": current,
        "grouped": grouped,
        "total": len(providers),
    }


@app.get("/api/v1/settings/model")
def get_current_model():
    """获取当前正在使用的模型信息。"""
    from config.llm import model_manager, PROVIDER_CONFIGS
    current = model_manager.get_provider()
    cfg = PROVIDER_CONFIGS.get(current, {})
    return {
        "provider": current,
        "model_name": cfg.get("model_name", ""),
        "desc": cfg.get("desc", ""),
        "series": cfg.get("series", "other"),
    }


@app.post("/api/v1/settings/model")
def change_model(req: ChangeModelRequest):
    """
    动态切换模型，无需重启后端即时生效。

    切换后所有后续的 /api/v1/chat 请求将使用新模型。
    """
    from config.llm import model_manager
    try:
        result = model_manager.set_provider(req.provider)
        return {
            "status": "ok",
            "message": f"模型已切换: {result['previous']} → {result['current']}",
            **result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/api/v1/settings/model/history")
def get_model_history():
    """获取模型切换历史记录。"""
    from config.llm import model_manager
    return {"history": model_manager.get_history()}


@app.post("/api/v1/settings/model/test")
def test_model(req: ChangeModelRequest):
    """测试指定模型的连通性（发送一条简短消息验证）。"""
    from config.llm import test_one_provider
    result = test_one_provider(req.provider)
    if not result["ok"]:
        return {"status": "error", **result}
    return {"status": "ok", **result}


# ============================================================
# Phase 3+4: Agent 对话 & 记忆端点
# ============================================================


class ChatRequest(PydanticBaseModel):
    query: str
    session_id: Optional[str] = None


@app.post("/api/v1/chat")
def chat_endpoint(req: ChatRequest):
    """Phase 4 多轮对话。返回 session_id 用于后续追问。"""
    from agents.graph import chat as agent_chat, clear_progress
    result = agent_chat(query=req.query, session_id=req.session_id)
    # 延迟清理：返回结果后保留5秒供前端最后一次拉取进度
    import threading
    def _delayed_clear():
        import time
        time.sleep(5)
        clear_progress(result["session_id"])
    threading.Thread(target=_delayed_clear, daemon=True).start()
    return result


@app.get("/api/v1/chat/progress")
def get_chat_progress(session_id: str = Query(..., description="会话ID")):
    """查询对话处理的实时进度事件（前端轮询用）"""
    from agents.graph import get_progress
    events = get_progress(session_id)
    return {"session_id": session_id, "events": events}


# ── Phase 4: 对话记忆 ──
from memory.database import get_memory_db

@app.get("/api/v1/memory/sessions")
def get_sessions(db: Session = Depends(get_memory_db)):
    """列出最近活跃的 session"""
    from memory.history import list_sessions
    return {"sessions": list_sessions(db)}


@app.get("/api/v1/memory/history")
def get_chat_history(
    session_id: str = Query(...),
    n: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_memory_db),
):
    """查询某 session 的对话历史"""
    from memory.history import get_recent_history
    history = get_recent_history(db, session_id, n)
    return {"session_id": session_id, "turns": len(history) // 2, "history": history}


@app.delete("/api/v1/memory/sessions/{session_id}")
def clear_session(session_id: str, db: Session = Depends(get_memory_db)):
    """清除指定 session（前端清除按钮）"""
    from memory.history import clear_session
    count = clear_session(db, session_id)
    return {"session_id": session_id, "deleted": count}


# ── Phase 4: 周报 ──

class WeeklyRequest(PydanticBaseModel):
    week_start: Optional[str] = None  # "YYYY-MM-DD" 周一，默认本周一


@app.post("/api/v1/report/weekly")
def create_weekly_report(req: WeeklyRequest, db: Session = Depends(get_db)):
    """生成周报（默认本周）"""
    from datetime import date
    from memory.weekly import generate_weekly_report
    ws = date.fromisoformat(req.week_start) if req.week_start else None
    return generate_weekly_report(db, ws)


@app.get("/api/v1/report/weekly")
def query_weekly_report(
    week_start: str = Query(...),
    db: Session = Depends(get_db),
):
    """查询历史周报"""
    from datetime import date
    from memory.weekly import get_weekly_report
    ws = date.fromisoformat(week_start)
    result = get_weekly_report(db, ws)
    if not result:
        raise HTTPException(status_code=404, detail="周报不存在，请先生成")
    return result


@app.get("/api/v1/report/weekly/list")
def list_weekly_reports(db: Session = Depends(get_db)):
    """列出最近 12 份历史周报"""
    from memory.weekly import list_weekly_reports
    return {"reports": list_weekly_reports(db)}


@app.api_route("/api/v1/report/weekly", methods=["DELETE"])
def delete_weekly_report(
    week_start: str = Query(..., description="周起始日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """删除指定周报"""
    from datetime import date as dt_date
    from memory.schema import WeeklyReport
    ws = dt_date.fromisoformat(week_start)
    row = db.query(WeeklyReport).filter(WeeklyReport.week_start == ws).first()
    if not row:
        raise HTTPException(status_code=404, detail="周报不存在")
    db.delete(row)
    db.commit()
    logger.info(f"Weekly report deleted: {week_start}")
    return {"deleted": week_start}


# ── Phase 4: 健康趋势 ──

@app.get("/api/v1/health/trend")
def get_health_trend(
    metric: str = Query(..., description="指标名，如 heart_rate"),
    weeks: int = Query(7, ge=2, le=366),
    granularity: str = Query("day", description="day | week"),
    db: Session = Depends(get_db),
):
    """健康指标趋势（day=每日数据点, week=按周聚合）"""
    from memory.trend import get_trend
    return get_trend(db, metric, weeks, granularity)


# ============================================================
# Phase 5+: 手动 JSON 上传
# ============================================================

@app.post("/api/v1/health/upload")
def upload_weekly_json(
    file: UploadFile = File(..., description="Health Auto Export 导出的 JSON 文件"),
    db: Session = Depends(get_db),
):
    """
    接收每周 Health Auto Export JSON 文件 → 校验 → 入库 → 聚合 → 存档。

    校验流程:
      1. 文件名去重（同名 JSON 拒绝导入）
      2. JSON 格式校验（必须有 data.metrics 字段）
      3. 全量解析 metrics → 写入 raw_health_samples（事务）
      4. 触发该周日期范围内每日聚合 → 写入 daily_metrics
      5. 原始 JSON 存档到 data/weekly_raw/

    全部回滚：任何步骤失败 → raw 写入回滚 + JSON 不存档。
    """
    from .upload_handler import (
        handle_upload,
        DuplicateError,
        FormatError,
        UploadSizeError,
    )

    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="仅支持 .json 文件")

    try:
        file_bytes = file.file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取文件失败: {e}")

    try:
        result = handle_upload(
            file_bytes=file_bytes,
            filename=file.filename,
            db=db,
        )
    except DuplicateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UploadSizeError as e:
        raise HTTPException(status_code=413, detail=str(e))
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")

    return result


@app.get("/api/v1/health/upload/list")
def list_uploaded_files_endpoint():
    """查询已导入的周文件列表（扫描 data/weekly_raw/ 目录）"""
    from .upload_handler import list_uploaded_files
    files = list_uploaded_files()
    return {
        "count": len(files),
        "directory": os.getenv("WEEKLY_RAW_DIR", "data/weekly_raw"),
        "files": files,
    }


@app.delete("/api/v1/health/upload/{filename}")
def delete_uploaded_file(filename: str, db: Session = Depends(get_db)):
    """
    删除已上传的周文件及其对应的 raw 数据和聚合数据。

    联动删除流程（方案A：基于日期范围匹配）：
      1. 检查存档文件是否存在
      2. 读取存档 JSON，提取日期范围
      3. 事务：删除 raw_health_samples + daily_metrics
      4. 提交后删除存档文件

    返回:
        {"deleted": filename, "raw_deleted": N, "daily_deleted": M, "dates": [...]}
    """
    from .upload_handler import delete_upload

    try:
        result = delete_upload(filename=filename, db=db)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Delete failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")

    return result


# ============================================================
# 日历看板：按月批量查询日聚合数据
# ============================================================

@app.get("/api/v1/health/daily/batch")
def get_daily_batch(
    month: str = Query(..., description="月份 YYYY-MM，如 2026-07"),
    db: Session = Depends(get_db),
):
    """
    按月批量查询日聚合数据，用于日历看板展示。

    返回该月每天的核心指标摘要，格式：
    {
      "month": "2026-07",
      "days": {
        "2026-07-01": {
          "heart_rate": {"avg": 72, "min": 58, "max": 95},
          "step_count": {"total": 8234},
          ...
        },
        ...
      }
    }
    """
    from datetime import date as dt_date
    from calendar import monthrange

    try:
        year, mon = map(int, month.split("-"))
        if mon < 1 or mon > 12:
            raise ValueError
    except Exception:
        raise HTTPException(status_code=400, detail=f"月份格式错误: {month}，应为 YYYY-MM")

    # 计算该月的日期范围
    _, days_in_month = monthrange(year, mon)
    start_date = dt_date(year, mon, 1)
    end_date = dt_date(year, mon, days_in_month)

    # 批量查询该月所有 daily_metrics
    rows = (
        db.query(DailyMetric)
        .filter(
            DailyMetric.date >= start_date,
            DailyMetric.date <= end_date,
        )
        .all()
    )

    # 按日期分组
    days = {}
    for r in rows:
        date_str = str(r.date)
        if date_str not in days:
            days[date_str] = {}

        # 只返回核心指标（日历卡片展示用）
        CORE_METRICS = {
            "heart_rate", "resting_heart_rate", "heart_rate_variability",
            "step_count", "active_energy", "basal_energy_burned",
            "sleep_analysis", "respiratory_rate", "walking_running_distance",
            "apple_exercise_time", "flights_climbed", "vo2_max",
        }

        if r.metric_type in CORE_METRICS:
            days[date_str][r.metric_type] = {
                "avg": r.avg_value,
                "min": r.min_value,
                "max": r.max_value,
                "total": r.total_value,
                "samples": r.sample_count,
                "unit": r.unit,
            }

    return {
        "month": month,
        "days_in_month": days_in_month,
        "days": days,
    }


# ============================================================
# v4: 单日健康分析
# ============================================================

DAILY_SYSTEM = """Write a single-day health analysis based on one day of monitoring data.

Output format (in Chinese):
1. 日期 — 确认分析的日期
2. 核心指标 — 列出当日心率、步数、能量、睡眠等核心指标（有数据则列具体数值，无数据则标注"当日无数据"）
3. 日内特征 — 对比个人基线，指出突出或异常的数据点
4. 简短建议 — 1-2条针对明日的建议
Keep it under 200 words."""


class DailyAnalysisRequest(PydanticBaseModel):
    date: str  # "YYYY-MM-DD"


@app.post("/api/v1/health/daily-analysis")
def create_daily_analysis(req: DailyAnalysisRequest, db: Session = Depends(get_db)):
    """
    生成单日健康分析（非周报）并持久化。
    接受日期 → 查询该日聚合指标 → LLM 生成分析 → 存入 daily_analyses 表。
    """
    from datetime import date as dt_date
    from dateutil import parser as dt_parser
    from config.llm import get_action_llm
    from memory.schema import DailyAnalysis

    try:
        parsed = dt_parser.parse(req.date)
        target_date = parsed.strftime("%Y-%m-%d")
    except Exception:
        raise HTTPException(status_code=400, detail=f"日期格式错误: {req.date}")

    target = dt_date.fromisoformat(target_date)

    # 查重 — 已存在则直接返回
    existing = db.query(DailyAnalysis).filter(DailyAnalysis.target_date == target).first()
    if existing:
        return {
            "date": str(existing.target_date),
            "narrative": existing.narrative,
            "metrics": json.loads(existing.metrics_json) if existing.metrics_json else {},
            "created_at": existing.created_at.isoformat() if existing.created_at else None,
            "cached": True,
        }

    # 查询当日所有聚合指标
    rows = (
        db.query(DailyMetric)
        .filter(DailyMetric.date == target_date)
        .all()
    )

    if not rows:
        narrative = f"## {target_date} 健康分析\n\n该日期暂无健康数据。请确认已上传并聚合了对应日期的数据。"
        metrics_json = "{}"
        data_points = 0
    else:
        metrics_summary = {}
        for r in rows:
            metrics_summary[r.metric_type] = {
                "avg": r.avg_value, "min": r.min_value, "max": r.max_value,
                "total": r.total_value, "samples": r.sample_count, "unit": r.unit,
            }
        core_keys = [
            "heart_rate", "resting_heart_rate", "heart_rate_variability",
            "step_count", "active_energy", "basal_energy_burned",
            "sleep_analysis", "respiratory_rate", "walking_running_distance",
            "apple_exercise_time",
        ]
        core = {k: metrics_summary[k] for k in core_keys if k in metrics_summary}
        core_json = json.dumps(core, ensure_ascii=False, indent=2)
        metrics_json = json.dumps(metrics_summary, ensure_ascii=False)
        data_points = len(rows)

        llm = get_action_llm()
        prompt = f"{DAILY_SYSTEM}\n\nDate: {target_date}\nCore metrics: {core_json}"
        try:
            narrative = llm.invoke(prompt).content
        except Exception as e:
            logger.error(f"LLM daily analysis failed: {e}")
            narrative = f"## {target_date} 健康分析\n\nLLM 调用失败，以下为当日原始数据摘要。\n\n请稍后重试。"

    # 持久化
    record = DailyAnalysis(
        target_date=target,
        narrative=narrative,
        metrics_json=metrics_json,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "date": str(record.target_date),
        "narrative": record.narrative,
        "metrics": json.loads(record.metrics_json) if record.metrics_json else {},
        "data_points": data_points,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@app.get("/api/v1/health/daily-analysis")
def get_daily_analysis(
    date: str = Query(..., description="日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """查询某一天的分析报告"""
    from datetime import date as dt_date
    from memory.schema import DailyAnalysis
    target = dt_date.fromisoformat(date)
    row = db.query(DailyAnalysis).filter(DailyAnalysis.target_date == target).first()
    if not row:
        raise HTTPException(status_code=404, detail="该日期的分析报告不存在，请先生成")
    return {
        "date": str(row.target_date),
        "narrative": row.narrative,
        "metrics": json.loads(row.metrics_json) if row.metrics_json else {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@app.get("/api/v1/health/daily-analysis/list")
def list_daily_analyses(db: Session = Depends(get_db)):
    """列出最近 30 份日分析报告"""
    from memory.schema import DailyAnalysis
    rows = (
        db.query(DailyAnalysis)
        .order_by(DailyAnalysis.target_date.desc())
        .limit(30)
        .all()
    )
    return {
        "analyses": [
            {
                "date": str(r.target_date),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@app.delete("/api/v1/health/daily-analysis")
def delete_daily_analysis(
    date: str = Query(..., description="日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """删除某一天的日分析报告"""
    from datetime import date as dt_date
    from memory.schema import DailyAnalysis
    target = dt_date.fromisoformat(date)
    row = db.query(DailyAnalysis).filter(DailyAnalysis.target_date == target).first()
    if not row:
        raise HTTPException(status_code=404, detail="该日期的分析报告不存在")
    db.delete(row)
    db.commit()
    return {"deleted": date}


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)
