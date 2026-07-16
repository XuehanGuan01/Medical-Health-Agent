"""
上传处理器 — 接收每周 Health Auto Export JSON → 校验 → 入库 → 聚合 → 存档。

流程:
  1. 文件名去重 — weekly_raw/{filename} 已存在则拒绝 400 Duplicate
  2. JSON 格式校验 — 非 {"data": {"metrics": [...]}} 结构 → 400 Invalid format
  3. 全量解析所有 metrics → 逐一写入 raw 表（事务）
  4. 触发该周日期范围日聚合 → 写入 daily_metrics
  5. 原始 JSON 写入 data/weekly_raw/{filename} 存档

全部回滚策略：任一步骤失败 → raw 写入回滚 + JSON 不存档。
"""
import json
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from .config import WEEKLY_RAW_DIR, MAX_UPLOAD_SIZE_MB, AGGREGATION_METRICS
from .models import (
    HealthMetric,
    WorkoutData,
    RawHealthSample,
    DailyMetric,
    SyncLog,
)
from .aggregator import aggregate_daily_metrics

logger = logging.getLogger("upload-handler")


# ============================================================
# 自定义异常
# ============================================================

class DuplicateError(Exception):
    """文件已导入过"""


class FormatError(Exception):
    """JSON 格式不符合 Health Auto Export 规范"""


class UploadSizeError(Exception):
    """文件超过大小限制"""


# ============================================================
# 核心入口
# ============================================================

def handle_upload(file_bytes: bytes, filename: str, db: Session) -> dict:
    """
    处理一次 JSON 文件上传。

    参数:
        file_bytes: 上传文件的原始字节
        filename:    原始文件名（用于去重 + 存档）
        db:          SQLAlchemy Session

    返回:
        {"status": "ok", "filename": ..., "week_start": ..., "week_end": ...,
         "metrics_count": ..., "data_points_inserted": ..., "days_aggregated": ...}

    异常:
        DuplicateError  — 文件名重复
        FormatError     — JSON 结构不符合预期
        UploadSizeError — 文件过大
    """
    # ── 0. 大小检查 ──
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_SIZE_MB:
        raise UploadSizeError(
            f"文件大小 {size_mb:.1f}MB 超过限制（{MAX_UPLOAD_SIZE_MB}MB）。"
            f"请上传单周文件（通常 < 200KB）。"
        )
    logger.info(f"Upload check: {filename} ({size_mb:.2f}MB)")

    # ── 1. 文件名去重 ──
    archive_path = _archive_path(filename)
    if os.path.exists(archive_path):
        raise DuplicateError(f"文件 {filename} 已导入过")

    # ── 2. 解析 JSON ──
    try:
        data = json.loads(file_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise FormatError(f"JSON 解析失败: {e}")

    # 校验顶层结构: {"data": {"metrics": [...]}}
    if "data" not in data:
        raise FormatError("缺少顶层 'data' 字段，请确认是 Health Auto Export 导出的 JSON")
    inner = data["data"]
    if "metrics" not in inner or not isinstance(inner["metrics"], list):
        raise FormatError("缺少 'data.metrics' 字段或格式不正确，请确认是 Health Auto Export 导出的 JSON")

    metrics_raw = inner["metrics"]
    workouts_raw = inner.get("workouts", [])

    if not metrics_raw:
        raise FormatError("data.metrics 为空数组，文件中没有健康数据")

    # ── 3. 解析所有 metrics → Pydantic 模型 ──
    metrics: list[HealthMetric] = []
    parse_errors: list[str] = []
    for i, m in enumerate(metrics_raw):
        try:
            metrics.append(HealthMetric(**m))
        except Exception as e:
            parse_errors.append(f"指标 #{i} ({m.get('name', 'unknown')}): {e}")

    if parse_errors:
        raise FormatError(
            f"指标解析失败（{len(parse_errors)}/{len(metrics_raw)}）:\n" +
            "\n".join(parse_errors[:5])  # 最多展示5条
        )

    # ── 4. 事务写入 ──
    received_at = datetime.now(timezone.utc)
    data_points_inserted = 0
    workouts_inserted = 0

    try:
        # 4a. 写入所有 metrics
        for metric in metrics:
            inserted = _insert_metric_samples(db, metric, received_at)
            data_points_inserted += inserted

        # 4b. 写入 workouts（如有）
        for w in workouts_raw:
            try:
                workout = WorkoutData(**w)
                _insert_workout(db, workout, received_at)
                workouts_inserted += 1
            except Exception as e:
                logger.warning(f"Workout 解析失败 '{w.get('name', 'unknown')}': {e}")
                # workout 不影响整体事务，跳过

        # 4c. 提取日期范围并聚合
        dates = _extract_date_range(metrics)
        if not dates:
            raise FormatError("无法从数据中提取日期范围")

        week_start = min(dates)
        week_end = max(dates)
        days_aggregated = 0
        agg_errors: list[str] = []

        for d in dates:
            try:
                aggregate_daily_metrics(db, d)
                days_aggregated += 1
            except Exception as e:
                agg_errors.append(f"{d}: {e}")
                logger.error(f"Aggregation failed for {d}: {e}", exc_info=True)

        if agg_errors:
            raise Exception(f"聚合失败（{len(agg_errors)}/{len(dates)} 天）: " + "; ".join(agg_errors[:3]))

        # ── 5. 记录同步日志 ──
        _log_upload(db, len(metrics), data_points_inserted, workouts_inserted,
                    "success", None, received_at)

        db.commit()
        logger.info(f"Upload committed: {filename}, {data_points_inserted} points, "
                    f"{days_aggregated} days aggregated")

    except Exception:
        db.rollback()
        logger.error(f"Upload failed, transaction rolled back: {filename}", exc_info=True)
        raise

    # ── 6. 存档原始 JSON ──
    os.makedirs(os.path.dirname(archive_path), exist_ok=True)
    with open(archive_path, "wb") as f:
        f.write(file_bytes)

    return {
        "status": "ok",
        "filename": filename,
        "week_start": str(week_start),
        "week_end": str(week_end),
        "metrics_count": len(metrics),
        "data_points_inserted": data_points_inserted,
        "workouts_inserted": workouts_inserted,
        "days_aggregated": days_aggregated,
    }


# ============================================================
# 内部辅助函数
# ============================================================

def _archive_path(filename: str) -> str:
    """计算存档路径: data/weekly_raw/{filename}"""
    return os.path.join(WEEKLY_RAW_DIR, os.path.basename(filename))


def _extract_date_range(metrics: list[HealthMetric]) -> list[date]:
    """
    从所有 metrics 的数据点中提取覆盖的日期列表（去重、排序）。

    日期来源优先级:
      1. data[].date  — 大多数日聚合型指标
      2. data[].startDate — 睡眠等区间型指标
    所有日期强制转为当地时间日期（忽略时区偏移）。
    """
    dates_set: set[date] = set()
    for metric in metrics:
        for dp in metric.data:
            d = _extract_date_from_dp(dp)
            if d:
                dates_set.add(d)
    return sorted(dates_set)


def _extract_date_from_dp(dp) -> Optional[date]:
    """从单个数据点提取日期"""
    from dateutil import parser as dt_parser

    date_str = dp.date or dp.startDate
    if not date_str:
        return None

    try:
        parsed = dt_parser.parse(date_str)
        return parsed.date()
    except Exception:
        return None


def _insert_metric_samples(db: Session, metric: HealthMetric,
                           received_at: datetime) -> int:
    """
    将单个 HealthMetric 的 data[] 数组批量写入 raw_health_samples。

    复用 Phase 1 的插入逻辑，与 webhook_server._insert_metric_samples 等价。
    """
    count = 0
    for dp in metric.data:
        value = _extract_value(dp, metric.name)

        # 解析时间：优先 startDate（睡眠分析/训练），否则 date
        start_time = _parse_datetime(dp.startDate) if dp.startDate else _parse_datetime(dp.date)
        if start_time is None:
            logger.warning(f"Skipping data point: no parseable time for metric={metric.name}")
            continue

        end_time = _parse_datetime(dp.endDate) if dp.endDate else None

        sample = RawHealthSample(
            metric_type=metric.name,
            value=value,
            unit=metric.units,
            start_time=start_time,
            end_time=end_time,
            source=dp.source,
            device=None,
            received_at=received_at,
            extra=_build_extra(dp),
        )
        db.add(sample)
        count += 1

    # 逐条 flush 让后续聚合可见，但不 commit（由外层事务控制）
    db.flush()
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
        return round(float(dp.totalSleep) * 60, 1)
    if dp.startDate and dp.endDate:
        try:
            start = _parse_datetime(dp.startDate)
            end = _parse_datetime(dp.endDate)
            if start and end:
                return round((end - start).total_seconds() / 60.0, 1)
        except Exception:
            pass
    return None


def _build_extra(dp) -> Optional[str]:
    """将 Pydantic 模型中不在主列中的字段序列化为 extra JSON"""
    extra_fields = {}

    for key in ("min", "max", "value"):
        val = getattr(dp, key, None)
        if val is not None:
            extra_fields[key] = val

    for key in ("totalSleep", "asleep", "core", "deep", "rem",
                "sleepStart", "sleepEnd", "inBed", "inBedStart", "inBedEnd"):
        val = getattr(dp, key, None)
        if val is not None:
            extra_fields[key] = val

    if dp.systolic is not None:
        extra_fields["systolic"] = dp.systolic
    if dp.diastolic is not None:
        extra_fields["diastolic"] = dp.diastolic

    if dp.mealTime is not None:
        extra_fields["mealTime"] = dp.mealTime

    if extra_fields:
        return json.dumps(extra_fields, ensure_ascii=False)
    return None


def _insert_workout(db: Session, workout: WorkoutData,
                    received_at: datetime):
    """将训练数据写入 raw_health_samples"""
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
        device=None,
        received_at=received_at,
        extra=json.dumps(
            {k: v for k, v in workout_data.items() if v is not None},
            ensure_ascii=False,
        ),
    )
    db.add(sample)
    db.flush()


def _log_upload(db: Session, metrics_count: int, data_points: int,
                workouts_count: int, status: str, error_msg: Optional[str],
                received_at: datetime):
    """写入上传日志（复用 SyncLog 表）"""
    log = SyncLog(
        received_at=received_at,
        metrics_count=metrics_count,
        data_points_count=data_points,
        workouts_count=workouts_count,
        status=status,
        error_message=error_msg,
    )
    db.add(log)


# ============================================================
# 日期解析
# ============================================================

def _parse_datetime(s: Optional[str]) -> Optional[datetime]:
    """解析 iOS 端各种日期格式 → timezone-aware datetime (UTC)"""
    if not s:
        return None

    from dateutil import parser as dt_parser
    import re

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
# 已上传文件列表查询
# ============================================================

def list_uploaded_files() -> list[dict]:
    """
    扫描 data/weekly_raw/ 目录，返回已导入文件列表。

    返回:
        [{"filename": ..., "size_bytes": ..., "imported_at": "..."}, ...]
    """
    dir_path = WEEKLY_RAW_DIR
    if not os.path.isdir(dir_path):
        return []

    files = []
    for entry in sorted(os.listdir(dir_path)):
        if not entry.endswith(".json"):
            continue
        full_path = os.path.join(dir_path, entry)
        stat = os.stat(full_path)
        files.append({
            "filename": entry,
            "size_bytes": stat.st_size,
            "imported_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })

    return files
