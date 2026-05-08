"""全局配置"""
import os

DATABASE_URL = os.getenv("HEALTH_DB_URL", "sqlite:///data/health.db")
API_KEY = os.getenv("HEALTH_API_KEY", "medical-health-agent-dev-key-2026")

AGGREGATION_METRICS = [
    "heart_rate",
    "resting_heart_rate",
    "heart_rate_variability",
    "step_count",
    "active_energy",
    "oxygen_saturation",
    "respiratory_rate",
]

WRAPPER_KEY = "data"
