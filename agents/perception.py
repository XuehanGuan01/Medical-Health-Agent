"""健康数据感知节点 (v3: 传日期 + 全量分析 + 2天窗口)"""
import logging
from datetime import date, datetime, timedelta
from collections import defaultdict

from config.llm import get_perception_llm
from data_pipeline.database import SessionLocal
from data_pipeline.aggregator import compute_baseline
from data_pipeline.models import DailyMetric
from agents.state import AgentState
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("agent.perception")

# 累积型指标：对 LLM 展示 total_value（日总量），avg（每次采样均值）无意义
CUMULATIVE_METRICS = {
    "step_count", "active_energy", "basal_energy_burned",
    "apple_exercise_time", "apple_stand_time", "apple_stand_hour",
    "walking_running_distance", "flights_climbed",
    "sleep_analysis", "cycling_distance",
    "environmental_audio_exposure", "headphone_audio_exposure",
    "time_in_daylight", "mindful_minutes", "handwashing",
}

PERCEPTION_SYSTEM = """你是专业的个人健康数据分析师。基于提供的健康数据，进行全面深入的分析。

**核心要求**：
1. 必须逐一分析每个可用指标，不得遗漏任何一个
2. 先列出原始数值，再给出解读
3. 偏离30天基线 ≥1.5σ 的指标必须单独标注并解释可能原因
4. 综合分析：心脏变异率HRV、心率、步数、能量、呼吸频率等指标之间的关联
5. 给出整体健康评分和具体建议
6. **严禁使用 --- 水平分割线**，用空行分隔段落

**输出格式**（用 Markdown 分段，清楚易读）：

## 日期: [数据日期]

**核心指标一览** (逐项列出，每项给出数值+判定)：
- 心率 (heart_rate): xx bpm (范围 xx-xx)，基线 xx bpm，[正常/偏高/偏低]
- 静息心率 (resting_heart_rate): ...
- HRV (heart_rate_variability): ...
- 步数 (step_count): ...
- 活动能量 (active_energy): ...
- [继续列出所有剩余指标...]

**异常指标分析** (如有偏离 ≥1.5σ 的指标):
- [指标名]: 偏离 xσ，可能原因...

**综合评估**:
[一段话总结整体健康状态]

**建议**:
1. [具体建议]
2. [具体建议]

⚠️ **严禁使用 --- 水平分割线**，用空行分隔段落即可。"""


def perception_node(state: AgentState) -> dict:
    today = date.today()
    three_days_ago = today - timedelta(days=2)

    query = state.get("query", "")
    db = SessionLocal()
    try:
        # 始终给 3 天数据（今天+昨天+前天），让 LLM 自行识别用户问的是哪天
        all_metrics = (
            db.query(DailyMetric)
            .filter(DailyMetric.date >= three_days_ago)
            .order_by(DailyMetric.date.desc(), DailyMetric.metric_type)
            .all()
        )

        if not all_metrics:
            return {
                "health_metrics": None,
                "personal_context": f"暂无 {today} 的健康数据。请确保 iPhone Health Auto Export 已完成同步。",
            }

        by_date = defaultdict(dict)
        for m in all_metrics:
            d = str(m.date)
            bl = compute_baseline(db, m.metric_type, days=30)
            deviation = None
            if bl.get("mean") and bl.get("std") and bl["std"] > 0:
                deviation = round((m.avg_value - bl["mean"]) / bl["std"], 2)

            by_date[d][m.metric_type] = {
                "avg": m.avg_value, "total": m.total_value,
                "min": m.min_value, "max": m.max_value,
                "stddev": m.stddev_value, "samples": m.sample_count,
                "baseline_mean": bl.get("mean"),
                "upper_bound": bl.get("upper_bound"),
                "lower_bound": bl.get("lower_bound"),
                "deviation_sigma": deviation,
            }
    finally:
        db.close()

    metric_labels = {
        "heart_rate": "Heart Rate(bpm)", "resting_heart_rate": "Resting HR(bpm)",
        "heart_rate_variability": "HRV(ms)", "step_count": "Steps",
        "active_energy": "Active Energy(kJ)", "basal_energy_burned": "Basal Energy(kJ)",
        "apple_exercise_time": "Exercise(min)", "apple_stand_time": "Stand Time(min)",
        "apple_stand_hour": "Stand Hours", "walking_running_distance": "Distance(km)",
        "flights_climbed": "Flights Climbed", "physical_effort": "Physical Effort(MET)",
        "walking_speed": "Walking Speed(m/s)", "walking_step_length": "Step Length(cm)",
        "walking_asymmetry_percentage": "Walking Asymmetry(%)",
        "walking_double_support_percentage": "Double Support(%)",
        "walking_heart_rate_average": "Walking HR Avg(bpm)",
        "stair_speed_down": "Stair Speed Down(m/s)", "stair_speed_up": "Stair Speed Up(m/s)",
        "running_power": "Running Power(W)", "running_speed": "Running Speed(m/s)",
        "running_ground_contact_time": "Ground Contact(ms)",
        "running_vertical_oscillation": "Vertical Osc(cm)",
        "running_stride_length": "Stride Length(m)", "cycling_distance": "Cycling Distance(km)",
        "respiratory_rate": "Respiratory Rate(breaths/min)",
        "sleep_analysis": "Sleep(min)",
        "environmental_audio_exposure": "Env Noise(dB)", "headphone_audio_exposure": "Headphone Noise(dB)",
        "time_in_daylight": "Daylight(min)", "mindful_minutes": "Mindful Minutes",
        "cardio_recovery": "Cardio Recovery(bpm)", "vo2_max": "VO2 Max",
        "six_minute_walking_test_distance": "6min Walk(m)",
        "weight_body_mass": "Weight(kg)", "body_fat_percentage": "Body Fat(%)",
        "body_mass_index": "BMI", "height": "Height(m)",
        "handwashing": "Handwashing(events)",
        "blood_oxygen_saturation": "SpO2(%)", "wrist_temperature": "Wrist Temp(degC)",
    }

    lines = [
        f"**Current date (today): {today}**",
        f"User asked about: \"{query}\"",
        f"If the user asked about a specific date (e.g. 'yesterday', 'May 11', '前天'), find that date in the data below.",
        f""
    ]
    for d in sorted(by_date.keys(), reverse=True):
        if d == str(today):
            day_label = f"Today ({d})"
        elif d == str(today - timedelta(days=1)):
            day_label = f"Yesterday ({d})"
        else:
            day_label = str(d)
        day_metrics = by_date[d]
        lines.append(f"\n## {day_label}")
        for metric_key in sorted(day_metrics.keys()):
            m = day_metrics[metric_key]
            label = metric_labels.get(metric_key, metric_key)
            dev_str = ""
            if m["deviation_sigma"] is not None and abs(m["deviation_sigma"]) >= 1.5:
                direction = "↑" if m["deviation_sigma"] > 0 else "↓"
                dev_str = f" | ⚠️偏离基线 {direction}{abs(m['deviation_sigma'])}σ"
            # 累积型指标展示 total；瞬时型展示 avg
            if metric_key in CUMULATIVE_METRICS:
                val_str = f"total={m['total']} (avg={m['avg']}, range {m['min']}~{m['max']})"
            else:
                val_str = f"avg={m['avg']} (range {m['min']}~{m['max']})"
            lines.append(
                f"- **{label}**: {val_str}, "
                f"baseline={m['baseline_mean']}, samples={m['samples']}{dev_str}"
            )

    summary_text = "\n".join(lines)
    total_metrics = sum(len(v) for v in by_date.values())

    llm = get_perception_llm()
    now = datetime.now()
    time_now = now.strftime("%H:%M")
    messages = [
        SystemMessage(content=PERCEPTION_SYSTEM + f"\n\nCurrent time: {time_now}, date: {today}. The day is not over yet — data shown is partial for today. The user may ask about a specific date — look for that date in the data below."),
        HumanMessage(content=f"User query: {query}\n\n---\n{summary_text}\n---\n\nAnalyze ALL {total_metrics} metrics. If the user asked about a specific date, focus on that date's data. Do not say 'I can only see today' — all 3 days of data are provided above. Note that today is still in progress."),
    ]
    narrative = llm.invoke(messages).content

    logger.info(f"Perception: {len(by_date)} days, {total_metrics} total metrics")

    return {"health_metrics": by_date, "personal_context": narrative}
