"""全局配置中心"""
import os

# ── 数据库 ──────────────────────────────────────────────
DATABASE_URL = os.getenv("HEALTH_DB_URL", "sqlite:///data/health.db")

# ── API 鉴权 ────────────────────────────────────────────
API_KEY = os.getenv("HEALTH_API_KEY", "medical-health-agent-dev-key-2026")

# ── 服务配置 ────────────────────────────────────────────
HOST = os.getenv("HEALTH_HOST", "0.0.0.0")
PORT = int(os.getenv("HEALTH_PORT", "8000"))

# ── 聚合配置 (全部 39 种 iOS 指标) ──────────────────────
AGGREGATION_METRICS = [
    # 心脏 (4)
    "heart_rate",
    "resting_heart_rate",
    "heart_rate_variability",
    "walking_heart_rate_average",
    "cardio_recovery",
    # 活动 (10)
    "step_count",
    "active_energy",
    "basal_energy_burned",
    "apple_exercise_time",
    "apple_stand_time",
    "apple_stand_hour",
    "walking_running_distance",
    "flights_climbed",
    "physical_effort",
    "vo2_max",
    # 步行 (5)
    "walking_speed",
    "walking_step_length",
    "walking_asymmetry_percentage",
    "walking_double_support_percentage",
    "six_minute_walking_test_distance",
    # 楼梯 (2)
    "stair_speed_down",
    "stair_speed_up",
    # 跑步 (4)
    "running_power",
    "running_speed",
    "running_ground_contact_time",
    "running_vertical_oscillation",
    "running_stride_length",
    # 骑行 (1)
    "cycling_distance",
    # 呼吸 (1)
    "respiratory_rate",
    # 睡眠 (1)
    "sleep_analysis",
    # 身体 (4)
    "weight_body_mass",
    "body_fat_percentage",
    "body_mass_index",
    "height",
    # 环境 (3)
    "environmental_audio_exposure",
    "headphone_audio_exposure",
    "time_in_daylight",
    # 正念 (1)
    "mindful_minutes",
    # 其他 (2)
    "handwashing",
    "blood_oxygen_saturation",
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

# ── 手动上传 JSON 存档目录 ──────────────────────────────
WEEKLY_RAW_DIR = os.getenv("WEEKLY_RAW_DIR", "data/weekly_raw")

# ── 上传文件大小限制 ────────────────────────────────────
MAX_UPLOAD_SIZE_MB = 5  # 单周约76KB，全年~4MB，上限5MB
