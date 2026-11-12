"""공용 자료형과 날짜·표시 도우미."""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
WEEKDAY = "월화수목금토일"
KIND_LABEL = {"lecture": "강의", "quiz": "퀴즈", "assignment": "과제", "todo": "할 일", "review": "퀴즈 복습"}


@dataclass
class Task:
    key: str
    kind: str  # lecture | quiz | assignment | todo | review(퀴즈 앱 복습)
    course: str
    title: str
    due: datetime | None
    minutes: int
    url: str = ""
    earliest: datetime | None = None  # 이 시각 이전에는 배치하지 않음 (반복 할 일)
    source: str = "canvas"  # canvas | inbox | quiz
    status: str = "open"  # open | done | ignored | gone


def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(KST) if s else None


def now():
    return datetime.now(KST).replace(second=0, microsecond=0)


def kday(dt):
    return f"{dt:%m/%d}({WEEKDAY[dt.weekday()]})"


def short_course(name):
    return re.sub(r"\s*\d{6}$", "", name or "")


def label(t):
    return f"{short_course(t.course)} · {t.title}" if t.course else t.title


def fmt(t):
    due = f"{kday(t.due)} {t.due:%H:%M}" if t.due else "기한 없음   "
    return f"{t.key:>24}  {due}  [{KIND_LABEL[t.kind]}] {label(t)}  ({t.minutes}분)"
