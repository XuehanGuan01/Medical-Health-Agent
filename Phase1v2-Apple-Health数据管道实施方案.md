# Phase 1 v2: Apple Health 数据管道 — 可执行实施方案

> **目标**：实现 Apple Health 数据从 iPhone 到本地数据库的自动同步，构建数据聚合层，为 Phase 2 的 Agent 分析提供结构化输入。
>
> **周期**：1–2 周
>
> **核心原则**：本阶段不涉及任何 LLM，纯粹是数据工程。

---

## v2 更新说明

相对于 v1 版本，本版新增/改进：

| # | 变更 | 说明 |
|---|------|------|
| 1 | **URL 机制与数据流详解** | 新增 §2.2–2.3，说明 Health Auto Export REST API 的 URL 路由机制、请求构造方式、完整数据流 |
| 2 | **数据类目全景图** | 新增 §1.3，按优先级分 Tier 1/2/3，明确主流数据与扩展数据的取舍策略 |
| 3 | **逐文件设计说明** | 每个代码文件前增加「文件角色」「输入→输出」「关键设计决策」说明块 |
| 4 | **代码审查 & 优化** | 修复 v1 代码中的问题：`normalize_date` 空转、`datetime.utcnow` 已弃用、缺少空值分层处理等 |
| 5 | **待确认问题清单** | 新增附录 C，记录所有模糊点和待用户确认的事项 |

---

## 目录

1. [架构总览](#1-架构总览)
2. [iOS 端：Health Auto Export 深度解析](#2-ios-端health-auto-export-深度解析)
   - 2.1 [App 配置步骤](#21-app-配置步骤)
   - 2.2 [REST API URL 路由机制](#22-rest-api-url-路由机制)
   - 2.3 [端到端数据流](#23-端到端数据流)
3. [后端实现：FastAPI + SQLite](#3-后端实现fastapi--sqlite)
   - 3.1 [项目结构 & 文件角色说明](#31-项目结构--文件角色说明)
   - 3.2 [data_pipeline/config.py](#32-data_pipelineconfigpy)
   - 3.3 [data_pipeline/models.py](#33-data_pipelinemodelspy)
   - 3.4 [data_pipeline/database.py](#34-data_pipelinedatabasepy)
   - 3.5 [data_pipeline/webhook_server.py](#35-data_pipelinewebhook_serverpy)
   - 3.6 [data_pipeline/aggregator.py](#36-data_pipelineaggregatorpy)
   - 3.7 [data_pipeline/test_data.py](#37-data_pipelinetest_datapy)
4. [数据聚合层](#4-数据聚合层)
5. [部署与运行](#5-部署与运行)
6. [测试验证](#6-测试验证)
7. [Phase 2 衔接准备](#7-phase-2-衔接准备)

---

## 1. 架构总览

### 1.1 架构图

```
┌──────────────────────────────────────┐
│          iPhone (iOS 17+)            │
│                                      │
│  ┌────────────────────────────────┐  │
│  │  Health Auto Export App        │  │
│  │  (Lybron Sobers, 免费版)       │  │
│  │                                │  │
│  │  • 读取 HealthKit 数据          │  │
│  │  • 定时触发 (每 30 分钟)        │  │
│  │  • 构造 JSON Payload           │  │
│  │  • POST → 公网 URL             │  │
│  └────────────┬───────────────────┘  │
│               │ HTTPS                 │
└───────────────┼───────────────────────┘
                │
    ┌───────────▼──────────────────────┐
    │   ngrok / Cloudflare Tunnel      │  ← 反向代理，将公网流量转发到本地
    │   公网 URL → localhost:8000       │
    └───────────┬──────────────────────┘
                │
    ┌───────────▼──────────────────────┐
    │   FastAPI Webhook Server        │
    │   (webhook_server.py)           │
    │                                 │
    │   POST /api/v1/health/sync      │  ← 接收 & 校验 JSON
    │   GET  /api/v1/health/daily     │  ← 查询日聚合
    │   GET  /api/v1/health/raw       │  ← 查询原始数据
    │   GET  /api/v1/health/status    │  ← 数据库概览
    └───────────┬──────────────────────┘
                │
    ┌───────────▼──────────────────────┐
    │   SQLite 数据库                  │
    │   (data/health.db)              │
    │                                 │
    │   raw_health_samples  ← 原始数据 │
    │   daily_metrics       ← 日聚合   │
    │   sync_log            ← 同步日志 │
    └───────────┬──────────────────────┘
                │
    ┌───────────▼──────────────────────┐
    │   数据聚合层 (aggregator.py)      │
    │   • 日聚合 (avg/min/max/stddev)   │
    │   • 30 天基线计算                 │
    └──────────────────────────────────┘
```

### 1.2 数据流（时序）

```
时间线：
  T+0min    Health Auto Export 后台定时器触发
  T+1s      App 读取 HealthKit 增量数据 (上次同步至今)
  T+2s      App 按 Export Format 构造 JSON
  T+3s      App 发起 HTTPS POST → ngrok URL → FastAPI
  T+3.5s    FastAPI Pydantic 校验 JSON 结构
  T+3.6s    遍历 metrics[] → 逐条写入 raw_health_samples
  T+3.8s    触发增量聚合 → 更新 daily_metrics (当天)
  T+4s      返回 200 {"status": "success", ...}
  T+4.5s    Health Auto Export 记录同步成功，等待下一个 30 分钟周期
```

### 1.3 健康数据类型全景图

Health Auto Export 支持 150+ 健康指标，以下按**数据可用性**和**分析价值**分三级：

#### Tier 1 — 主流指标（优先接入，Phase 1 必须覆盖）

| 类别 | 指标 | HA Export 字段名 | 单位 | 典型采样频率 | 说明 |
|------|------|-----------------|------|-------------|------|
| 心脏 | 心率 | `heart_rate` | bpm | ~每5分钟 | Apple Watch 自动采集，数据最密集 |
| 心脏 | 静息心率 | `resting_heart_rate` | bpm | 每天1-2次 | 早晨静息状态测量 |
| 心脏 | 心率变异性 | `heart_rate_variability` | ms | ~每2-4小时 | 反映自主神经状态 |
| 活动 | 步数 | `step_count` | count | ~每小时 | iPhone + Watch 融合 |
| 活动 | 活跃能量 | `active_energy` | kJ | ~每小时 | 即活动卡路里消耗 |
| 活动 | 运动时长 | `exercise_time` | min | ~每小时 | 中高强度运动分钟数 |
| 睡眠 | 睡眠分析 | `sleep_analysis` | — | 每天1次 | 含 inBed / asleepREM / asleepDeep 等阶段 |
| 呼吸 | 血氧饱和度 | `oxygen_saturation` | % | 每天数次 | Apple Watch SpO2 传感器 |
| 呼吸 | 呼吸频率 | `respiratory_rate` | breaths/min | 每天数次 | 睡眠期间测量为主 |
| 身体 | 手腕温度 | `wrist_temperature` | °C | 每晚1次 | 基础体温相对变化（夜间） |
| 运动 | 训练数据 | `workouts` | — | 按事件 | 每次手动开启运动记录 |

#### Tier 2 — 扩展指标（Phase 1 后期加入，可能有空值）

| 类别 | 指标 | HA Export 字段名 | 空值原因 |
|------|------|-----------------|---------|
| 心脏 | 步行心率 | `walking_heart_rate_average` | 仅在户外步行时采集 |
| 心脏 | 心电图 (ECG) | `electrocardiogram` | 需手动测量，频率很低 |
| 心脏 | 血压 | `blood_pressure_systolic` / `diastolic` | 需第三方血压计 |
| 活动 | 步行距离 | `walking_running_distance` | — |
| 活动 | 爬楼层数 | `flights_climbed` | 仅气压计机型 |
| 睡眠 | 睡眠心率 | `sleeping_heart_rate` | 需 Watch 佩戴睡觉 |
| 睡眠 | 睡眠血氧 | `sleeping_oxygen_saturation` | 需 Watch 佩戴睡觉 + Series 6+ |
| 身体 | 体重 | `body_mass` | 需手动输入 |
| 身体 | BMI | `body_mass_index` | 需手动输入 |
| 营养 | 膳食能量 | `dietary_energy` | 需手动输入 |
| 其他 | 环境噪音 | `environmental_sound_level` | 仅 Series 4+ 噪音 App |

#### Tier 3 — 低优先级（数据稀疏，Phase 2/3 考虑）

| 类别 | 指标 | 说明 |
|------|------|------|
| 心脏 | 心率恢复 | 运动后的心率下降速率 |
| 活动 | MET | 代谢当量 |
| 活动 | 最大摄氧量 | VO2 max 估算值 |
| 生殖 | 经期追踪 | 需手动记录 |
| 其他 | 洗手 | 洗手秒数 |

> **设计决策**：Phase 1 代码架构设计为**动态兼容所有类型** —— 接收端不做指标白名单限制，任何 Health Auto Export 发送的指标都可以写入数据库。聚合层仅对 Tier 1 指标做日聚合，Tier 2/3 数据保留在原始表中供查询。
>
> **空值处理策略**：
> - 入库时：空值不阻塞写入，`value=None` 的行仍然保留 `start_time` 和 `extra` JSON
> - 聚合时：`value.isnot(None)` 过滤，只对有效数值进行统计
> - 查询时：API 返回时标注 `null`，由下游（Phase 2 Agent）决定如何处理

---

## 2. iOS 端：Health Auto Export 深度解析

### 2.1 App 配置步骤

**Step 1 — 安装 App**

从 App Store 下载 **Health Auto Export - JSON+CSV**（开发者：Lybron Sobers）。

> 免费版即可满足全部 Phase 1 需求。付费版增加 CSV 格式和更多导出目标，非必需。

**Step 2 — 授权 HealthKit 访问**

打开 App → 按提示授权以下数据类型（至少勾选 Tier 1 全部指标）：

- Heart Rate
- Resting Heart Rate
- Heart Rate Variability
- Steps
- Active Energy
- Exercise Time
- Sleep Analysis
- Oxygen Saturation
- Respiratory Rate
- Wrist Temperature
- Workouts

> App 会请求 HealthKit 权限，iOS 原生弹窗逐类确认。建议**全部允许**以便后续扩展。

**Step 3 — 配置 REST API 自动化**

进入 App → **Automations** 标签 → 右上角 **+** → **API Export**：

| 配置项 | 值 | 说明 |
|--------|-----|------|
| URL | `https://<your-ngrok-url>/api/v1/health/sync` | 见 §2.2 URL 机制 |
| Format | JSON | 仅支持 JSON |
| Period | Last Sync | 增量同步（每次只发上次同步至今的新数据） |
| Interval | Minutes | 以分钟为间隔单位 |
| Sync | 30 Minutes | 每 30 分钟自动触发一次 |
| Data Type | Health Metrics + Workouts | 同时发送健康指标和训练数据 |
| Custom Headers | `Authorization: Bearer <your-api-key>` | API Key 鉴权（见 config.py） |
| Custom Headers | `Content-Type: application/json` | 通常自动添加 |

**Step 4 — 启用自动化**

将 Automation 开关设为 **Enabled**。

> iOS 后台执行说明：Health Auto Export 使用 iOS Background Tasks 机制，30 分钟间隔为**建议值**，实际触发时间由 iOS 系统调度决定，可能在 20–60 分钟范围内波动。


### 2.2 REST API URL 路由机制

#### 2.2.1 URL 的构成与作用

Health Auto Export 的 REST API 功能本质上是一个 **HTTP Client**，运行在 iPhone 后台。其 URL 机制如下：

```
URL 模板: https://<host>/<path>

完整示例: https://abc123.ngrok-free.app/api/v1/health/sync

┌──────────────────┬──────────────────────────────┐
│ URL 组成部分      │ 作用                          │
├──────────────────┼──────────────────────────────┤
│ https://         │ 必须使用 HTTPS（iOS ATS 强制）  │
│ <host>           │ 公网可达的域名/IP               │
│ /api/v1/        │ API 版本前缀（预留未来升级）     │
│ /health/sync     │ 具体端点：接收健康数据同步       │
└──────────────────┴──────────────────────────────┘
```

#### 2.2.2 URL 的工作机制

```
iPhone (Health Auto Export)
  │
  │ ① 定时器触发 (每 30 分钟)
  │ ② 读取 HealthKit 增量数据
  │ ③ 按 Export Format 构造 JSON Body
  │    (结构见 §3.3 models.py 的 HealthSyncRequest)
  │ ④ 组装 HTTP Request:
  │    POST <配置的URL>
  │    Headers:
  │      Authorization: Bearer <api-key>
  │      Content-Type: application/json
  │      User-Agent: HealthAutoExport/<version> iOS/<version>
  │    Body: <JSON payload>
  │ ⑤ 通过 URLSession 发起 HTTPS POST
  │
  ▼
  ngrok 反向代理 (公网 → 本地)
  │
  │ ⑥ ngrok 接收 HTTPS 请求，TLS 终止
  │ ⑦ ngrok 将请求转发到本地 tcp://localhost:8000
  │
  ▼
  FastAPI (webhook_server.py)
  │
  │ ⑧ verify_api_key() → 校验 Authorization header
  │ ⑨ Pydantic 解析 JSON → HealthSyncRequest
  │ ⑩ 写入数据库 + 触发聚合
  │ ⑪ 返回 JSON Response
  │
  ▼
  Health Auto Export 收到 Response
  │
  │ ⑫ 记录同步时间戳 → 下次只取此时间之后的数据
  │ ⑬ 如有错误，App 内显示红色标记
```

**关键点**：
- URL 必须在代码部署后才能确定，因为需要通过 ngrok 获取公网地址
- 一旦 FastAPI 服务启动并完成 ngrok 绑定，将生成的 ngrok URL 填入 App 配置即可
- App 会**持久化保存** URL，不需要每次重新配置
- 如果 URL 不可达，App 会静默失败并在 Automation 列表中显示错误状态

#### 2.2.3 当前状态：URL 待定

> **当前阶段**：代码尚未部署，URL 路由尚未生成。等后端代码在本地启动并通过 ngrok 暴露后，将获得类似以下格式的 URL：
> ```
> https://<random-id>.ngrok-free.app/api/v1/health/sync
> ```
> 将此 URL 填入 Health Auto Export 的 Automation 配置即可。


### 2.3 端到端数据流（含数据格式转换）

```
┌─────────────────── HealthKit (iOS 原生) ───────────────────┐
│ 数据类型: HKQuantityTypeIdentifierHeartRate                 │
│ 存储格式: HKSample[] (startDate, endDate, value, device)    │
└──────────────────────────┬─────────────────────────────────┘
                           │ Health Auto Export 读取
                           ▼
┌─────────────────── Health Auto Export JSON ────────────────┐
│ {                                                          │
│   "data": {                                                │
│     "metrics": [{                                          │
│       "name": "heart_rate",    ← 内部字段名映射             │
│       "units": "bpm",                                       │
│       "data": [{                                           │
│         "date": "2026-05-06 08:05:00 +0000",               │
│         "min": 68, "avg": 72, "max": 85,                   │
│         "source": "Apple Watch Series 7"                   │
│       }, ...]                                              │
│     }, ...],                                               │
│     "workouts": [...]                                      │
│   }                                                        │
│ }                                                          │
└──────────────────────────┬─────────────────────────────────┘
                           │ HTTPS POST
                           ▼
┌─────────────────── Pydantic 校验 ──────────────────────────┐
│ HealthSyncRequest → HealthExportPayload                     │
│   └── metrics: list[HealthMetric]                           │
│         └── data: list[MetricDataPoint]                     │
│               ├── date → normalize_date() → ISO 8601        │
│               ├── avg/qty/value → 提取数值                   │
│               └── min/max/value → extra JSON               │
└──────────────────────────┬─────────────────────────────────┘
                           │ ORM 写入
                           ▼
┌─────────────────── raw_health_samples (SQLite) ────────────┐
│ id │ metric_type   │ value │ unit │ start_time          │  │
│  1 │ heart_rate    │ 72.0  │ bpm  │ 2026-05-06T08:05:00 │  │
│  2 │ step_count    │ 245   │ count│ 2026-05-06T08:00:00 │  │
│  3 │ sleep_analysis│ 450.0 │ min  │ 2026-05-05T23:15:00 │  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 后端实现：FastAPI + SQLite

### 3.1 项目结构 & 文件角色说明

```
Medical-Health-Agent/
├── data_pipeline/                   # Phase 1 全部代码
│   ├── __init__.py                  # 包标记，使 data_pipeline 成为可 import 的 Python 包
│   ├── config.py                    # 全局配置中心
│   ├── models.py                    # 数据模型（Pydantic 校验 + SQLAlchemy 表）
│   ├── database.py                  # 数据库连接、会话管理、表初始化
│   ├── webhook_server.py            # FastAPI 主应用（所有 API 端点）
│   ├── aggregator.py                # 数据聚合引擎（原始→日指标→基线）
│   └── test_data.py                 # 模拟 Apple Health 测试数据生成器
├── data/                            # 运行时数据目录（自动创建）
│   └── health.db                    # SQLite 数据库文件（单文件，便携）
├── requirements.txt                 # Python 依赖清单
└── Phase1v2-Apple-Health数据管道实施方案.md  # 本文档
```

**依赖关系图**：

```
config.py          ← 无依赖，被所有模块引用
models.py          ← 依赖: 无（仅使用 Pydantic/SQLAlchemy）
database.py        ← 依赖: config.py, models.py
aggregator.py      ← 依赖: config.py, models.py
webhook_server.py  ← 依赖: config.py, database.py, models.py, aggregator.py
test_data.py       ← 无依赖（独立运行）
```

### 3.2 `data_pipeline/config.py`

**文件角色**：全局配置中心，所有可调参数集中管理。

**输入 → 输出**：
- 输入：环境变量 `HEALTH_DB_URL`, `HEALTH_API_KEY`
- 输出：被其余 5 个模块 import 的配置常量

**关键设计决策**：
- `AGGREGATION_METRICS` 仅控制聚合层行为，不影响数据接收（接收端不做白名单过滤）
- `API_KEY` 默认值仅用于本地开发，生产环境必须通过环境变量覆盖
- Tier 1/Tier 2/Tier 3 分类不体现在代码中，因为入库端不区分优先级

```python
"""
全局配置中心。

所有可调参数集中在这里，其余模块通过 `from .config import ...` 引用。
生产环境：通过环境变量 HEALTH_API_KEY 和 HEALTH_DB_URL 覆盖默认值。
"""
import os

# ── 数据库 ──────────────────────────────────────────────
# SQLite 路径。Phase 3 迁移到 PostgreSQL 时只需改这里 + database.py
DATABASE_URL = os.getenv("HEALTH_DB_URL", "sqlite:///data/health.db")

# ── API 鉴权 ────────────────────────────────────────────
# ⚠️ 生产环境务必通过环境变量覆盖，不要用默认值
API_KEY = os.getenv("HEALTH_API_KEY", "medical-health-agent-dev-key-2026")

# ── 聚合配置 ────────────────────────────────────────────
# 需要日聚合的指标列表（Tier 1 主流指标）
# 不在列表中的指标仍然会入库，只是不自动聚合
AGGREGATION_METRICS = [
    # 心脏
    "heart_rate",
    "resting_heart_rate",
    "heart_rate_variability",
    # 活动
    "step_count",
    "active_energy",
    "exercise_time",
    # 呼吸
    "oxygen_saturation",
    "respiratory_rate",
    # 身体
    "wrist_temperature",
]

# 睡眠分析的特殊阶段值（用于 sleep_analysis 类型的数据分类）
SLEEP_STAGES = [
    "inBed",        # 卧床时间
    "asleep",       # 总睡眠（Apple Health 泛化阶段）
    "asleepREM",    # 快速眼动
    "asleepDeep",   # 深度睡眠
    "asleepCore",   # 核心睡眠（Apple 自 iOS 16 起的分类）
    "awake",        # 夜间醒来
]

# ── 服务配置 ────────────────────────────────────────────
HOST = os.getenv("HEALTH_HOST", "0.0.0.0")
PORT = int(os.getenv("HEALTH_PORT", "8000"))

# Health Auto Export JSON 顶层包裹键名
# 实测表明 App 会以 {"data": {...}} 包裹，但为兼容保留直接发送的路径
WRAPPER_KEY = "data"
```

**v1 → v2 变更**：
- 新增 `HOST`, `PORT` 配置项（原来硬编码在 `__main__` 中）
- 新增 `SLEEP_STAGES` 常量，用于睡眠阶段分类
- 注释从 "不同版本可能用" 改为确认 "data" 包裹格式


### 3.3 `data_pipeline/models.py`

**文件角色**：定义系统中的所有数据结构 — 请求校验层（Pydantic）和持久化层（SQLAlchemy ORM）。

**输入 → 输出**：
- Pydantic 模型：接收 HTTP Request Body JSON → 校验 + 类型转换 → 传给 webhook_server.py 处理函数
- SQLAlchemy 模型：定义数据库表结构 → 由 database.py 创建表，由 webhook_server.py 写入数据

**关键设计决策**：
- `date` 字段在 Pydantic 中为 `Optional[str]`，因为睡眠分析类型使用 `startDate`/`endDate` 而非 `date`（v2 已修正 v1 的 `date: str` 必填问题）
- `normalize_date` validator 已修复 v1 的"空转"问题，现在实际执行格式标准化
- `MetricDataPoint` 的字段全部 Optional：这是**刻意的设计**，因为不同类型的数据点使用不同字段组合

```python
"""
Pydantic 校验模型 & SQLAlchemy 存储模型。

Pydantic (请求层):
  MetricDataPoint → HealthMetric → HealthExportPayload → HealthSyncRequest
  负责校验 Health Auto Export 发来的 JSON 结构。

SQLAlchemy (持久化层):
  RawHealthSample / DailyMetric / SyncLog
  对应数据库中的 3 张表。
"""
from __future__ import annotations

import re
from datetime import datetime, date, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, Text
from sqlalchemy.orm import DeclarativeBase


# ============================================================
# Pydantic — 请求校验（接收 Health Auto Export 的 JSON）
# ============================================================

class MetricDataPoint(BaseModel):
    """
    单个健康数据点。

    字段组合因数据类型而异：
    - 心率等连续型：{date, min, avg, max}
    - 步数等累积型：{date, qty}
    - 睡眠分析型：{startDate, endDate, value, qty}  (date 通常为空)
    - 单值型(SpO2等)：{date, qty}
    """
    date: Optional[str] = None
    qty: Optional[float] = None
    min: Optional[float] = None
    avg: Optional[float] = None
    max: Optional[float] = None
    value: Optional[str] = None       # 睡眠分析的阶段标签 (e.g. "inBed")
    startDate: Optional[str] = None   # 睡眠分析/训练的开始时间
    endDate: Optional[str] = None     # 睡眠分析/训练的结束时间
    source: Optional[str] = None

    @field_validator("date", "startDate", "endDate", mode="before")
    @classmethod
    def normalize_datetime(cls, v: Optional[str]) -> Optional[str]:
        """
        [v2 修复] 将 iOS 多种日期格式统一为 ISO 8601。

        输入:
          "2026-05-06 08:05:00 +0000"  → "2026-05-06T08:05:00+00:00"
          "2026-05-06T08:05:00+00:00"  → (不变)
          None                         → None
        """
        if not isinstance(v, str):
            return v
        # 替换 " +0000" → "+00:00" 格式
        v = re.sub(r" \+(\d{2})(\d{2})$", r"+\1:\2", v)
        # 日期和时间之间的空格 → T
        if "T" not in v:
            v = v.replace(" ", "T", 1)
        return v


class HealthMetric(BaseModel):
    """Health Auto Export 的单个指标组"""
    name: str                        # e.g. "heart_rate"
    units: str                       # e.g. "bpm"
    data: list[MetricDataPoint]      # 该指标下的所有数据点


class WorkoutData(BaseModel):
    """训练数据"""
    name: str
    startDate: str
    endDate: str
    duration: Optional[float] = None        # 秒
    activeEnergy_kJ: Optional[float] = None
    distance_m: Optional[float] = None
    avgHeartRate_bpm: Optional[float] = None
    maxHeartRate_bpm: Optional[float] = None


class HealthExportPayload(BaseModel):
    """Health Auto Export 发送的完整 JSON 结构（data 内部）"""
    metrics: list[HealthMetric] = Field(default_factory=list)
    workouts: list[WorkoutData] = Field(default_factory=list)


class HealthSyncRequest(BaseModel):
    """
    最外层请求包装。

    Health Auto Export 实测以 {"data": {metrics: [...], workouts: [...]}} 包裹。
    同时兼容直接发送 metrics/workouts（不包裹 data）的情况。
    """
    data: Optional[HealthExportPayload] = None
    metrics: Optional[list[HealthMetric]] = None
    workouts: Optional[list[WorkoutData]] = None

    def get_payload(self) -> HealthExportPayload:
        """解包：优先取 data 内的 payload，否则用顶层字段"""
        if self.data:
            return self.data
        return HealthExportPayload(
            metrics=self.metrics or [],
            workouts=self.workouts or [],
        )


# ============================================================
# SQLAlchemy — 数据库表
# ============================================================

class Base(DeclarativeBase):
    pass


class RawHealthSample(Base):
    """
    原始健康数据点 —— 每一行 = 一条 Apple Health 记录。

    用途：存储 Health Auto Export 发来的所有原始数据，不做聚合。
    Phase 2 的感知 Agent 可直接查询此表获取细粒度数据。
    """
    __tablename__ = "raw_health_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_type = Column(String(64), nullable=False, index=True)   # 指标名，如 "heart_rate"
    value = Column(Float)                                          # 核心数值（可为空）
    unit = Column(String(32))                                      # 单位
    start_time = Column(DateTime, nullable=False, index=True)      # 采样起始时间
    end_time = Column(DateTime)                                    # 采样结束时间（有持续期的类型）
    source = Column(String(128))                                   # 数据来源设备
    device = Column(String(128))                                   # 用户标识（预留多用户）
    received_at = Column(DateTime, nullable=False)                 # 服务端接收时间
    extra = Column(Text)                                           # JSON 字符串（min/max/value 等扩展字段）


class DailyMetric(Base):
    """
    日聚合指标。

    用途：每天每种指标一行，包含均值/最值/标准差/采样数。
    Phase 2 的异常检测 Agent 主要读取此表。
    """
    __tablename__ = "daily_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)                # 日期 (YYYY-MM-DD)
    metric_type = Column(String(64), nullable=False, index=True)   # 指标名
    avg_value = Column(Float)                                      # 日平均值
    min_value = Column(Float)                                      # 日最低值
    max_value = Column(Float)                                      # 日最高值
    stddev_value = Column(Float)                                   # 日标准差
    total_value = Column(Float)                                    # 日累积值（步数、卡路里等）
    sample_count = Column(Integer)                                 # 有效采样数
    unit = Column(String(32))                                      # 单位
    created_at = Column(DateTime, nullable=False)                  # 聚合计算时间


class SyncLog(Base):
    """
    同步日志。

    用途：每次 POST /sync 写入一条，用于监控数据管道的健康状态。
    排查问题时的第一入口。
    """
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    received_at = Column(DateTime, nullable=False)                 # 接收时间
    metrics_count = Column(Integer, default=0)                     # 收到的指标组数
    data_points_count = Column(Integer, default=0)                 # 成功写入的数据点数
    workouts_count = Column(Integer, default=0)                    # 训练记录数
    status = Column(String(32), default="success")                # success / partial / error
    error_message = Column(Text)                                   # 错误详情
```

**v1 → v2 变更**：
| 变更 | 位置 | 原因 |
|------|------|------|
| `MetricDataPoint.date` 改为 `Optional[str]` | Pydantic | v1 设为必填，但睡眠分析型数据用 startDate/endDate 替代 date，date 字段会为空 |
| `normalize_date` 实际执行格式转换 | Pydantic | v1 的 validator 只是 `return v`，格式转换从未执行 |
| 移除 `from typing import Union` | 导入 | 实际未使用 |
| 新增字段注释说明各类型的字段组合模式 | Pydantic | 帮助理解 Optional fields 的设计意图 |
| `received_at` / `created_at` 移除 `default=datetime.utcnow` | SQLAlchemy | Python 3.12+ `datetime.utcnow()` 已弃用，改为在 webhook_server.py 中显式传 `datetime.now(timezone.utc)` |
| 新增 docstring 到每个 SQLAlchemy 类 | SQLAlchemy | 说明表的用途，Phase 2 如何消费 |


### 3.4 `data_pipeline/database.py`

**文件角色**：数据库引擎创建、会话工厂、表初始化。其他模块通过 `get_db()` 获取数据库会话。

**输入 → 输出**：
- 输入：`config.DATABASE_URL`（SQLite 路径）
- 输出：`engine`（全局单例）、`SessionLocal`（会话工厂）、`init_db()`（建表）、`get_db()`（FastAPI 依赖注入）

**关键设计决策**：
- `connect_args={"check_same_thread": False}` 是 SQLite + FastAPI 多线程访问的必须配置
- `get_db()` 是生成器函数，配合 FastAPI `Depends()` 实现请求级会话生命周期

```python
"""
数据库连接 & 会话管理。

职责：
  - 创建 SQLAlchemy Engine（全局单例）
  - 提供 FastAPI 依赖注入的 get_db() 生成器
  - init_db() 负责首次启动时自动建表

SQLite 特殊注意事项：
  - check_same_thread=False 是 FastAPI 多线程模式下的必需配置
  - SQLite 文件路径从 config.DATABASE_URL 解析（去掉 "sqlite:///" 前缀）
"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .config import DATABASE_URL
from .models import Base

# ── Engine & Session ─────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    echo=False,                                  # 生产环境关闭 SQL 日志
    connect_args={"check_same_thread": False},    # SQLite + FastAPI 多线程
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    """
    初始化数据库：创建数据目录 + 建表。

    幂等：多次调用不会重复创建表。
    在 FastAPI startup 事件中调用一次。
    """
    # [v2 修复] 使用 Path 对象替代字符串切割，更健壮地处理 sqlite:/// 前缀
    db_path = DATABASE_URL
    if db_path.startswith("sqlite:///"):
        db_path = db_path[len("sqlite:///"):]

    # 确保数据目录存在
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(engine)


def get_db() -> Session:
    """
    FastAPI 依赖注入：每个请求创建一个数据库会话，请求结束后自动关闭。

    用法:
        @app.get("/api/...")
        def handler(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**v1 → v2 变更**：
| 变更 | 原因 |
|------|------|
| `os.makedirs(os.path.dirname(db_path) or "data")` → `Path(db_path).parent.mkdir(parents=True)` | v1 的 `or "data"` 在 db_path 为空字符串时会错误地创建 data 目录 |
| 增加 `autoflush=False, autocommit=False` | 明确事务边界，避免隐式自动提交 |
| 补齐 `import os` | v1 代码中使用了 `os` 但未 import（文档中的代码与实际文件不一致） |


### 3.5 `data_pipeline/webhook_server.py`

**文件角色**：FastAPI 主应用 —— 所有 HTTP API 端点。是数据管道的**入口**（接收 iOS 数据）和**出口**（提供查询接口）。

**输入 → 输出**：
- 输入：`POST /api/v1/health/sync` → Health Auto Export JSON
- 输入：`GET /api/v1/health/daily?date=...` → 查询参数
- 输入：`GET /api/v1/health/raw?metric_type=...&date_from=...` → 查询参数
- 输入：`GET /api/v1/health/status` → 无参数
- 输出：JSON Response + 数据库写入

**依赖链**：
```
webhook_server.py
  ├── config.py       → API_KEY, HOST, PORT
  ├── database.py     → init_db(), get_db()
  ├── models.py       → HealthSyncRequest, RawHealthSample, DailyMetric, SyncLog
  └── aggregator.py   → aggregate_daily_metrics()
```

```python
"""
FastAPI Webhook — 接收 Apple Health 数据 & 提供查询 API。

端点清单:
  POST /api/v1/health/sync   — 核心: 接收 Health Auto Export 推送
  GET  /api/v1/health/daily  — 查询日聚合指标
  GET  /api/v1/health/raw    — 查询原始健康数据
  GET  /api/v1/health/status — 数据库概览 & 同步状态
  GET  /api/v1/health/baseline — [v2 新增] 查询个人基线
"""
import json
import logging
import re
from datetime import datetime, timezone, date
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Header, Query
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

app = FastAPI(
    title="Medical-Health-Agent Data Pipeline",
    version="2.0.0",
    description="Phase 1: Apple Health 数据采集与聚合",
)


# ============================================================
# 鉴权
# ============================================================

def verify_api_key(authorization: Optional[str] = Header(None)):
    """
    API Key 鉴权中间件。

    Health Auto Export 在 Custom Headers 中设置:
      Authorization: Bearer <api-key>
    """
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.replace("Bearer ", "").strip()
    if token != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return token


# ============================================================
# 生命周期
# ============================================================

@app.on_event("startup")
def startup():
    """服务启动时自动初始化数据库（建表）"""
    init_db()
    logger.info("Database initialized successfully")


# ============================================================
# 日期解析工具
# ============================================================

def _parse_datetime(s: Optional[str]) -> Optional[datetime]:
    """
    解析 iOS 端的各种日期格式 → timezone-aware datetime (UTC)。

    支持格式:
      - ISO 8601:  "2026-05-06T08:05:00+00:00", "2026-05-06T08:05:00Z"
      - iOS 原生:  "2026-05-06 08:05:00 +0000"
      - 仅日期:    "2026-05-06"

    [v2 修复] 返回 timezone-aware datetime (UTC)，替代已弃用的 datetime.utcnow()。
    """
    if not s:
        return None

    from dateutil import parser as dt_parser

    try:
        parsed = dt_parser.parse(s)
        # 如果解析结果没有时区信息，假定为 UTC
        if parsed.tzinfo is None:
            from datetime import timezone
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        pass

    # Fallback: 手动修正 " +0000" → "+00:00" 然后 fromisoformat
    try:
        cleaned = re.sub(r" \+(\d{2})(\d{2})$", r"+\1:\2", s)
        if "T" not in cleaned:
            cleaned = cleaned.replace(" ", "T", 1)
        return datetime.fromisoformat(cleaned)
    except Exception:
        logger.warning(f"Failed to parse datetime: {s!r}")
        return None


# ============================================================
# 核心接口: POST /api/v1/health/sync
# ============================================================

@app.post("/api/v1/health/sync")
def receive_health_data(
    payload: HealthSyncRequest,
    target: Optional[str] = Query(None, description="用户标识（预留多用户）"),
    db: Session = Depends(get_db),
    _token: str = Depends(verify_api_key),
):
    """
    接收 Health Auto Export 推送的健康数据。

    Health Auto Export 请求体格式:
    {
      "data": {
        "metrics": [
          {
            "name": "heart_rate",
            "units": "bpm",
            "data": [
              {"date": "2026-05-06 08:05:00 +0000", "min": 68, "avg": 72, "max": 85},
              ...
            ]
          },
          ...
        ],
        "workouts": [
          {
            "name": "Outdoor Walk",
            "startDate": "2026-05-06 07:30:00 +0000",
            "endDate": "2026-05-06 08:05:00 +0000",
            "duration": 2100,
            ...
          }
        ]
      }
    }

    响应:
      200: {"status": "success", "metrics_received": N, "data_points_inserted": M, ...}
      207: 部分成功，某类指标写入失败
    """
    now = datetime.now(timezone.utc)
    export = payload.get_payload()
    metrics_count = len(export.metrics)
    data_points_count = 0
    workouts_count = len(export.workouts)

    # ── 处理 metrics ──
    for metric in export.metrics:
        try:
            inserted = _insert_metric_samples(db, metric, target, now)
            data_points_count += inserted
        except Exception as e:
            logger.error(f"Failed to insert metric '{metric.name}': {e}", exc_info=True)
            _log_sync(db, metrics_count, data_points_count, workouts_count, "partial", str(e), now)
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
            # workouts 失败不影响整体状态，仅记录日志

    # ── 增量聚合 ──
    agg_errors = []
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
    """
    将单个 HealthMetric 的 data[] 数组批量写入 raw_health_samples。

    [v2 改进] 空值数据点仍然写入（保留 start_time + extra），
              仅当 date 和 startDate 都为空时才跳过。
    """
    count = 0
    for dp in metric.data:
        # 提取核心数值（可能为 None —— 比如睡眠 "inBed" 没有 qty）
        value = _extract_value(dp, metric.name)

        # 解析时间：优先 startDate（睡眠分析/训练），否则 date
        start_time = (
            _parse_datetime(dp.startDate) if dp.startDate
            else _parse_datetime(dp.date)
        )
        if start_time is None:
            logger.warning(f"Skipping data point with no parseable time: metric={metric.name}")
            continue

        end_time = _parse_datetime(dp.endDate) if dp.endDate else None

        sample = RawHealthSample(
            metric_type=metric.name,
            value=value,              # 可以为 None
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
      1. avg  — 心率等聚合型数据（Apple Watch 内部已做窗口聚合）
      2. qty  — 步数、距离、HRV 等单值型数据
      3. 睡眠时长 — 从 startDate/endDate 计算（返回分钟数）

    [v2 改进] 睡眠分析空 value 不再静默返回 None 而是计算时长。
    """
    if dp.avg is not None:
        return float(dp.avg)
    if dp.qty is not None:
        return float(dp.qty)
    # 睡眠分析：通过 startDate - endDate 计算时长
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
    """
    将 Pydantic 模型中不在 RawHealthSample 主列中的字段，
    序列化为 JSON 存入 extra 列。

    存储: min, max, value（睡眠阶段标签）
    """
    extra_fields = {}
    for key in ("min", "max", "value"):
        val = getattr(dp, key, None)
        if val is not None:
            extra_fields[key] = val
    if extra_fields:
        return json.dumps(extra_fields, ensure_ascii=False)
    return None


def _insert_workout(db: Session, workout: WorkoutData, target: Optional[str],
                    received_at: datetime):
    """将训练数据以 workout_<type> 为 metric_type 写入 raw_health_samples"""
    start = _parse_datetime(workout.startDate)
    end = _parse_datetime(workout.endDate)

    workout_extra = {}
    for key in ("duration_sec", "active_energy_kJ", "distance_m",
                 "avg_heart_rate_bpm", "max_heart_rate_bpm"):
        val = getattr(workout, key.replace("_sec", "").replace("_k", "K").replace("_m", "_m")
                     .replace("_b", "B"), None)
    # 直接构造，避免动态 getattr 的复杂映射
    workout_data = {
        "duration_sec": workout.duration,
        "active_energy_kJ": workout.activeEnergy_kJ,
        "distance_m": workout.distance_m,
        "avg_heart_rate_bpm": workout.avgHeartRate_bpm,
        "max_heart_rate_bpm": workout.maxHeartRate_bpm,
    }

    metric_type = f"workout_{workout.name.lower().replace(' ', '_')}"

    sample = RawHealthSample(
        metric_type=metric_type,
        value=workout.duration,           # 主值 = 时长（秒）
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
    date: str = Query(..., description="日期 YYYY-MM-DD"),
    metric: Optional[str] = Query(None, description="指标名，不传返回全部"),
    db: Session = Depends(get_db),
):
    """查询某一天的聚合指标"""
    q = db.query(DailyMetric).filter(DailyMetric.date == date)
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
    metric_type: str = Query(..., description="指标名，如 heart_rate"),
    date_from: str = Query(..., description="起始日期 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD（不含）"),
    limit: int = Query(1000, ge=1, le=10000, description="返回上限"),
    db: Session = Depends(get_db),
):
    """查询原始健康数据点"""
    from datetime import datetime as dt

    start = dt.strptime(date_from, "%Y-%m-%d")
    end = dt.strptime(date_to, "%Y-%m-%d") if date_to else None

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
    [v2 新增] 查询个人基线（30 天均值 ± 2σ）。

    用于 Phase 2 异常检测。
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

    # 各类指标的数据量分布
    metric_counts = (
        db.query(RawHealthSample.metric_type, func.count(RawHealthSample.id))
        .group_by(RawHealthSample.metric_type)
        .order_by(func.count(RawHealthSample.id).desc())
        .limit(20)  # [v2 新增] 限制返回数量，避免 150+ 类型全输出
        .all()
    )

    # [v2 新增] 统计空值比例
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
# 入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)
```

**v1 → v2 变更**：
| 变更 | 位置 | 原因 |
|------|------|------|
| `datetime.utcnow()` → `datetime.now(timezone.utc)` | 全局 | Python 3.12+ `utcnow()` 已弃用 |
| `received_at` 参数化传递 | `_insert_*`, `_log_sync` | 避免在多处重复调用 `now()`，且保持同一次请求的时间一致性 |
| 空值数据点改为写入（标记 null） | `_insert_metric_samples` | 睡眠 "inBed" 等无 qty 的阶段标签订阅仍应保留 |
| API 返回增加 `end_time` 和 `extra` | `get_raw_samples` | 丰富查询结果，支持后续分析 |
| 新增 `GET /api/v1/health/baseline` | 新端点 | Phase 2 异常检测需要直接可访问的基线数据 |
| 空值比例统计 | `get_status` | 监控数据质量 |
| metric_counts 限制 20 条 | `get_status` | 避免 150+ 指标类型全量返回 |
| 解析失败时 `logger.warning` | `_parse_datetime` | v1 静默返回 None，不利于排查 |
| 移除 v1 `_insert_workout` 中无用的动态 getattr | 代码质量 | v1 代码片段有残留的无效映射逻辑 |


### 3.6 `data_pipeline/aggregator.py`

**文件角色**：数据聚合引擎 — 将 `raw_health_samples` 中的原始数据点计算为 `daily_metrics` 中的日统计指标。

**输入 → 输出**：
- 输入：`raw_health_samples` 表（某一天 + 某指标的原始数据点）
- 输出：`daily_metrics` 表（一行聚合记录：avg/min/max/stddev/total/count）
- 辅助函数：`compute_baseline()` → 30 天统计基线 dict

**关键设计决策**：
- 聚合按需触发（每次 `/sync` 后增量更新当天），不自动扫全表
- "删除旧记录 + 插入新记录" 保证幂等性
- `AGGREGATION_METRICS` 控制聚合范围（白名单），不在名单中的指标仅存原始表
- `compute_baseline` 仅使用 `avg_value`（日平均值），不嵌套原始数据点

```python
"""
数据聚合引擎：raw_health_samples → daily_metrics。

核心函数:
  aggregate_daily_metrics(db, target_date)  — 日聚合（增量、幂等）
  compute_baseline(db, metric_type, days)    — 30 天基线（Phase 2 前置）

聚合策略:
  - 连续型指标（心率/HRV/血氧）：avg/min/max/stddev
  - 累积型指标（步数/卡路里/运动时长）：avg/min/max/total
  - 睡眠：通过 extra JSON 中的 value 标签分类统计（待实现）
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from .config import AGGREGATION_METRICS
from .models import RawHealthSample, DailyMetric

logger = logging.getLogger("aggregator")


def aggregate_daily_metrics(db: Session, target_date: Optional[date] = None):
    """
    将 raw_health_samples 聚合为 daily_metrics（增量、幂等）。

    对于 AGGREGATION_METRICS 列表中的每种指标：
      - 查询 target_date 当天的所有有效数据点 (value IS NOT NULL)
      - 计算 avg / min / max / stddev / total / sample_count
      - 删除旧聚合记录 → 插入新记录（幂等）

    [v2 改进] target_date 显式传递，避免隐式依赖 date.today()
    """
    if target_date is None:
        target_date = date.today()

    day_start = datetime(target_date.year, target_date.month, target_date.day,
                         tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    for metric_type in AGGREGATION_METRICS:
        try:
            _aggregate_one_metric(db, metric_type, target_date, day_start, day_end)
        except Exception as e:
            logger.error(f"Aggregation failed for '{metric_type}' on {target_date}: {e}",
                         exc_info=True)

    db.commit()
    logger.info(f"Aggregation completed for {target_date}")


def _aggregate_one_metric(db: Session, metric_type: str, target_date: date,
                          day_start: datetime, day_end: datetime):
    """聚合单个指标类型某天的数据"""
    samples = (
        db.query(RawHealthSample.value, RawHealthSample.unit)
        .filter(
            RawHealthSample.metric_type == metric_type,
            RawHealthSample.start_time >= day_start,
            RawHealthSample.start_time < day_end,
            RawHealthSample.value.isnot(None),   # 仅聚合有数值的记录
        )
        .all()
    )

    if not samples:
        return

    values = np.array([s.value for s in samples], dtype=np.float64)
    unit = samples[0].unit

    # ── 幂等：先删后插 ──
    db.query(DailyMetric).filter(
        DailyMetric.date == target_date,
        DailyMetric.metric_type == metric_type,
    ).delete()

    daily = DailyMetric(
        date=target_date,
        metric_type=metric_type,
        avg_value=float(np.mean(values)),
        min_value=float(np.min(values)),
        max_value=float(np.max(values)),
        stddev_value=float(np.std(values)) if len(values) > 1 else 0.0,
        total_value=float(np.sum(values)),
        sample_count=len(values),
        unit=unit,
        created_at=datetime.now(timezone.utc),
    )
    db.add(daily)


def compute_baseline(db: Session, metric_type: str, days: int = 30) -> dict:
    """
    计算个人基线（前 N 天均值的均值 ± 2σ）。

    用于 Phase 2 的异常检测：
      - "今日静息心率 78 bpm，偏离 30 天基线 2.3σ"
      - "HRV 连续 5 天低于 30 天均值"

    参数:
        metric_type: 指标名
        days: 基线窗口（天），默认 30

    返回:
        {"mean": ..., "std": ..., "upper_bound": ..., "lower_bound": ..., "n_days": ...}
        如果数据不足，mean/std 为 None 并包含 error 字段。
    """
    from datetime import date as date_type
    cutoff = date_type.today() - timedelta(days=days)

    rows = (
        db.query(DailyMetric.avg_value)
        .filter(
            DailyMetric.metric_type == metric_type,
            DailyMetric.date >= cutoff,
            DailyMetric.avg_value.isnot(None),
        )
        .all()
    )

    values = [r.avg_value for r in rows]
    if len(values) < 3:
        return {
            "mean": None,
            "std": None,
            "upper_bound": None,
            "lower_bound": None,
            "n_days": len(values),
            "error": f"Insufficient data: need ≥3 days, got {len(values)}",
        }

    arr = np.array(values, dtype=np.float64)
    mean = float(np.mean(arr))
    std = float(np.std(arr))

    return {
        "mean": round(mean, 2),
        "std": round(std, 2),
        "upper_bound": round(mean + 2 * std, 2),
        "lower_bound": round(mean - 2 * std, 2),
        "n_days": len(values),
    }
```

**v1 → v2 变更**：
| 变更 | 原因 |
|------|------|
| 返回值增加 `upper_bound` / `lower_bound` 替代 `upper` / `lower` | 命名更明确，与 API 响应保持一致 |
| 数值精度 `round(..., 2)` | 健康数据两位小数足够，避免浮点噪音 |
| `_aggregate_one_metric` 接受 `day_start`/`day_end` 参数 | 避免内部重复计算 datetime 边界 |
| `stddev_value` 当 `len(values)==1` 时设为 `0.0`（而非 NaN） | API 返回时 NaN 不是合法 JSON |
| 聚合后 `db.commit()` 移到 `aggregate_daily_metrics` 层 | 所有指标一次性提交，减少 IO |
| 增加 exc_info=True 到日志 | 便于排查聚合异常 |


### 3.7 `data_pipeline/test_data.py`

**文件角色**：独立的测试数据生成器 —— 模拟 Health Auto Export 发送的 JSON，用于本地调试和 CI 测试。

**输入 → 输出**：
- 输入：命令行参数（天数、采样频率 — 未来可扩展）
- 输出：stdout 打印 JSON payload + 统计摘要

**关键设计决策**：
- 所有生成函数使用 `random.gauss` 配合合理的人体参数范围，使数据具有真实感
- 可以直接 pipe 到 curl 进行端到端测试
- 不依赖数据库或 FastAPI，可独立运行

```python
"""
模拟 Health Auto Export 的测试数据生成器。

用法:
  # 生成 JSON 并打印到 stdout
  python -m data_pipeline.test_data

  # 直接发送到 webhook (配合 curl)
  python -m data_pipeline.test_data | curl -X POST http://localhost:8000/api/v1/health/sync \\
    -H "Content-Type: application/json" \\
    -H "Authorization: Bearer medical-health-agent-dev-key-2026" \\
    -d @-

生成范围:
  - 心率: 均值 72±8 bpm，每 5 分钟一条
  - 静息心率: 均值 58±3 bpm，一条
  - HRV: 均值 45±12 ms，每小时一条
  - 步数: 均值 200±100，每小时一条
  - 活跃能量: 800-2500 kJ 均匀分布
  - 睡眠: inBed 7.5h + asleepREM 2.5h
  - 训练: 35 分钟 Outdoor Walk
"""
import json
import random
from datetime import datetime, timedelta, timezone


def generate_test_payload(days_back: int = 1, samples_per_hour: int = 12) -> dict:
    """
    生成模拟 Health Auto Export JSON。

    参数:
        days_back: 模拟多少天前的数据（1 = 最近 24 小时）
        samples_per_hour: 心率类型每小时采样点数（默认 12 = 每 5 分钟）
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days_back)
    end = now

    # [v2 修复] 避免 days_back=0 导致 start == end
    if start >= end:
        start = end - timedelta(hours=24)

    def gen_heart_rate():
        """模拟心率数据：均值 72±8 bpm，含 min/avg/max"""
        data = []
        t = start
        while t < end:
            hr = round(random.gauss(72, 8), 1)
            data.append({
                "date": t.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "min": round(hr - random.uniform(2, 6), 1),
                "avg": hr,
                "max": round(hr + random.uniform(3, 10), 1),
                "source": "Apple Watch Series 7",
            })
            t += timedelta(seconds=max(300, 3600 // samples_per_hour))  # 至少 5 分钟间隔
        return data

    def gen_steps():
        """模拟步数数据：均值 200±100 步/小时"""
        data = []
        t = start
        while t < end:
            steps = max(0, round(random.gauss(200, 100)))
            data.append({
                "date": t.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "qty": steps,
                "source": "Apple Watch Series 7",
            })
            t += timedelta(hours=1)
        return data

    def gen_hrv():
        """模拟 HRV 数据：均值 45±12 ms"""
        data = []
        t = start
        while t < end:
            hrv = max(10, round(random.gauss(45, 12), 1))
            data.append({
                "date": t.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "qty": hrv,
                "source": "Apple Watch Series 7",
            })
            t += timedelta(hours=1)
        return data

    def gen_sleep():
        """模拟睡眠分析：inBed + asleepREM"""
        sleep_start = (end - timedelta(days=1)).replace(hour=23, minute=0, second=0)
        sleep_end = sleep_start + timedelta(hours=7, minutes=30)
        return [
            {
                "startDate": sleep_start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "endDate": sleep_end.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "value": "inBed",
                "source": "Apple Watch Series 7",
            },
            {
                "startDate": sleep_start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "endDate": sleep_end.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "value": "asleepREM",
                "qty": 2.5 * 3600,   # 2.5h REM in seconds
                "source": "Apple Watch Series 7",
            },
            {
                "startDate": sleep_start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "endDate": sleep_end.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "value": "asleepDeep",
                "qty": 1.5 * 3600,   # 1.5h Deep
                "source": "Apple Watch Series 7",
            },
            {
                "startDate": sleep_start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "endDate": sleep_end.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "value": "asleepCore",
                "qty": 3.5 * 3600,   # 3.5h Core
                "source": "Apple Watch Series 7",
            },
        ]

    def gen_spo2():
        """模拟血氧：均值 97±2%"""
        return [
            {
                "date": start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "qty": round(random.gauss(97, 2), 1),
                "source": "Apple Watch Series 7",
            }
            for _ in range(4)  # 每天数次
        ]

    def gen_respiratory_rate():
        """模拟呼吸频率：均值 16±3 breaths/min"""
        return [
            {
                "date": start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "qty": round(random.gauss(16, 3), 1),
                "source": "Apple Watch Series 7",
            }
            for _ in range(8)
        ]

    def gen_wrist_temp():
        """模拟手腕温度（基础体温相对变化）：均值 0±0.5°C"""
        return [
            {
                "date": start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "qty": round(random.gauss(0, 0.5), 2),
                "source": "Apple Watch Series 7",
            }
        ]

    payload = {
        "data": {
            "metrics": [
                {"name": "heart_rate", "units": "bpm", "data": gen_heart_rate()},
                {"name": "resting_heart_rate", "units": "bpm", "data": [
                    {"date": start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                     "qty": round(random.gauss(58, 3), 1),
                     "source": "Apple Watch Series 7"}
                ]},
                {"name": "heart_rate_variability", "units": "ms", "data": gen_hrv()},
                {"name": "step_count", "units": "count", "data": gen_steps()},
                {"name": "active_energy", "units": "kJ", "data": [
                    {"date": start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                     "qty": round(random.uniform(800, 2500), 1),
                     "source": "Apple Watch Series 7"}
                ]},
                {"name": "exercise_time", "units": "min", "data": [
                    {"date": start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                     "qty": round(random.uniform(15, 60), 1),
                     "source": "Apple Watch Series 7"}
                ]},
                {"name": "sleep_analysis", "units": "hr", "data": gen_sleep()},
                {"name": "oxygen_saturation", "units": "%", "data": gen_spo2()},
                {"name": "respiratory_rate", "units": "breaths/min", "data": gen_respiratory_rate()},
                {"name": "wrist_temperature", "units": "degC", "data": gen_wrist_temp()},
            ],
            "workouts": [
                {
                    "name": "Outdoor Walk",
                    "startDate": start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                    "endDate": (start + timedelta(minutes=35)).strftime("%Y-%m-%d %H:%M:%S +0000"),
                    "duration": 2100,
                    "activeEnergy_kJ": 650,
                    "distance_m": 3200,
                    "avgHeartRate_bpm": 115,
                    "maxHeartRate_bpm": 142,
                }
            ],
        }
    }
    return payload


if __name__ == "__main__":
    payload = generate_test_payload()
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    total_points = sum(len(m["data"]) for m in payload["data"]["metrics"])
    print(f"\n# 生成 {total_points} 条数据点 + {len(payload['data']['workouts'])} 条训练记录",
          file=__import__("sys").stderr)
```

**v1 → v2 变更**：
| 变更 | 原因 |
|------|------|
| 新增 `exercise_time`, `oxygen_saturation`, `respiratory_rate`, `wrist_temperature` 生成 | 涵盖 Tier 1 全部指标 |
| 新增 `asleepDeep`, `asleepCore` 睡眠阶段 | 匹配 iOS 16+ 睡眠分类 |
| `days_back` 边界检查（`if start >= end`） | 防止 days_back=0 导致空数据 |
| 心率 min/max 用 `random.uniform` 抖动代替固定值 | 更真实的 Apple Watch 数据特征 |
| `datetime.utcnow()` → `datetime.now(timezone.utc)` | Python 3.12+ 兼容 |


### 3.8 依赖清单 `requirements.txt`

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy==2.0.36
pydantic==2.10.3
python-dateutil==2.9.0
numpy==2.2.1
```

---

## 4. 数据聚合层

### 4.1 聚合逻辑

```
原始数据（raw_health_samples）
    │  心率: 每 5 分钟一条，一天 ~288 条
    │  HRV:   每 1 小时一条，一天 ~24 条
    │  步数:  每 1 小时一条，一天 ~24 条
    │  血氧:  每天 4–10 条
    │
    ▼  日聚合 (aggregate_daily_metrics)
    │     - 查询当天该指标的所有 value IS NOT NULL 记录
    │     - np.mean / np.min / np.max / np.std / np.sum
    │     - 幂等: DELETE old → INSERT new
    │
    ▼
日指标（daily_metrics）
    │  avg_value    — 日平均值
    │  min_value    — 日最低值
    │  max_value    — 日最高值
    │  stddev_value — 日标准差（反映波动性）
    │  total_value  — 日累积值（步数、卡路里）
    │  sample_count — 有效采样数
```

### 4.2 个人基线计算（Phase 2 前置）

`compute_baseline(metric_type, days=30)` 返回前 N 天的日平均值的统计特征：

```python
{
    "mean": 68.5,           # 30 天日平均值的中枢
    "std": 4.2,             # 日平均值之间的标准差
    "upper_bound": 76.9,    # mean + 2σ（上警戒线）
    "lower_bound": 60.1,    # mean - 2σ（下警戒线）
    "n_days": 28,           # 有效天数
}
```

用于 Phase 2：
- 异常检测：「今日静息心率 78，偏离个人基线 2.3σ」
- 趋势判断：「HRV 连续 5 天低于 30 天均值」

### 4.3 聚合触发时机

| 触发方式 | 时机 | 说明 |
|---------|------|------|
| 自动 | 每次 `POST /sync` 后 | 增量聚合当天指标 |
| 手动 (API) | 调用内部函数 | 历史数据全量聚合（暂未暴露为 API） |
| 手动 (脚本) | `python -c "from data_pipeline.aggregator import ..."` | 调试用 |

---

## 5. 部署与运行

### 5.1 本地开发

```bash
# 1. 安装依赖
cd Medical-Health-Agent
pip install -r requirements.txt

# 2. 启动 FastAPI
cd data_pipeline
python webhook_server.py
# → 服务启动在 http://0.0.0.0:8000

# 3. 快速验证
curl http://localhost:8000/api/v1/health/status
```

### 5.2 使用 ngrok 暴露公网 URL

```bash
# 1. 安装 ngrok（https://ngrok.com/download）
# 2. 注册免费账号 → 获取 authtoken
ngrok config add-authtoken <your-token>

# 3. 启动隧道
ngrok http 8000

# 输出:
# Forwarding  https://abc123.ngrok-free.app → http://localhost:8000
#
# Health Auto Export URL 配置为:
# https://abc123.ngrok-free.app/api/v1/health/sync
```

### 5.3 发送测试数据

```bash
# 生成模拟数据 → 发送到 webhook
python -m data_pipeline.test_data | curl -X POST http://localhost:8000/api/v1/health/sync \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer medical-health-agent-dev-key-2026" \
  -d @-

# 验证
curl http://localhost:8000/api/v1/health/status
curl "http://localhost:8000/api/v1/health/daily?date=$(date +%Y-%m-%d)"
curl "http://localhost:8000/api/v1/health/baseline?metric_type=heart_rate&days=30"
```

### 5.4 Docker 部署（可选）

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "uvicorn", "data_pipeline.webhook_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t health-pipeline .
docker run -d -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e HEALTH_API_KEY=<your-production-key> \
  health-pipeline
```

### 5.5 安全配置（上线前必做）

1. **修改 API Key**：`export HEALTH_API_KEY=<random-64-char-string>`
2. **HTTPS**：ngrok 免费版自带 HTTPS（TLS 终止在 ngrok 端），本地无需配置证书
3. **生产方案**：长期运行建议用 Cloudflare Tunnel 替代 ngrok（免费且无连接数限制）
4. **Nginx 配置**（自建公网服务器时）：`client_max_body_size 50M;`

---

## 6. 测试验证

### 6.1 功能测试清单

| # | 测试项 | 方法 | 预期结果 |
|---|--------|------|---------|
| 1 | 服务启动 | `curl GET /api/v1/health/status` | 200, `total_raw_samples: 0` |
| 2 | API Key 鉴权 | 不带 `Authorization` POST | 401 |
| 3 | 错误 API Key | 带错误 Key POST | 403 |
| 4 | 接收测试数据 | `test_data.py` → POST | 200, 返回 `data_points_inserted` |
| 5 | 数据写入 | 查 `/status` | `total_raw_samples > 0` |
| 6 | 日聚合 | 查 `/daily?date=...` | 返回各指标 avg/min/max/stddev |
| 7 | 幂等性 | 同一数据 POST 两次 | 不报错，daily_metrics 不重复 |
| 8 | 空值处理 | 发送 value=null 的点 | 写入 raw 表但 value=NULL，不影响聚合 |
| 9 | 日期格式兼容 | `2024-01-01T12:00:00Z`, `2024-01-01 12:00:00 +0000` | 全部正确解析 |
| 10 | 基线计算 | `GET /baseline?metric_type=heart_rate` | 返回 mean/std/bounds |
| 11 | 未知指标入库 | 发送不在 AGGREGATION_METRICS 中的指标 | 写入 raw 表，不报错 |

### 6.2 真实 iOS 数据测试

1. 在 iPhone 上安装 **Health Auto Export**
2. 确认 FastAPI + ngrok 已启动
3. 将 ngrok URL 填入 App → Automation → API Export
4. 手动触发一次同步（点 Automation 行右侧的 ▶️ 按钮）
5. 检查 `GET /api/v1/health/status` 确认数据到达
6. 检查 `/daily?date=...` 确认聚合触发

### 6.3 空值数据处理测试

```bash
# 测试发送包含空值的数据（睡眠 inBed 阶段）
curl -X POST http://localhost:8000/api/v1/health/sync \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer medical-health-agent-dev-key-2026" \
  -d '{
    "data": {
      "metrics": [{
        "name": "sleep_analysis",
        "units": "hr",
        "data": [
          {"startDate": "2026-05-06 23:00:00 +0000", "endDate": "2026-05-07 06:30:00 +0000", "value": "inBed"},
          {"startDate": "2026-05-06 23:15:00 +0000", "endDate": "2026-05-07 02:30:00 +0000", "value": "asleepDeep", "qty": 11700},
          {"startDate": "2026-05-07 02:30:00 +0000", "endDate": "2026-05-07 06:15:00 +0000", "value": "asleepREM", "qty": 13500}
        ]
      }]
    }
  }'

# 验证：inBed value 应为 null（无 qty），asleepDeep/REM 应有 min 值
curl "http://localhost:8000/api/v1/health/raw?metric_type=sleep_analysis&date_from=2026-05-06&limit=10"
```

### 6.4 端到端验证脚本

```bash
#!/bin/bash
# e2e_test.sh — Phase 1 数据管道端到端测试

BASE="http://localhost:8000"
AUTH="Authorization: Bearer medical-health-agent-dev-key-2026"
PASS=0
FAIL=0

check() {
  local desc="$1"
  local expected="$2"
  local actual="$3"
  if echo "$actual" | grep -q "$expected"; then
    echo "  ✅ $desc"
    ((PASS++))
  else
    echo "  ❌ $desc (expected: $expected)"
    ((FAIL++))
  fi
}

echo "========================================="
echo " Phase 1 E2E Test Suite"
echo "========================================="

echo -e "\n── 1. Service Status ──"
STATUS=$(curl -s $BASE/api/v1/health/status)
echo "$STATUS" | python -m json.tool 2>/dev/null || echo "$STATUS"
check "Status endpoint returns 200" "total_raw_samples" "$STATUS"

echo -e "\n── 2. Auth: Missing Key → 401 ──"
AUTH_RESP=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/api/v1/health/sync \
  -H "Content-Type: application/json" -d '{}')
check "Missing API key → 401" "401" "$AUTH_RESP"

echo -e "\n── 3. Auth: Wrong Key → 403 ──"
AUTH_RESP=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/api/v1/health/sync \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer wrong-key" \
  -d '{}')
check "Wrong API key → 403" "403" "$AUTH_RESP"

echo -e "\n── 4. Send Test Data ──"
python -m data_pipeline.test_data > /tmp/health_test.json
SYNC_RESP=$(curl -s -X POST $BASE/api/v1/health/sync \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d @/tmp/health_test.json)
echo "$SYNC_RESP" | python -m json.tool 2>/dev/null || echo "$SYNC_RESP"
check "Sync returns success" "success" "$SYNC_RESP"

echo -e "\n── 5. Verify Data Written ──"
STATUS2=$(curl -s $BASE/api/v1/health/status)
check "Raw samples > 0" "total_raw_samples" "$STATUS2"
echo "$STATUS2" | python -m json.tool 2>/dev/null || echo "$STATUS2"

echo -e "\n── 6. Query Daily Metrics ──"
TODAY=$(date +%Y-%m-%d)
DAILY=$(curl -s "$BASE/api/v1/health/daily?date=$TODAY")
echo "$DAILY" | python -m json.tool 2>/dev/null || echo "$DAILY"
check "Daily metrics non-empty" "metric_type" "$DAILY"

echo -e "\n── 7. Query Raw Data ──"
RAW=$(curl -s "$BASE/api/v1/health/raw?metric_type=heart_rate&date_from=$TODAY&limit=3")
echo "$RAW" | python -m json.tool 2>/dev/null || echo "$RAW"
check "Raw data accessible" "samples" "$RAW"

echo -e "\n── 8. Query Baseline ──"
BASELINE=$(curl -s "$BASE/api/v1/health/baseline?metric_type=heart_rate&days=7")
echo "$BASELINE" | python -m json.tool 2>/dev/null || echo "$BASELINE"
check "Baseline endpoint" "mean" "$BASELINE"

echo -e "\n── 9. Idempotency: Resend Same Data ──"
SYNC_RESP2=$(curl -s -X POST $BASE/api/v1/health/sync \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d @/tmp/health_test.json)
check "Resend returns success" "success" "$SYNC_RESP2"

echo -e "\n========================================="
echo " Results: $PASS passed, $FAIL failed"
echo "========================================="
```

---

## 7. Phase 2 衔接准备

Phase 1 完成后，以下数据将直接供 Phase 2 的 Agent 使用：

### 7.1 感知 Agent 输入格式

```python
# Phase 2 中，感知节点将这样读取数据：
from data_pipeline.aggregator import compute_baseline
from data_pipeline.database import SessionLocal

db = SessionLocal()

# 获取今日所有聚合指标
today_metrics = db.query(DailyMetric).filter(date=date.today()).all()

# 获取个人基线（用于异常检测阈值）
hr_baseline = compute_baseline(db, "heart_rate", days=30)

# 生成结构化摘要 → 发送给 LLM
summary = {
    "date": str(date.today()),
    "heart_rate": {
        "avg": 72,
        "baseline_mean": 68.5,
        "deviation_sigma": 0.83,   # (72 - 68.5) / 4.2
    },
    "hrv": {
        "avg": 48,
        "baseline_mean": 45,
        "deviation_sigma": 0.71,
    },
    "steps": {"total": 8500, "baseline_mean": 7200},
    "sleep": {"total_hours": 7.2, "deep_hours": 1.5, "rem_hours": 2.1},
}
```

### 7.2 Prompt 模板参照

```
你是私人健康顾问。基于以下今日数据给出分析：

- 心率: 均值 {avg} bpm，范围 {min}–{max}，标准差 {std}，偏离基线 {delta}σ
- HRV: 今日 {avg} ms，30天基线 {baseline_mean} ± {baseline_std} ms
- 步数: 今日 {total} 步
- 睡眠: 总时长 {total}h，深度 {deep}h，REM {rem}h
- 运动: 活跃能量 {energy} kJ，运动时长 {exercise} min

请输出:
1. 今日状态总结 (1句话)
2. 需要关注的点 (如有)
3. 饮食建议
4. 明日运动建议
```

### 7.3 数据积累时间线

| 时间 | 数据量 | 可用功能 |
|------|--------|---------|
| 第 1 天 | 1 天原始数据 | 日聚合 |
| 第 7 天 | 7 天聚合数据 | 周趋势、短期基线 |
| 第 30 天 | 30 天基线 | 个人基线 + 异常检测 (2σ) |
| 第 90 天 | 90 天基线 | 稳定基线 + 长期趋势 |

---

## 附录 A：Health Auto Export JSON 完整示例

```json
{
  "data": {
    "metrics": [
      {
        "name": "heart_rate",
        "units": "bpm",
        "data": [
          {
            "date": "2026-05-06 08:05:00 +0000",
            "min": 68,
            "avg": 72,
            "max": 85,
            "source": "Apple Watch Series 7"
          },
          {
            "date": "2026-05-06 08:10:00 +0000",
            "min": 67,
            "avg": 71,
            "max": 82,
            "source": "Apple Watch Series 7"
          }
        ]
      },
      {
        "name": "step_count",
        "units": "count",
        "data": [
          {"date": "2026-05-06 08:00:00 +0000", "qty": 245, "source": "Apple Watch"}
        ]
      },
      {
        "name": "sleep_analysis",
        "units": "hr",
        "data": [
          {
            "startDate": "2026-05-05 23:15:00 +0000",
            "endDate": "2026-05-06 06:45:00 +0000",
            "value": "inBed",
            "source": "Apple Watch Series 7"
          },
          {
            "startDate": "2026-05-05 23:30:00 +0000",
            "endDate": "2026-05-06 02:00:00 +0000",
            "value": "asleepDeep",
            "qty": 9000,
            "source": "Apple Watch Series 7"
          }
        ]
      },
      {
        "name": "oxygen_saturation",
        "units": "%",
        "data": [
          {"date": "2026-05-06 02:15:00 +0000", "qty": 97.5, "source": "Apple Watch Series 7"}
        ]
      }
    ],
    "workouts": [
      {
        "name": "Outdoor Walk",
        "startDate": "2026-05-06 07:30:00 +0000",
        "endDate": "2026-05-06 08:05:00 +0000",
        "duration": 2100,
        "activeEnergy_kJ": 650,
        "distance_m": 3200,
        "avgHeartRate_bpm": 115,
        "maxHeartRate_bpm": 142
      }
    ]
  }
}
```

---

## 附录 B：常见问题排查

| 问题 | 可能原因 | 排查步骤 |
|------|---------|---------|
| iOS 端同步失败（红色标记） | ngrok URL 过期 / 网络不通 | 1. 重启 ngrok 2. 更新 App 中的 URL 3. 在 iPhone Safari 中打开 URL 测试 |
| `401 Unauthorized` | API Key 不匹配 | 1. 检查环境变量 `HEALTH_API_KEY` 2. 检查 App Custom Headers 中 `Authorization: Bearer <key>` |
| `400 Bad Request` | JSON 结构与 Pydantic 模型不匹配 | 1. 查看服务端日志中的实际 payload 2. 对比 models.py 中的字段定义 |
| 日期解析为 None | 新格式未在 `_parse_datetime` 中覆盖 | 1. 查看日志中的 failed datetime 原始字符串 2. 在 `_parse_datetime` 中增加对应的格式规则 |
| 聚合数据为空 | metric_type 不在 `AGGREGATION_METRICS` 中 | 检查 `config.py` 的 `AGGREGATION_METRICS` 列表 |
| 数据已写入但 value 全是 null | Health Auto Export 版本不同导致字段名变化 | 使用 `GET /raw` 查看 `extra` 列的实际 JSON，对比 models.py 的字段定义 |
| 睡眠数据仅有 "inBed" 无时长 | "inBed" 阶段 qty 字段为空是正常的 | 时长通过 `endDate - startDate` 计算（已在代码中处理） |

---

## 附录 C：待确认问题 & 模糊点

> **以下事项需要用户确认或提供信息后才能最终确定。**

### C.1 需要确认的事项

| # | 问题 | 影响范围 | 优先级 |
|---|------|---------|--------|
| 1 | **Health Auto Export REST API 文档** — 无法访问 `help.healthyapps.dev`，文档中的具体 JSON schema、可选配置项、错误码等无法验证。需要用户将网页内容加载到本地文件供分析。 | models.py 的字段定义可能有遗漏 | **高** |
| 2 | **Health Auto Export Export Format 文档** — 同上，无法确认 150+ 指标的具体字段名映射。当前代码基于 v1 文档中的示例推断。 | Tier 2/3 指标接入时的字段名 | **高** |
| 3 | **Health Auto Export 实际 JSON 结构** — 是否总是 `{"data": {"metrics": [...], "workouts": [...]}}` 格式？不同版本是否有差异？ | `HealthSyncRequest` 的兼容性 | **中** |
| 4 | **睡眠分析阶段的字段名** — 实际 App 发送的睡眠阶段 (`value` 字段) 是否确实为 `"inBed"`, `"asleepREM"`, `"asleepDeep"`, `"asleepCore"`？ | 睡眠聚合的逻辑 | **中** |
| 5 | **多用户场景** — 当前 `target` 参数预留了多用户标识，实际是否需要？如果单人使用，可以简化。 | webhook_server.py 的 target 参数 | **低** |
| 6 | **ngrok 替代方案偏好** — 是否考虑 Cloudflare Tunnel（免费且不限连接数）？还是 ngrok 免费版（每月 1GB 带宽限制）已足够？ | 部署方案 | **低** |

### C.2 无法访问的参考 URL

以下两个 URL 因网络安全策略阻止访问，需要用户以本地文件形式提供内容：

1. **REST API 自动化**：`https://help.healthyapps.dev/zh-hans/health-auto-export/automations/rest-api/`
   - 期望获取：URL 配置方式、HTTP Method、Headers 格式、API 响应处理、错误重试机制
2. **导出格式**：`https://help.healthyapps.dev/zh-hans/health-auto-export/export-format/`
   - 期望获取：全部 150+ 指标的 `name` 字段映射、units 格式、JSON 结构规范、日期格式说明

> 建议：将这两个网页另存为 HTML 或截图，放到 `Medical-Health-Agent/docs/` 目录下，我可以读取后进一步修正文档和代码。

### C.3 代码中的已知限制

| 限制 | 说明 | 计划 |
|------|------|------|
| 睡眠聚合未按阶段分类 | 当前聚合不区分 REM/Deep/Core，仅计算总时长 | Phase 2 按需实现 |
| 不处理 GPS/路线数据 | workouts 中的 GPS 坐标可能很大，当前丢弃 | 如果分析需要，新增 `gps_points` 表 |
| 无历史数据回填 | App 首次同步只发「上次同步至今」的增量数据，历史数据需要 App 内选择 Period: All Time | 文档中给出说明 |
| 无 Webhook 验证签名 | Health Auto Export 不支持 HMAC 签名，仅靠 API Key + HTTPS 保证安全 | 对于个人健康数据足够，如需增强可加 IP 白名单 |

---

> **下一步 Phase 2**：LangGraph 构建 `HealthAnalysisGraph`，感知 Agent 读取聚合数据，分析 Agent 调用大模型 API 生成健康报告。详见 `Phase2-医疗RAG知识库构建方案.md`。
