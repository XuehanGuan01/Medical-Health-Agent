"""模拟 Health Auto Export 发送的测试数据"""
import json
import random
from datetime import datetime, timedelta


def generate_test_payload(days_back: int = 1, samples_per_hour: int = 12) -> dict:
    now = datetime.utcnow()
    start = now - timedelta(days=max(days_back, 1))
    end = now

    def gen_heart_rate():
        data = []
        t = start
        while t < end:
            hr = round(random.gauss(72, 8), 1)
            ts = t.strftime("%Y-%m-%d %H:%M:%S +0000")
            data.append({
                "date": ts,
                "min": round(hr - 5, 1),
                "avg": hr,
                "max": round(hr + 8, 1),
                "source": "Apple Watch Series 7",
            })
            t += timedelta(seconds=3600 // samples_per_hour)
        return data

    def gen_steps():
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
        sleep_start = (now - timedelta(days=days_back)).replace(hour=23, minute=0, second=0)
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
                "qty": 2.5 * 3600,
                "source": "Apple Watch Series 7",
            },
        ]

    payload = {
        "data": {
            "metrics": [
                {"name": "heart_rate", "units": "bpm", "data": gen_heart_rate()},
                {"name": "resting_heart_rate", "units": "bpm", "data": [
                    {"date": start.strftime("%Y-%m-%d %H:%M:%S +0000"), "qty": round(random.gauss(58, 3), 1)}
                ]},
                {"name": "heart_rate_variability", "units": "ms", "data": gen_hrv()},
                {"name": "step_count", "units": "count", "data": gen_steps()},
                {"name": "sleep_analysis", "units": "minutes", "data": gen_sleep()},
                {"name": "active_energy", "units": "kJ", "data": [
                    {"date": start.strftime("%Y-%m-%d %H:%M:%S +0000"), "qty": round(random.uniform(800, 2500), 1)}
                ]},
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
    print(f"\n生成 {total_points} 条数据点 + 1 条训练记录")
