"""健康数据感知节点 — 消费 Phase 1 数据"""
import logging
from datetime import date

from config.llm import get_perception_llm
from data_pipeline.database import SessionLocal
from data_pipeline.aggregator import compute_baseline
from data_pipeline.models import DailyMetric
from agents.state import AgentState
from prompts.perception import PERCEPTION_SYSTEM, PERCEPTION_USER
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("agent.perception")


def perception_node(state: AgentState) -> dict:
    """读取今日健康聚合数据 + 30天基线，生成结构化摘要"""
    db = SessionLocal()
    try:
        today = date.today()
        today_metrics = (
            db.query(DailyMetric)
            .filter(DailyMetric.date == today)
            .all()
        )

        if not today_metrics:
            logger.info(f"No daily_metrics for {today}")
            return {
                "health_metrics": None,
                "personal_context": "今日暂无健康数据。请确保 iPhone Health Auto Export 已完成同步。",
            }

        metrics_summary_lines = []
        baseline_lines = []
        health_metrics = {}

        for m in today_metrics:
            bl = compute_baseline(db, m.metric_type, days=30)
            deviation = None
            if (
                bl.get("mean") is not None
                and bl.get("std") is not None
                and bl["std"] > 0
            ):
                deviation = round(
                    (m.avg_value - bl["mean"]) / bl["std"], 2
                )

            metrics_summary_lines.append(
                f"- {m.metric_type}: avg={m.avg_value}, min={m.min_value}, "
                f"max={m.max_value}, stddev={m.stddev_value}, samples={m.sample_count}"
            )

            if bl.get("mean") is not None:
                baseline_lines.append(
                    f"- {m.metric_type}: 30d均值={bl['mean']}, "
                    f"范围=[{bl['lower_bound']}, {bl['upper_bound']}]"
                    + (f", 偏离={deviation}σ" if deviation is not None else "")
                )

            health_metrics[m.metric_type] = {
                "avg": m.avg_value,
                "min": m.min_value,
                "max": m.max_value,
                "stddev": m.stddev_value,
                "samples": m.sample_count,
                "baseline_mean": bl.get("mean"),
                "upper_bound": bl.get("upper_bound"),
                "lower_bound": bl.get("lower_bound"),
                "deviation_sigma": deviation,
            }
    finally:
        db.close()

    # LLM 生成叙事
    llm = get_perception_llm()
    messages = [
        SystemMessage(content=PERCEPTION_SYSTEM),
        HumanMessage(content=PERCEPTION_USER.format(
            metrics_summary="\n".join(metrics_summary_lines),
            baseline_context="\n".join(baseline_lines),
        )),
    ]
    narrative = llm.invoke(messages).content

    logger.info(
        f"Perception: {len(health_metrics)} metrics analyzed"
    )

    return {
        "health_metrics": health_metrics,
        "personal_context": narrative,
    }
