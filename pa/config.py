"""프로젝트 설정 로딩 (.env, config/*.yaml)."""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_timetable():
    return yaml.safe_load((ROOT / "config" / "timetable.yaml").read_text())


def reminders():
    r = load_timetable().get("reminders") or {}
    return {"plan": int(r.get("plan_minutes_before", 0)), "deadline": int(r.get("deadline_minutes_before", 0))}


def popup(minutes):
    """Google Calendar 일정 알림 설정 (0 이하면 알림 없음)."""
    return {"useDefault": False, "overrides": [{"method": "popup", "minutes": minutes}] if minutes > 0 else []}
