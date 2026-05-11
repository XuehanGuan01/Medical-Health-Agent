# Phase 4 测试手册

> 验收：多轮对话记忆、周报生成、趋势查询、session 管理

---

## 一、环境确认

```powershell
cd C:\Users\Lenovo\Desktop\Medical-Health-Agent

# 启动（会自动建 memory.db）
python -m data_pipeline.webhook_server
```

---

## 二、多轮对话记忆

### 2.1 基础多轮

```powershell
# 第一轮（记录返回的 session_id）
python -c "
import requests, json
r = requests.post('http://localhost:8000/api/v1/chat', json={'query':'我今天心率怎么样？'})
resp = r.json()
print('session_id:', resp['session_id'])
print('response:', resp['response'][:100])
"

# 用同一个 session_id 追问
python -c "
import requests, json
sid = '<上一步的session_id>'
r = requests.post('http://localhost:8000/api/v1/chat', json={'query':'那跟昨天比呢？', 'session_id': sid})
resp = r.json()
print('intent:', resp['intent'])
print('response:', resp['response'][:100])
"
```

**预期**：第二轮应在上下文中理解"昨天"指前一天的 health_data。

### 2.2 查看历史

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/memory/history?session_id=<sid>" | ConvertTo-Json -Depth 3
```

**预期**：返回 user+assistant 成对记录。

### 2.3 Session 列表

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/memory/sessions" | ConvertTo-Json -Depth 3
```

**预期**：含 `session_id`, `last_active`, `first_query`, `turns`。

### 2.4 清除 Session

```powershell
Invoke-RestMethod -Method Delete "http://localhost:8000/api/v1/memory/sessions/<sid>"
```

---

## 三、周报

### 3.1 生成周报

```powershell
python -c "
import requests, json
r = requests.post('http://localhost:8000/api/v1/report/weekly', json={})
print(json.dumps(r.json(), indent=2, ensure_ascii=False)[:500])
"
```

**预期**：含 `week_start`, `week_end`, `narrative`, `metrics`。

### 3.2 查询历史周报

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/report/weekly?week_start=2026-05-04" | ConvertTo-Json -Depth 3
```

### 3.3 周报列表

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/report/weekly/list" | ConvertTo-Json -Depth 3
```

---

## 四、趋势查询

```powershell
# 心率 4 周趋势
Invoke-RestMethod "http://localhost:8000/api/v1/health/trend?metric=heart_rate&weeks=4" | ConvertTo-Json -Depth 5

# 步数 8 周趋势
Invoke-RestMethod "http://localhost:8000/api/v1/health/trend?metric=step_count&weeks=8" | ConvertTo-Json -Depth 5
```

**预期**：含 `trend_direction`（stable/rising/falling）、`change_pct`、`weeks_data` 周均值数组。

---

## 五、完整验收清单

| # | 测试项 | 方法 | 预期 |
|---|--------|------|------|
| 1 | 单轮 chat | POST `/chat` 无 session_id | 返回新 session_id |
| 2 | 多轮追问 | 同 session_id 再 POST | 上下文连贯 |
| 3 | history 查询 | GET `/memory/history` | 含 user+assistant 成对 |
| 4 | session 列表 | GET `/memory/sessions` | 显示 last_active + turns |
| 5 | 清除 session | DELETE `/memory/sessions/{id}` | 返回 deleted count |
| 6 | 周报生成 | POST `/report/weekly` | narrative 含指标分析 |
| 7 | 周报查询 | GET `/report/weekly?week_start=...` | 返回持久化周报 |
| 8 | 趋势查询 | GET `/health/trend?metric=heart_rate` | 含 direction + change_pct |
| 9 | 紧急短路 | POST `/chat` 含 "胸痛" | safety_level=emergency |

---

## 六、数据库文件

```
data/
├── health.db    ← Phase 1 (raw_health_samples, daily_metrics, sync_log)
└── memory.db    ← Phase 4 (chat_history, weekly_reports)
```
