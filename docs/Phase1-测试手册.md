# Phase 1 测试手册

> 目标：验证 Apple Health 数据从 iPhone → ngrok → FastAPI → SQLite 的完整通路。

---

## 环境确认

```bash
cd Medical-Health-Agent
python -c "from data_pipeline.config import *; print('OK')"
```

## 一、本地模拟测试（无 iPhone，先验证后端）

### Step 1 — 启动 FastAPI

在 **PyCharm 终端** 中：

```powershell
python -m data_pipeline.webhook_server
```

看到以下输出表示成功：

```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

![[Pasted image 20260509161317.png]]
### Step 2 — 验证服务

另开一个终端：

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health/status | ConvertTo-Json -Depth 5
```

预期返回：`"total_raw_samples": 0`（空库）
![[Pasted image 20260509161526.png]]

那是我之前测试时写入的模拟数据。删掉数据库文件重新启动即可清空：

```powershell
# 停掉 FastAPI (Ctrl+C)，然后：
Remove-Item C:\Users\Lenovo\Desktop\Medical-Health-Agent\data\health.db

# 重新启动，init_db() 会自动创建空库
python -m data_pipeline.webhook_server

# 再查一次 /status 就是 total_raw_samples: 0 了。
```
![[Pasted image 20260509161817.png]]
### Step 3 — 发送模拟数据

```bash
python -c "import requests, subprocess, json;data=subprocess.run(['python','-m','data_pipeline.test_data'],capture_output=True).stdout;r=requests.post('http://localhost:8000/api/v1/health/sync', data=data,headers={'Content-Type':'application/json','Authorization':'Bearer medical-health-agent-dev-key-2026'}); print(json.dumps(r.json(), indent=2,ensure_ascii=False))"
```

预期返回：

```json
{
    "status": "success",
    "metrics_received": 10,
    "data_points_inserted": ~350,
    "workouts_received": 1
}
```
![[Pasted image 20260509163120.png]]
### Step 4 — 验证数据已入库

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health/status | ConvertTo-Json -Depth 5
```

`total_raw_samples` 应 >0。
![[Pasted image 20260509163730.png]]
### Step 5 — 验证聚合

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/health/daily?date=2026-05-09" | ConvertTo-Json -Depth 5
```

应返回各指标的 avg/min/max/stddev/sample_count。
![[Pasted image 20260509163740.png]]
### Step 6 — 验证基线

```powershell
python -c "import requests; r=requests.get('http://localhost:8000/api/v1/health/baseline', params={'metric_type':'heart_rate','days':7}); print(r.text)"
```

首次运行因数据不足 3 天，会返回 `"error": "Insufficient data"`（正常）。

### Step 7 — 清理数据库（如需重新测试）

```powershell
# Ctrl+C 停 FastAPI
Remove-Item C:\Users\Lenovo\Desktop\Medical-Health-Agent\data\health.db
python -m data_pipeline.webhook_server
```

---

## 二、ngrok 穿透 + iPhone 真机测试

### Step 1 — 启动 ngrok

确保 FastAPI 在 8000 端口运行中，然后**另开终端**：

```powershell
python -m data_pipeline.webhook_server
```
```bash
ngrok http 8000
```

输出：

```
Forwarding  https://xxxx-xxx.ngrok-free.app → http://localhost:8000
```

### Step 2 — 获取 ngrok 公网 URL

```powershell
Invoke-RestMethod http://localhost:4040/api/tunnels | ForEach-Object tunnels | Where-Object public_url -like "https://*" | Select-Object -ExpandProperty public_url
```

记下输出的 URL（如 `https://abc123.ngrok-free.app`）。

### Step 3 — 在浏览器快速验证 ngrok 通路

在 iPhone Safari 中打开：

```
https://<你的ngrok-url>/api/v1/health/status
```

应能看到 JSON 响应（证明 ngrok 通路正常）。
![[29b216308e794ba9d53e82db9b0d346c.png|282]]

### Step 4 — 配置 iPhone Health Auto Export

1. 打开 Health Auto Export App
2. **Automations** → 右上角 **+** → **API Export**
3. 填入配置：

| 配置项       | 值                                          |
| --------- | ------------------------------------------ |
| URL       | `https://<你的ngrok-url>/api/v1/health/sync` |
| Format    | **JSON**                                   |
| Period    | **Last Sync**（增量同步）                        |
| Interval  | **Minutes** / **30 Minutes**               |
| Data Type | **Health Metrics + Workouts**              |
| 导出版本      | **Version 2**                              |
| 日期范围      | **自上次同步**                                  |
| 汇总数据      | 关闭（获取原始数据点）                                |

4. **Custom Headers** 添加：

```
Authorization: Bearer medical-health-agent-dev-key-2026
```

5. 开关设为 **Enabled**

### Step 5 — 手动触发首次同步

在 Automation 列表中，点 **▶️ 按钮** 手动执行一次。

### Step 6 — 验证 iPhone 数据已到达

在 PC 终端：

```powershell
python -c "import requests; r=requests.get('http://localhost:8000/api/v1/health/status'); print(r.text)"
```

`total_raw_samples` 应增加。查看 `metric_types_top20` 确认数据种类。

```powershell
# 查看具体指标数据
python -c "import requests; r=requests.get('http://localhost:8000/api/v1/health/raw', params={'metric_type':'heart_rate','date_from':'2026-05-09'}); print(r.text)"
```
![[Pasted image 20260509175153.png]]
---
![[ebf087e59e643393f04dec56288f3ef5.jpg|266]]
## 三、常规操作流程（每次使用）

```
1. PC → 终端1: python -m data_pipeline.webhook_server
2. PC → 终端2: ngrok http 8000
3. PC → 复制 ngrok 输出的 URL
4. iPhone → Health Auto Export → Automation → 粘贴 URL（如URL已变）
5. iPhone → 点 ▶️ 手动触发同步
6. PC → python -c "import requests;..."  /status 确认数据到达
```

> **ngrok 重启后 URL 会变**，需要更新步骤 3。ngrok 持续运行期间 URL 不变。

---

## 四、真机数据验证 & 聚合

### 4.1 检查数据覆盖天数

```powershell
python -c "from data_pipeline.database import SessionLocal; from data_pipeline.models import RawHealthSample; from sqlalchemy import func; db = SessionLocal(); result = db.query(func.min(RawHealthSample.start_time), func.max(RawHealthSample.start_time)).first(); daily = db.query(func.date(RawHealthSample.start_time).label('day'), func.count(RawHealthSample.id)).group_by('day').order_by('day').all(); db.close(); print(f'日期范围: {result[0]} -> {result[1]}'); print(f'覆盖天数: {len(daily)} 天\n'); [print(f'  {d}: {c} 条') for d, c in daily]"
```

### 4.2 指标名称对齐（⚠️ 关键）

**真机 Apple Health 数据中的指标名称可能与配置不一致**。例如：

| 配置中名称 | 真机实际名称 |
|-----------|-------------|
| `exercise_time` | `apple_exercise_time` |

同步后立即检查 `/status` 的 `metric_types_top20`，如有新指标但未被聚合，将实际名称加入 `config.py` 的 `AGGREGATION_METRICS` 列表。

### 4.3 手动触发聚合

已入库的历史数据需要手动触发一次聚合：

```powershell
python -c "from data_pipeline.database import SessionLocal; from data_pipeline.aggregator import aggregate_daily_metrics; from datetime import date; db = SessionLocal(); aggregate_daily_metrics(db, date.today()); print('聚合完成'); db.close()"
```

验证聚合结果：

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/health/daily?date=2025-10-09" | ConvertTo-Json -Depth 5
```

### 4.4 上传历史数据

Health Auto Export 默认"自上次同步"只发增量。要回填历史：

1. 打开 Health Auto Export → Automation → 手动导出
2. 日期范围选大窗口（如"过去 7 天"先测试，再逐步扩大到月、年）
3. 一年的全量数据量很大，建议分批上传避免超时
4. 上传前可清空数据库（见 Step 7）避免新旧数据混杂

---

## 五、聚合维护

### 5.1 自动聚合

每次 iPhone POST `/sync` 时，服务端自动对**当天**数据触发一次聚合。日常增量同步无需手动操作。

### 5.2 增量聚合（推荐，只补漏掉的天）

仅对有原始数据但缺少日聚合的日期进行聚合，避免全量重算：

```powershell
python -c "
from data_pipeline.database import SessionLocal
from data_pipeline.aggregator import aggregate_daily_metrics
from data_pipeline.models import RawHealthSample, DailyMetric
from sqlalchemy import func, distinct
from datetime import date

db = SessionLocal()

# 有原始数据的日期
raw_days = set(r[0] for r in db.query(
    func.date(RawHealthSample.start_time)
).distinct().all())

# 已有聚合的日期
agg_days = set(r[0] for r in db.query(
    distinct(DailyMetric.date)
).all())

# 差集 = 需要补聚合的日期
missing = sorted(raw_days - agg_days)

if missing:
    print(f'需补聚合: {len(missing)} 天')
    for day in missing:
        target = date.fromisoformat(str(day))
        aggregate_daily_metrics(db, target)
        print(f'  {day} ✅')
else:
    print('所有日期已聚合，无需操作')

db.close()
"
```

### 5.3 全量重新聚合（仅在修改 config 后使用）

```powershell
python -c "
from data_pipeline.database import SessionLocal
from data_pipeline.aggregator import aggregate_daily_metrics
from data_pipeline.models import RawHealthSample
from sqlalchemy import func
from datetime import date

db = SessionLocal()
days = db.query(
    func.date(RawHealthSample.start_time).label('day')
).group_by('day').order_by('day').all()

print(f'共 {len(days)} 天需重算')
for (day,) in days:
    target = date.fromisoformat(str(day))
    aggregate_daily_metrics(db, target)
    print(f'  {day} ✅')
db.close()
print('全量重算完成')
"
```

### 5.4 验证聚合覆盖率

```powershell
python -c "
from data_pipeline.database import SessionLocal
from data_pipeline.models import DailyMetric
from sqlalchemy import func
db = SessionLocal()
total = db.query(func.count(DailyMetric.id)).scalar()
days = db.query(func.date(DailyMetric.date).label('day'), func.count(DailyMetric.id)).group_by('day').order_by(func.date(DailyMetric.date).desc()).limit(14).all()
db.close()
print(f'聚合总行数: {total}')
print('最近 14 天:')
for d, c in days:
    print(f'  {d}: {c} 个指标')
"
```

### 5.5 日常维护清单

| 频率             | 操作                 | 命令                                                                                                |
| -------------- | ------------------ | ------------------------------------------------------------------------------------------------- |
| 每次启动           | 启动 FastAPI + ngrok | `python -m data_pipeline.webhook_server` + `ngrok http 8000`                                      |
| 每次 iPhone 同步后  | 自动聚合当天             | 无需操作                                                                                              |
| 修改 config.py 后 | 重启 + 重跑全量聚合        | 见 5.2                                                                                             |
| 每周             | 查数据覆盖 `baseline`   | `Invoke-RestMethod "http://localhost:8000/api/v1/health/baseline?metric_type=heart_rate&days=30"` |
| 每周             | 备份数据库              | `copy data\health.db data\backup\health_$(Get-Date -Format yyyyMMdd).db`                          |

### 5.6 数据库备份

```powershell
# 创建备份目录
New-Item -ItemType Directory -Force -Path data\backup

# 备份（替换日期）
copy data\health.db data\backup\health_2026-05-09.db
```

---

## 六、API 速查

| 端点 | 用途 |
|------|------|
| `GET /api/v1/health/status` | 数据库概览、最近同步状态 |
| `GET /api/v1/health/daily?date=YYYY-MM-DD` | 某天聚合数据 |
| `GET /api/v1/health/daily?date=YYYY-MM-DD&metric=heart_rate` | 某天单指标 |
| `GET /api/v1/health/raw?metric_type=heart_rate&date_from=YYYY-MM-DD` | 原始数据点 |
| `GET /api/v1/health/raw?metric_type=sleep_analysis&date_from=YYYY-MM-DD&limit=10` | 睡眠原始数据 |
| `GET /api/v1/health/baseline?metric_type=heart_rate&days=30` | 30 天基线 |

---

## 七、常见问题

| 现象 | 排查 |
|------|------|
| `401` Unauthorized | Authorization header 没配或 API Key 不对 |
| `403` Forbidden | API Key 值不匹配（检查 `config.py` 的 `API_KEY`） |
| `400 Bad Request` | JSON 格式不匹配，看服务端终端日志中的实际 payload |
| `405 Method Not Allowed` on `GET /sync` | `/sync` 是 POST 端点，浏览器直接打开是 GET 请求 |
| `ImportError: attempted relative import` | 要用 `python -m data_pipeline.webhook_server`，不要 `cd data_pipeline && python webhook_server.py` |
| 端口 8000 被占用 | `python -c "import subprocess,os;out=subprocess.check_output('netstat -ano \| findstr :8000',shell=True).decode();lines=[l for l in out.split('\n') if 'LISTENING' in l];pids=list(set(l.split()[-1] for l in lines));[os.system(f'taskkill /F /PID {p}') for p in pids]"` |
| 聚合指标少 | 真机数据指标名可能与 `config.py` 不匹配，检查 `/status` 的 `metric_types_top20` 后更新 `AGGREGATION_METRICS` |
| ngrok URL 访问不通 | 浏览器打开 `http://localhost:4040` 查看 ngrok 状态 |
| iPhone 同步失败 | 1) iPhone Safari 中打开 ngrok URL 测试 2) 检查 App 活动日志 |
| iPhone 锁屏时不同步 | iOS 限制——Health Auto Export 在 iPhone 解锁状态下才能访问 HealthKit |
