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
    """{'plan': 분, 'deadline': [분, …]} — 숫자 하나나 목록 모두 받는다."""
    r = load_timetable().get("reminders") or {}
    dl = r.get("deadline_minutes_before", [])
    return {"plan": int(r.get("plan_minutes_before", 0)),
            "deadline": [int(x) for x in (dl if isinstance(dl, list) else [dl]) if int(x) > 0]}


def popup(minutes):
    """Google Calendar 일정 알림 설정. minutes: 분 또는 분 목록 (최대 5개, 0 이하는 무시)."""
    ms = sorted({m for m in (minutes if isinstance(minutes, (list, tuple)) else [minutes]) if m > 0}, reverse=True)[:5]
    return {"useDefault": False, "overrides": [{"method": "popup", "minutes": m} for m in ms]}
