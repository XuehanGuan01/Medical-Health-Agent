# Phase 4 长期记忆 & 周报 & 趋势 — 实施方案

> 2026-05-10 | 依赖 Phase 1 ✅ + Phase 3 ✅ | 目标：3个API端点 + 多轮对话升级
> 可与 Phase 5（前端）并行开发

---

## 一、前置条件确认

| 依赖 | 状态 | 说明 |
|------|------|------|
| Phase 3 `/api/v1/chat` | ✅ 已验证 | 单轮对话正常，需扩展注入历史 |
| `AgentState.messages` | ✅ 已预留 | `add_messages` reducer，直接用 |
| Phase 1 `daily_metrics` | ✅ 真实数据 | 含 16 个聚合指标，支持日期范围查询 |
| `memory/` 目录 | ❌ 不存在 | 需创建 |
| Phase 3 `agents/graph.py` | ⚠️ 需微调 | chat() 增加 session_id 传参 |

---

## 二、架构概览

### 2.1 数据流

```
┌─────────────────────────────────────────────────────────┐
│                     Phase 4 数据流                        │
│                                                         │
│  用户 query ──→ chat(session_id)                        │
│       │                                                 │
│       ├─ ① 从 chat_history 读最近 5 轮                  │
│       ├─ ② 注入 AgentState.messages                     │
│       ├─ ③ Phase 3 Graph 执行（Router感知历史）           │
│       ├─ ④ 输出 response                               │
│       └─ ⑤ 自动写入 chat_history                        │
│                                                         │
│  周报生成:                                              │
│    daily_metrics(7天) → LLM叙事 → weekly_reports表      │
│                                                         │
│  趋势查询:                                              │
│    daily_metrics(N周) → 按周聚合 → 周均值对比            │
└─────────────────────────────────────────────────────────┘
```

### 2.2 新增文件清单

```
memory/
├── __init__.py
├── schema.py         — SQLite 表定义（chat_history, weekly_reports）
├── history.py        — 对话历史 CRUD
├── weekly.py         — 周报生成
├── trend.py          — 趋势查询
```

### 2.3 修改文件

| 文件 | 改动 |
|------|------|
| `agents/graph.py` | `chat()` 增加 `session_id` 参数，注入/保存对话历史 |
| `agents/state.py` | 无需改动（`messages` 已预留） |
| `agents/router.py` | 无需改动（LLM 看到历史自动感知上下文） |
| `data_pipeline/webhook_server.py` | 新增 4 个端点：`/chat` 多轮增强、`/memory/history`、`/report/weekly`、`/health/trend` |

---

## 三、逐文件详细设计

### 3.1 `memory/schema.py` — 数据表定义

```python
"""Phase 4 数据模型"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Float
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timezone


class Base(DeclarativeBase):
    pass


class ChatHistory(Base):
    """对话历史 — 每次 chat() 自动写入一行"""
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    role = Column(String(16), nullable=False)        # "user" | "assistant"
    content = Column(Text, nullable=False)
    intent = Column(String(32))                      # health_data | medical_qa | general_chat | emergency
    safety_level = Column(String(16))                # normal | caution | emergency
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class WeeklyReport(Base):
    """周报 — 每周一生成"""
    __tablename__ = "weekly_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    week_start = Column(Date, nullable=False, index=True)   # 周一日期
    week_end = Column(Date, nullable=False)                  # 周日日期
    narrative = Column(Text)                                 # LLM 叙事全文
    metrics_json = Column(Text)                              # 各项指标JSON（结构化数据）
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
```

**设计决策**：
- `ChatHistory` 放在 Phase 1 的 `data/health.db` 内（同一 SQLite 文件，省管理）。使用独立的 `Base` 类避免与 Phase 1 的 `models.Base` 冲突
- `WeeklyReport` 存 LLM 叙事 + JSON 结构化数据，方便前端图表渲染和历史查询

### 3.2 `memory/history.py` — 对话历史 CRUD

```python
"""对话历史持久化"""
from sqlalchemy.orm import Session
from memory.schema import ChatHistory


def save_turn(db: Session, session_id: str, role: str, content: str,
              intent: str = None, safety_level: str = "normal", retry_count: int = 0):
    """保存一轮对话"""
    record = ChatHistory(
        session_id=session_id,
        role=role,
        content=content,
        intent=intent,
        safety_level=safety_level,
        retry_count=retry_count,
    )
    db.add(record)
    db.commit()


def get_recent_history(db: Session, session_id: str, n: int = 5) -> list[dict]:
    """读取最近 N 轮对话（user+assistant 成对）"""
    records = (
        db.query(ChatHistory)
        .filter(ChatHistory.session_id == session_id)
        .order_by(ChatHistory.created_at.desc())
        .limit(n * 2)  # N轮 = N条 user + N条 assistant
        .all()
    )
    # 反转回时间正序
    records.reverse()
    return [
        {"role": r.role, "content": r.content, "intent": r.intent}
        for r in records
    ]


def list_sessions(db: Session, limit: int = 20) -> list[str]:
    """列出最近的 session_id"""
    from sqlalchemy import func, distinct
    sessions = (
        db.query(distinct(ChatHistory.session_id))
        .order_by(ChatHistory.session_id.desc())
        .limit(limit)
        .all()
    )
    return [s[0] for s in sessions]
```

### 3.3 `memory/weekly.py` — 周报生成

```python
"""周报生成 — 消费 Phase 1 聚合数据 + LLM 叙事"""
from datetime import date, timedelta
from sqlalchemy.orm import Session
from data_pipeline.models import DailyMetric
from memory.schema import WeeklyReport
from config.llm import get_action_llm    # 复用 action 的 LLM (temp=0.5)
import json


WEEKLY_SYSTEM = """你是私人健康周报撰写师。基于上周 7 天的健康监测数据生成周报。

输出格式：
1. 总览（一段话概括本周健康状态）
2. 核心指标周均值（心率/HRV/步数/能量/睡眠，每项一行）
3. 与上周对比（如有历史周报数据）
4. 下周建议（1-2条简短的改善建议）"""


def generate_weekly_report(db: Session, target_week_start: date = None) -> dict:
    """
    生成一周健康报告。

    参数:
        target_week_start: 周一日期，默认本周一
    返回:
        {"week_start": date, "week_end": date, "narrative": str, "metrics": dict}
    """
    if target_week_start is None:
        today = date.today()
        target_week_start = today - timedelta(days=today.weekday())  # 本周一

    week_end = target_week_start + timedelta(days=6)

    # 读取 7 天 DailyMetric
    metrics = (
        db.query(DailyMetric)
        .filter(
            DailyMetric.date >= target_week_start,
            DailyMetric.date <= week_end,
        )
        .all()
    )

    if not metrics:
        return {"error": f"No data for {target_week_start} ~ {week_end}"}

    # 按指标类型聚合
    from collections import defaultdict
    grouped = defaultdict(list)
    for m in metrics:
        grouped[m.metric_type].append(m)

    summary = {}
    for metric_type, rows in grouped.items():
        avgs = [r.avg_value for r in rows if r.avg_value is not None]
        totals = [r.total_value for r in rows if r.total_value is not None]
        summary[metric_type] = {
            "week_avg": round(sum(avgs) / len(avgs), 2) if avgs else None,
            "week_total": round(sum(totals), 2) if totals else None,
            "days_with_data": len(rows),
        }

    # LLM 叙事
    llm = get_action_llm()
    prompt = f"以下是 {target_week_start} ~ {week_end} 健康数据：\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n请生成周报。"
    narrative = llm.invoke(prompt).content

    # 持久化
    report = WeeklyReport(
        week_start=target_week_start,
        week_end=week_end,
        narrative=narrative,
        metrics_json=json.dumps(summary, ensure_ascii=False),
    )
    db.add(report)
    db.commit()

    return {
        "week_start": str(target_week_start),
        "week_end": str(week_end),
        "narrative": narrative,
        "metrics": summary,
    }


def get_weekly_report(db: Session, week_start: date) -> dict | None:
    """查询历史周报"""
    report = (
        db.query(WeeklyReport)
        .filter(WeeklyReport.week_start == week_start)
        .first()
    )
    if not report:
        return None
    return {
        "week_start": str(report.week_start),
        "week_end": str(report.week_end),
        "narrative": report.narrative,
        "metrics": json.loads(report.metrics_json) if report.metrics_json else {},
    }
```

### 3.4 `memory/trend.py` — 趋势查询

```python
"""健康趋势 — 多周对比"""
from datetime import date, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func
from data_pipeline.models import DailyMetric


def get_trend(db: Session, metric_type: str, weeks: int = 4) -> dict:
    """
    查询指标多周趋势。

    返回:
      {
        "metric": "heart_rate",
        "weeks": 4,
        "baseline_mean": 72.5,
        "weeks_data": [
          {"week_start": "2026-04-13", "avg": 71.2, "min": 52, "max": 138, "days": 7},
          ...
        ],
        "trend_direction": "stable" | "rising" | "falling"
      }
    """
    today = date.today()
    end_date = today
    start_date = today - timedelta(weeks=weeks * 7)

    rows = (
        db.query(
            DailyMetric.date,
            DailyMetric.avg_value,
            DailyMetric.min_value,
            DailyMetric.max_value,
            DailyMetric.sample_count,
        )
        .filter(
            DailyMetric.metric_type == metric_type,
            DailyMetric.date >= start_date,
            DailyMetric.date <= end_date,
            DailyMetric.avg_value.isnot(None),
        )
        .order_by(DailyMetric.date.asc())
        .all()
    )

    # 按周分组
    from datetime import datetime
    weeks_data = defaultdict(list)
    for r in rows:
        d = r.date if isinstance(r.date, date) else datetime.strptime(str(r.date), "%Y-%m-%d").date()
        monday = d - timedelta(days=d.weekday())
        weeks_data[monday].append(r)

    result_weeks = []
    week_avgs = []
    for monday in sorted(weeks_data.keys()):
        day_rows = weeks_data[monday]
        avgs = [r.avg_value for r in day_rows]
        mins = [r.min_value for r in day_rows if r.min_value is not None]
        maxs = [r.max_value for r in day_rows if r.max_value is not None]
        result_weeks.append({
            "week_start": str(monday),
            "avg": round(sum(avgs) / len(avgs), 2),
            "min": round(min(mins), 2) if mins else None,
            "max": round(max(maxs), 2) if maxs else None,
            "days": len(day_rows),
        })
        week_avgs.append(sum(avgs) / len(avgs))

    # 趋势方向
    if len(week_avgs) >= 2:
        slope = week_avgs[-1] - week_avgs[0]
        if slope > 2:
            direction = "rising"
        elif slope < -2:
            direction = "falling"
        else:
            direction = "stable"
    else:
        direction = "stable"

    return {
        "metric": metric_type,
        "weeks": weeks,
        "overall_mean": round(sum(week_avgs) / len(week_avgs), 2) if week_avgs else None,
        "weeks_data": result_weeks,
        "trend_direction": direction,
    }
```

---

## 四、`agents/graph.py` 升级 — 多轮对话注入

```python
# ── 修改 chat() 函数 ──

import uuid
from data_pipeline.database import SessionLocal
from memory.schema import Base as MemoryBase
from memory.history import save_turn, get_recent_history
from langchain_core.messages import HumanMessage, AIMessage


def chat(query: str, session_id: str = None) -> dict:
    """多轮对话入口"""
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]

    db = SessionLocal()
    try:
        # ① 读最近 5 轮历史
        history = get_recent_history(db, session_id, n=5)
        messages = []
        for h in history:
            if h["role"] == "user":
                messages.append(HumanMessage(content=h["content"]))
            else:
                messages.append(AIMessage(content=h["content"]))

        # ② 保存用户消息
        save_turn(db, session_id, "user", query)

        # ③ 硬边界短路
        is_emergency, emergency_msg = check_emergency(query)
        if is_emergency:
            save_turn(db, session_id, "assistant", emergency_msg,
                      intent="emergency", safety_level="emergency")
            db.close()
            return {
                "response": emergency_msg, "intent": "emergency",
                "route": "emergency", "source": "rule",
                "safety_level": "emergency", "retry_count": 0,
                "session_id": session_id,
            }

        # ④ 执行 Phase 3 Graph（注入历史）
        initial: AgentState = {
            "query": query,
            "messages": messages,       # ← 注入历史
            "intent": None,
            "route": None,
            "health_metrics": None,
            "personal_context": None,
            "retrieved_docs": None,
            "draft_response": None,
            "reflection": None,
            "retry_count": 0,
            "response": None,
            "source": None,
            "safety_level": "normal",
        }

        result = agent_graph.invoke(initial)

        # ⑤ 保存 assistant 回复
        save_turn(
            db, session_id, "assistant",
            result.get("response", ""),
            intent=result.get("intent"),
            safety_level=result.get("safety_level", "normal"),
            retry_count=result.get("retry_count", 0),
        )

        return {
            "response": result.get("response", ""),
            "intent": result.get("intent", ""),
            "route": result.get("route", ""),
            "source": result.get("source", ""),
            "safety_level": result.get("safety_level", "normal"),
            "retry_count": result.get("retry_count", 0),
            "session_id": session_id,
        }
    finally:
        db.close()
```

**设计决策**：
- `session_id` 自动生成（8位 UUID），前端可保存后在后续请求中传入
- 每次 `chat()` 自动写两行：user query + assistant response
- `chat_history` 表放在 Phase 1 的 `data/health.db` 内，需要 `init_db()` 建表时同时创建 Memory 表

---

## 五、FastAPI 端点集成

```python
# ── 在 webhook_server.py 中新增 ──

from memory.schema import Base as MemoryBase
from memory.weekly import generate_weekly_report, get_weekly_report
from memory.trend import get_trend
from memory.history import list_sessions, get_recent_history
from data_pipeline.database import engine, SessionLocal

# 建表扩展
MemoryBase.metadata.create_all(engine)   # 加入 startup 中执行


# ── 端点 ──

class ChatRequestV2(PydanticBaseModel):
    query: str
    session_id: str = None

@app.post("/api/v1/chat")
def chat_endpoint(req: ChatRequestV2):
    """多轮对话（Phase 4 升级），可选 session_id"""
    from agents.graph import chat as agent_chat
    return agent_chat(query=req.query, session_id=req.session_id)


@app.get("/api/v1/memory/history")
def get_chat_history(
    session_id: str = Query(...),
    n: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """查询某 session 的对话历史"""
    history = get_recent_history(db, session_id, n)
    return {"session_id": session_id, "turns": len(history), "history": history}


@app.get("/api/v1/memory/sessions")
def get_sessions(db: Session = Depends(get_db)):
    """列出最近 session"""
    return {"sessions": list_sessions(db)}


@app.post("/api/v1/report/weekly")
def create_weekly_report(
    week_start: str = None,
    db: Session = Depends(get_db),
):
    """生成周报（默认本周）"""
    from datetime import date
    ws = date.fromisoformat(week_start) if week_start else None
    return generate_weekly_report(db, ws)


@app.get("/api/v1/report/weekly")
def query_weekly_report(
    week_start: str = Query(...),
    db: Session = Depends(get_db),
):
    """查询历史周报"""
    from datetime import date
    ws = date.fromisoformat(week_start)
    result = get_weekly_report(db, ws)
    if not result:
        raise HTTPException(status_code=404, detail="周报不存在，请先生成")
    return result


@app.get("/api/v1/health/trend")
def get_health_trend(
    metric: str = Query(..., description="指标名"),
    weeks: int = Query(4, ge=2, le=52),
    db: Session = Depends(get_db),
):
    """健康指标多周趋势"""
    return get_trend(db, metric, weeks)
```

---

## 六、测试验证计划

### 6.1 多轮对话

```powershell
# 启动
python -m data_pipeline.webhook_server

# 第一轮
Invoke-RestMethod -Uri http://localhost:8000/api/v1/chat -Method Post -ContentType "application/json" -Body '{"query":"我今天心率怎么样？"}' | ConvertTo-Json

# 记录 session_id，第二轮在同 session 中追问
Invoke-RestMethod -Uri http://localhost:8000/api/v1/chat -Method Post -ContentType "application/json" -Body '{"query":"那跟昨天比呢？","session_id":"<上轮的session_id>"}' | ConvertTo-Json
```

**预期**：第二轮 LLM 应理解"昨天"指的是前一天心率数据（从历史中获取上下文）。

### 6.2 周报

```powershell
# 生成本周周报
Invoke-RestMethod -Uri http://localhost:8000/api/v1/report/weekly -Method Post

# 查询
Invoke-RestMethod "http://localhost:8000/api/v1/report/weekly?week_start=2026-05-04"
```

### 6.3 趋势

```powershell
# 心率 4 周趋势
Invoke-RestMethod "http://localhost:8000/api/v1/health/trend?metric=heart_rate&weeks=4" | ConvertTo-Json -Depth 5
```

**预期**：`trend_direction` 为 stable/rising/falling，`weeks_data` 含每周均值。

---

## 七、待确认问题 & 模糊点

### Q1 — ChatHistory 表放在 health.db 还是独立文件？
当前设计放在 `data/health.db`（与 Phase 1 共享）。好处是省管理，坏处是耦合。备选：`data/memory.db` 独立文件。

### Q2 — session_id 由谁生成？
当前设计：前端首次不传→后端自动生成 8 位 UUID 返回→前端保存后续传入。如果前端自己做 session 管理（LocalStorage），也可以前端生成。**需确认哪种方式**。

### Q3 — 多轮对话的 token 消耗
每轮对话注入最近 5 轮历史（~500 tokens/轮），约 2500 tokens 额外输入。加上 Self-RAG，单次多轮可能消耗 5000-7000 tokens。Qwen3-Max 免费额度是否有限制？

### Q4 — 周报对 LLM 的依赖
周报生成调用 LLM 叙事，如果 Qwen API 不可用，周报功能直接不可用。是否需要降级方案（纯数据表格，不生成叙事）？

### Q5 — 趋势查询的性能
4 周 × 7 天 × 16 个指标 = 448 行查询，量不大。但如果扩展到 52 周且频繁调用，是否需要缓存？

### Q6 — chat_history 表无限增长
无自动清理机制。一年后可能数万行。是否需要：①按时间归档 ②`list_sessions` 只展示最近 N 个 session ③前端提供清除按钮？

### Q7 — 周报是否支持自定义日期范围？
当前仅支持按自然周（周一~周日）。如需"最近 7 天"任意窗口，需要改动 `generate_weekly_report` 参数。

### Q8 — 多轮对话对 Router 的影响
如果历史上下文包含 "心率"、"睡眠" 等词，Router 的 LLM 可能将追问（如"那怎么样？"）误分类为 health_data。**建议**：Router 只读当前 query，不读历史。

### Q9 — ChromaDB 语义记忆是否需要？
当前 Phase 4 仅用 SQLite 做对话历史。如果后续需要"根据以往的对话内容理解用户偏好"（如用户提过"我睡眠不好"则后续回答中自动考虑），需要 ChromaDB 做语义检索。**首版建议**：SQLite 足够，语义记忆 Phase 4 可跳过。

### Q10 — 周报与 push 通知的关联
周报生成后是否需要主动通知用户（微信模板消息/邮件）？Phase 5 小程序端是否需要周报 push 触达？

---

## 八、开发排期

| Step   | 内容                                           | 预估       |
| ------ | -------------------------------------------- | -------- |
| Step 1 | `memory/schema.py` + 建表集成到 init_db           | 0.5天     |
| Step 2 | `memory/history.py` + `graph.py` chat() 升级多轮 | 0.5天     |
| Step 3 | `memory/weekly.py` + `/api/v1/report/weekly` | 0.5天     |
| Step 4 | `memory/trend.py` + `/api/v1/health/trend`   | 0.5天     |
| Step 5 | 测试手册 + 端到端验证                                 | 0.5天     |
| **合计** |                                              | **2.5天** |
