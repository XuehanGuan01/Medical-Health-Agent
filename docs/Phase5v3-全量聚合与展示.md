# Phase 5 v3 — 全量指标聚合与展示

> 2026-05-13 | 发现 39 种 iOS 指标仅聚合了 16 种 → 补全全部 39 种

---

## 一、问题

iOS 同步了 **39 种** 健康指标到 raw 表，但 `config.py` 的 `AGGREGATION_METRICS` 只有 16 种，导致 Dashboard 和 Perception 分析缺失 23 种指标。

### 缺失的 23 种

```
environmental_audio_exposure     17,243  环境噪音暴露
time_in_daylight                 13,792  日照时长
headphone_audio_exposure          9,162  耳机噪音暴露
apple_stand_hour                  4,341  站立小时
stair_speed_down                  2,310  下楼梯速度
mindful_minutes                   1,710  正念分钟
stair_speed_up                    1,496  上楼梯速度
walking_heart_rate_average          384  步行平均心率
sleep_analysis                      378  睡眠分析
running_power                       336  跑步功率
running_speed                       318  跑步速度
cycling_distance                    301  骑行距离
running_ground_contact_time         259  跑步触地时间
running_vertical_oscillation        259  跑步垂直摆动
running_stride_length               251  跑步步幅
handwashing                         175  洗手
vo2_max                              85  最大摄氧量
six_minute_walking_test_distance     58  六分钟步行测试
cardio_recovery                      53  心率恢复
weight_body_mass                      2  体重
body_fat_percentage                   1  体脂率
body_mass_index                       1  BMI
height                                1  身高
```

---

## 二、修复

### 2.1 `data_pipeline/config.py` — 补全全部 39 种指标

```
原: AGGREGATION_METRICS = 16 种
改: AGGREGATION_METRICS = 39 种（全部 raw 中存在的指标）
```

### 2.2 全量重新聚合

修改 config 后必须全量重算：

```powershell
python -c "
from data_pipeline.database import SessionLocal; from data_pipeline.aggregator import aggregate_daily_metrics
from data_pipeline.models import RawHealthSample; from sqlalchemy import func; from datetime import date
db = SessionLocal()
days = db.query(func.date(RawHealthSample.start_time).label('day')).group_by('day').order_by('day').all()
print(f'{len(days)} 天全量重算中...')
for (day,) in days:
    target = date.fromisoformat(str(day))
    aggregate_daily_metrics(db, target)
db.close()
print('Done')
"
```

### 2.3 `agents/perception.py` — 指标标签补全

新增 23 种指标的中文标签映射。

---

## 三、验证

```powershell
# 聚合后查 daily 指标数（应 ≈ 39）
Invoke-RestMethod "http://localhost:8000/api/v1/health/daily?date=2026-05-12" | ConvertTo-Json -Depth 3
```
