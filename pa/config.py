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
