"""全局配置中心"""
import os

# ── 数据库 ──────────────────────────────────────────────
DATABASE_URL = os.getenv("HEALTH_DB_URL", "sqlite:///data/health.db")

# ── API 鉴权 ────────────────────────────────────────────
API_KEY = os.getenv("HEALTH_API_KEY", "medical-health-agent-dev-key-2026")

# ── 服务配置 ────────────────────────────────────────────
HOST = os.getenv("HEALTH_HOST", "0.0.0.0")
PORT = int(os.getenv("HEALTH_PORT", "8000"))

# ── 聚合配置 ────────────────────────────────────────────
AGGREGATION_METRICS = [
    # 心脏
    "heart_rate",
    "resting_heart_rate",
    "heart_rate_variability",
    # 活动
    "step_count",
    "active_energy",
    "basal_energy_burned",
    "apple_exercise_time",
    "apple_stand_time",
    "walking_running_distance",
    "flights_climbed",
    # 步行
    "walking_speed",
    "walking_step_length",
    "walking_asymmetry_percentage",
    "walking_double_support_percentage",
    # 身体
    "physical_effort",
    # 呼吸
    "respiratory_rate",
    "blood_oxygen_saturation",
    # 其他
    "wrist_temperature",
]

# 睡眠阶段枚举（官方文档确认，首字母大写）
SLEEP_STAGES = [
    "In Bed",
    "Asleep",
    "Awake",
    "Core",
    "REM",
    "Deep",
    "Unspecified",
]

# Health Auto Export JSON 顶层包裹键名
WRAPPER_KEY = "data"
