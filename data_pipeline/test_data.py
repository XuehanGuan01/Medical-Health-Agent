"""
模拟 Health Auto Export 的测试数据生成器。

用法:
  python -m data_pipeline.test_data

  # 直接发送到 webhook
  python -m data_pipeline.test_data | curl -X POST http://localhost:8000/api/v1/health/sync \\
    -H "Content-Type: application/json" \\
    -H "Authorization: Bearer medical-health-agent-dev-key-2026" \\
    -d @-
"""
import json
import random
from datetime import datetime, timedelta, timezone


def generate_test_payload(days_back: int = 1, samples_per_hour: int = 12) -> dict:
    """
    生成模拟 Health Auto Export JSON（V2 格式）。

    参数:
        days_back: 模拟多少天前的数据（1 = 最近 24 小时）
        samples_per_hour: 心率类型每小时采样点数（默认 12 = 每 5 分钟）
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(days_back, 1))
    end = now

    def gen_heart_rate():
        """心率: 均值 72±8 bpm，官方格式用 Min/Avg/Max（首字母大写）"""
        data = []
        t = start
        while t < end:
            hr = round(random.gauss(72, 8), 1)
            data.append({
                "date": t.strftime("%Y-%m-%d %H:%M:%S +0000"),
                "Min": round(hr - random.uniform(2, 6), 1),
                "Avg": hr,
                "Max": round(hr + random.uniform(3, 10), 1),
                "source": "Apple Watch Series 7",
            })
            t += timedelta(seconds=max(300, 3600 // samples_per_hour))
        return data

    def gen_steps():
        """步数: 均值 200±100 步/小时"""
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
        """HRV: 均值 45±12 ms"""
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
        """睡眠: 官方阶段标签（首字母大写）Core / REM / Deep / In Bed / Awake"""
        sleep_start = (now - timedelta(days=days_back)).replace(hour=23, minute=0, second=0)
        sleep_end = sleep_start + timedelta(hours=7, minutes=30)
        ts_fmt = "%Y-%m-%d %H:%M:%S +0000"
        return [
            {
                "startDate": sleep_start.strftime(ts_fmt),
                "endDate": sleep_end.strftime(ts_fmt),
                "value": "In Bed",
                "source": "Apple Watch Series 7",
            },
            {
                "startDate": sleep_start.strftime(ts_fmt),
                "endDate": (sleep_start + timedelta(hours=1, minutes=30)).strftime(ts_fmt),
                "qty": 1.5 * 3600,
                "value": "Deep",
                "source": "Apple Watch Series 7",
            },
            {
                "startDate": (sleep_start + timedelta(hours=1, minutes=30)).strftime(ts_fmt),
                "endDate": (sleep_start + timedelta(hours=3, minutes=45)).strftime(ts_fmt),
                "qty": 2.25 * 3600,
                "value": "REM",
                "source": "Apple Watch Series 7",
            },
            {
                "startDate": (sleep_start + timedelta(hours=3, minutes=45)).strftime(ts_fmt),
                "endDate": sleep_end.strftime(ts_fmt),
                "qty": 3.75 * 3600,
                "value": "Core",
                "source": "Apple Watch Series 7",
            },
            {
                "startDate": sleep_start.strftime(ts_fmt),
                "endDate": sleep_end.strftime(ts_fmt),
                "value": "Awake",
                "qty": 0.25 * 3600,
                "source": "Apple Watch Series 7",
            },
        ]

    def gen_spo2():
        """血氧: 均值 97±2%"""
        return [
            {
                "date": (start + timedelta(hours=i * 6)).strftime("%Y-%m-%d %H:%M:%S +0000"),
                "qty": round(random.gauss(97, 2), 1),
                "source": "Apple Watch Series 7",
            }
            for i in range(4)
        ]

    def gen_respiratory_rate():
        """呼吸频率: 均值 16±3 breaths/min"""
        return [
            {
                "date": (start + timedelta(hours=i * 3)).strftime("%Y-%m-%d %H:%M:%S +0000"),
                "qty": round(random.gauss(16, 3), 1),
                "source": "Apple Watch Series 7",
            }
            for i in range(8)
        ]

    def gen_wrist_temp():
        """手腕温度: 均值 0±0.5°C（基础体温相对变化）"""
        return [
            {
                "date": (start + timedelta(hours=i * 6)).strftime("%Y-%m-%d %H:%M:%S +0000"),
                "qty": round(random.gauss(0, 0.5), 2),
                "source": "Apple Watch Series 7",
            }
            for i in range(4)
        ]

    payload = {
        "data": {
            "metrics": [
                {"name": "heart_rate", "units": "bpm", "data": gen_heart_rate()},
                {"name": "resting_heart_rate", "units": "bpm", "data": [
                    {
                        "date": start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                        "qty": round(random.gauss(58, 3), 1),
                        "source": "Apple Watch Series 7",
                    }
                ]},
                {"name": "heart_rate_variability", "units": "ms", "data": gen_hrv()},
                {"name": "step_count", "units": "count", "data": gen_steps()},
                {"name": "active_energy", "units": "kJ", "data": [
                    {
                        "date": start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                        "qty": round(random.uniform(800, 2500), 1),
                        "source": "Apple Watch Series 7",
                    }
                ]},
                {"name": "exercise_time", "units": "min", "data": [
                    {
                        "date": start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                        "qty": round(random.uniform(15, 60), 1),
                        "source": "Apple Watch Series 7",
                    }
                ]},
                {"name": "sleep_analysis", "units": "hr", "data": gen_sleep()},
                {"name": "blood_oxygen_saturation", "units": "%", "data": gen_spo2()},
                {"name": "respiratory_rate", "units": "breaths/min", "data": gen_respiratory_rate()},
                {"name": "wrist_temperature", "units": "degC", "data": gen_wrist_temp()},
            ],
            "workouts": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Outdoor Walk",
                    "start": start.strftime("%Y-%m-%d %H:%M:%S +0000"),
                    "end": (start + timedelta(minutes=35)).strftime("%Y-%m-%d %H:%M:%S +0000"),
                    "duration": 2100,
                    "activeEnergy_kJ": 650,
                    "distance_m": 3200,
                    "avgHeartRate_bpm": 115,
                    "maxHeartRate_bpm": 142,
                    "location": "Outdoor",
                }
            ],
        }
    }
    return payload


if __name__ == "__main__":
    payload = generate_test_payload()
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    total_points = sum(len(m["data"]) for m in payload["data"]["metrics"])
    print(
        f"\n# 生成 {total_points} 条数据点 + {len(payload['data']['workouts'])} 条训练记录",
        file=__import__("sys").stderr,
    )
