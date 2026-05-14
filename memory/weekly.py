"""
周报生成 — 消费 Phase 1 聚合数据 + LLM 叙事

固定 周一~周日 自然周。Phase 4 Q7 决策：不支持自定义范围。
"""
import json
import logging
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from config.llm import get_action_llm
from data_pipeline.models import DailyMetric
from memory.schema import WeeklyReport

logger = logging.getLogger("memory.weekly")

WEEKLY_SYSTEM = """Write a weekly health report based on 7 days of monitoring data.

Output format (in Chinese):
1. 总览 — 一段话概括本周健康状态
2. 核心指标 — 心率/HRV/步数/能量，每项一行周均值
3. 与上周对比（如有）
4. 下周建议 — 1-2 条简短改善建议
Keep it under 400 words."""


def generate_weekly_report(db: Session, target_monday: date = None) -> dict:
    """
    生成一周健康报告。

    参数:
        target_monday: 周一日期（默认本周一）
    返回:
        {"week_start": str, "week_end": str, "narrative": str, "metrics": dict}
    """
    if target_monday is None:
        today = date.today()
        target_monday = today - timedelta(days=today.weekday())

    sunday = target_monday + timedelta(days=6)

    metrics = (
        db.query(DailyMetric)
        .filter(
            DailyMetric.date >= target_monday,
            DailyMetric.date <= sunday,
        )
        .all()
    )

    if not metrics:
        return {"error": f"No data for {target_monday} ~ {sunday}"}

    # 按指标分组
    grouped = defaultdict(list)
    for m in metrics:
        grouped[m.metric_type].append(m)

    summary = {}
    for metric_type, rows in grouped.items():
        avgs = [r.avg_value for r in rows if r.avg_value is not None]
        totals = [r.total_value for r in rows if r.total_value is not None]
        unit = rows[0].unit if rows else ""
        summary[metric_type] = {
            "week_avg": round(sum(avgs) / len(avgs), 2) if avgs else None,
            "week_total": round(sum(totals), 2) if totals else None,
            "days": len(rows),
            "unit": unit,
        }

    # LLM 叙事
    llm = get_action_llm()
    prompt = (
        f"{WEEKLY_SYSTEM}\n\n"
        f"Period: {target_monday} ~ {sunday}\n"
        f"Data: {json.dumps(summary, ensure_ascii=False, indent=2)}"
    )
    narrative = llm.invoke(prompt).content

    # 持久化
    report = WeeklyReport(
        week_start=target_monday,
        week_end=sunday,
        narrative=narrative,
        metrics_json=json.dumps(summary, ensure_ascii=False),
    )
    db.add(report)
    db.commit()

    logger.info(f"Weekly report generated: {target_monday} ~ {sunday}")

    return {
        "week_start": str(target_monday),
        "week_end": str(sunday),
        "narrative": narrative,
        "metrics": summary,
    }


def get_weekly_report(db: Session, monday: date) -> dict | None:
    """查询历史周报"""
    report = (
        db.query(WeeklyReport)
        .filter(WeeklyReport.week_start == monday)
        .first()
    )
    if not report:
        return None
    return {
        "week_start": str(report.week_start),
        "week_end": str(report.week_end),
        "narrative": report.narrative,
        "metrics": json.loads(report.metrics_json) if report.metrics_json else {},
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


def list_weekly_reports(db: Session, limit: int = 12) -> list[dict]:
    """列出最近 N 份历史周报"""
    reports = (
        db.query(WeeklyReport)
        .order_by(WeeklyReport.week_start.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "week_start": str(r.week_start),
            "week_end": str(r.week_end),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]
