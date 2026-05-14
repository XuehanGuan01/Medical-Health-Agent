# Phase 5 v4 — 数据聚合修正方案

> 2026-05-14 | 目标：修正聚合逻辑中"重叠记录被错误求和"的问题，产出正确的 daily_metrics
> 此文档写给另一个 LLM Agent 执行

---

## 一、问题诊断

### 1.1 睡眠数据被错误求和

Health Auto Export 以**非聚合模式**发送睡眠数据时，同一晚会发送多条记录——每条都代表该夜的完整睡眠视图（含 `totalSleep`、`core`、`deep`、`rem`），但它们**时段重叠**：

```
2026-05-13  raw_health_samples 中 sleep_analysis:
  id=1  value=438min  totalSleep=7.30h  start=03:19  end=10:48  (core 4.7h + deep 1.0h + rem 1.6h)
  id=2  value=191min  totalSleep=3.18h  start=07:30  end=10:48  (core 2.1h + rem 1.1h)
  id=3  value=147min  totalSleep=2.45h  start=08:14  end=10:48  (core 2.1h + rem 0.4h)
```

三条都是同一晚的**完整睡眠摘要**（每条都含 totalSleep + 各阶段分布），只是覆盖的时段长短不同。当前代码把三个 `value` 求和：`438 + 191 + 147 = 776min = 12.9h`——这是错的，因为它们**不是独立的三次睡眠**，而是同一晚的三个重叠视角。

### 1.2 受到同样影响的指标

经过检查 39 种指标的 raw 数据，以下指标**不受影响**（每天只有 1 条或者多条之间不重叠）：
- 心率/HRV/静息心率：每条是独立采样窗口，不重叠，avg 有意义
- 步数/能量/运动/站立：累积型，求和(total)正确
- 步行指标/呼吸/环境噪音/日照：瞬时测量，avg 有意义

**唯一受影响的**是 `sleep_analysis`：同一晚多条重叠记录被错误求和。

---

## 二、修正方案

### 2.1 思路

**不在 raw 表层面去重**（保留所有原始数据），而是在**聚合层**区分两种语义：

| 指标类型 | 示例 | 语义 | 聚合方式 |
|---------|------|------|---------|
| 瞬时/采样型 | heart_rate, hrv, walking_speed, ... | 多条记录是独立采样 | avg = mean(values), total = sum(values) |
| 累积型 | step_count, active_energy, ... | 多条记录是分段累计 | avg = mean(values) 或无意义, total = sum(values) |
| **重叠摘要型** | sleep_analysis | 多条记录是同一事件的多个视角 | avg = max(values), total = max(values) (不是 sum) |

### 2.2 代码修改

**文件**: `data_pipeline/aggregator.py`

在 `_aggregate_one_metric` 函数中（约第 50 行），对 `sleep_analysis` 特殊处理：

```python
# 第 50 行附近，计算完 values 后：

OVELAP_METRICS = {"sleep_analysis"}   # 重叠摘要型指标：用 max 代替 sum/mean

values = np.array([s.value for s in samples], dtype=np.float64)
unit = samples[0].unit

db.query(DailyMetric).filter(
    DailyMetric.date == target_date,
    DailyMetric.metric_type == metric_type,
).delete()

is_overlap = metric_type in OVELAP_METRICS

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
```

**解释为什么 MAX 对睡眠是对的**：
- 每个 sleep_analysis 条目都是一个**完整**睡眠视图（含 totalSleep + core + deep + rem）
- 多条之间重叠（同一晚），不是独立的睡眠
- 取 MAX(value) = 最完整那条的 totalSleep = 当晚的真实总睡眠
- 每个条目的 `extra` JSON 中已经含有了 `totalSleep`、`core`、`deep`、`rem`，这些被保留在 raw 表中供查

### 2.3 Dashboard 显示

**文件**: `frontend/src/pages/dashboard/index.vue`

睡眠卡片的 `displayValue` 函数中，用 `total_value / 60` 显示为小时：

```javascript
if (m.metric_type === 'sleep_analysis' && m.total_value != null) {
    return (m.total_value / 60).toFixed(1) + 'h'
}
```

（这一步在 Phase 5 v4 中已完成，无需再改。）

### 2.4 趋势 API

**文件**: `memory/trend.py`

`get_trend()` 中，`sleep_analysis` 已在 §六 累积型指标列表中（使用 `total_value`）。Max 修正后，`total_value` 就是 MAX，趋势图也会显示正确值。

---

## 三、执行步骤

### Step 1 — 修改 `aggregator.py`

按 §2.2 添加 `OVERLAP_METRICS` 集合和 `is_overlap` 判断逻辑。

### Step 2 — 重跑睡眠聚合

```python
from data_pipeline.database import SessionLocal
from data_pipeline.aggregator import _aggregate_one_metric
from data_pipeline.models import DailyMetric, RawHealthSample
from sqlalchemy import func
from datetime import date, datetime, timezone, timedelta

db = SessionLocal()

# 删除所有旧的 sleep_analysis 聚合行
db.query(DailyMetric).filter(
    DailyMetric.metric_type == 'sleep_analysis'
).delete()
db.commit()

# 获取 raw 中有 sleep 数据的所有日期
raw_days = (
    db.query(func.date(RawHealthSample.start_time))
    .filter(RawHealthSample.metric_type == 'sleep_analysis')
    .distinct().all()
)

# 逐天重新聚合（此时 aggregator.py 已包含 OVELAP_METRICS 逻辑）
for (day_str,) in raw_days:
    d = date.fromisoformat(str(day_str))
    day_start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    _aggregate_one_metric(db, 'sleep_analysis', d, day_start, day_end)
db.commit()

# 验证
samples = (
    db.query(DailyMetric)
    .filter(DailyMetric.metric_type == 'sleep_analysis')
    .order_by(DailyMetric.date.desc()).limit(5).all()
)
for s in samples:
    print(f'{s.date}: total={s.total_value:.0f}min = {s.total_value/60:.1f}h  samples={s.sample_count}')
db.close()
```

### Step 3 — 验证 Dashboard

重启后端 + 前端，查看 Dashboard 睡眠卡片：
- 单条目天：`total_value / 60` = 实际睡眠时长
- 多条重叠天：`total_value` = 最完整那条的时长，不再虚高

### Step 4 — 确认其他指标不受影响

```python
from data_pipeline.database import SessionLocal
from data_pipeline.models import RawHealthSample
from sqlalchemy import func

db = SessionLocal()
# 检查每种指标每天的条目数分布（>1 表示同一天有多条）
rows = (
    db.query(
        RawHealthSample.metric_type,
        func.date(RawHealthSample.start_time),
        func.count(RawHealthSample.id)
    )
    .group_by(RawHealthSample.metric_type, func.date(RawHealthSample.start_time))
    .having(func.count(RawHealthSample.id) > 3)
    .order_by(func.count(RawHealthSample.id).desc())
    .limit(20).all()
)
for metric, day, cnt in rows:
    print(f'{metric} on {day}: {cnt} entries')
db.close()
```

预期：除 `sleep_analysis` 外，其他指标每天 ≤ 2-3 条（正常采样频率），不存在重叠问题。

---

## 四、关于 5.88h ≠ 8h28m 的说明

如果单条目天的 `totalSleep` 仍然偏小（如 5/14: 5.9h vs 用户感觉 8.5h），那是 **Health Auto Export 上报的数据本身偏小**，不是聚合逻辑的问题。可能原因：

- Apple Watch 睡眠追踪只捕获了部分时段
- 睡眠跨越午夜被拆到两天
- Health Auto Export 的时间窗口设置问题

这些需要从 iPhone 端配置解决，后端代码无法修补缺失的数据。
