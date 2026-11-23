"""습관 블록 — 시각 없이 양만 정한 반복 (inbox.md 의 '## 습관'). 계획기가 마감 있는 일을 다 놓은 뒤 남은 빈 곳에,
정한 시간대 안에서 넣는다. 자리가 없으면(바쁘면) 그날은 건너뛴다. 하루 마무리도 습관 하나 (config/timetable.yaml daily_review).

  - 복습 ~1h 매일 저녁            매일, 18~23시 사이 빈 곳에 1시간
  - 운동 ~40m 주3회               이번 주에 3번 (한 날은 한 번)
  - 영어 단어 ~20m 매주:월,수,금 아침
  - 독서 ~30m 매일 21-23시        시간대를 직접
시간대: 아침 06-12 · 오후 12-18 · 저녁 18-23 · 'HH-HH시' · 없으면 계획 시간(day_start~day_end).
했으면 대시보드 블록의 [했음] → 그날(주N회면 그 주 한 번) 은 끝. 계획 키 'h:<이름>@<날짜>'.
"""
import json
import re
from dataclasses import replace
from datetime import datetime, time, timedelta

from pa import db
from pa.config import load_timetable
from pa.model import KST, Task, now

WINDOWS = {"아침": (6, 12), "오전": (6, 12), "오후": (12, 18), "저녁": (18, 23), "밤": (21, 24)}
DAYS = "월화수목금토일"
REVIEW = "하루 마무리"


def parse(text):
    """'복습 ~1h 매일 저녁' → {title, minutes, every, per_week, days, window}. 모르는 줄은 ValueError."""
    t = text
    m = re.search(r"~(\d+(?:\.\d+)?)\s*(h|m|시간|분)", t)
    if not m:
        raise ValueError(f"습관에 길이(~1h · ~30m)가 없음: {text}")
    minutes = int(float(m[1]) * 60 if m[2] in ("h", "시간") else float(m[1]))
    t = t.replace(m[0], " ")
    every, per_week, days = "daily", None, None
    if m := re.search(r"주\s*(\d)\s*회", t):
        every, per_week = "weekly", int(m[1])
        t = t.replace(m[0], " ")
    elif m := re.search(r"매주\s*[:：]\s*([월화수목금토일,\s]+)", t):
        every, days = "days", sorted({DAYS.index(d) for d in m[1] if d in DAYS})
        t = t.replace(m[0], " ")
    elif "매일" in t:
        t = t.replace("매일", " ")
    window = None
    if m := re.search(r"(\d{1,2})(?::(\d\d))?\s*[-~]\s*(\d{1,2})(?::(\d\d))?\s*시?", t):
        window = (int(m[1]) * 60 + int(m[2] or 0), int(m[3]) * 60 + int(m[4] or 0))
        t = t.replace(m[0], " ")
    else:
        for w, (a, b) in WINDOWS.items():
            if re.search(rf"(^|\s){w}(\s|$)", t):
                window = (a * 60, b * 60)
                t = re.sub(rf"(^|\s){w}(\s|$)", " ", t)
                break
    title = " ".join(t.split())
    if not title:
        raise ValueError(f"습관 이름이 없음: {text}")
    if window and window[1] <= window[0]:
        raise ValueError(f"시간대가 이상함: {text}")
    return {"title": title, "minutes": minutes, "every": every, "per_week": per_week, "days": days, "window": window}


def load():
    """inbox 의 습관 + 하루 마무리. (습관 목록, 잘못된 줄 경고)"""
    from pa import inbox
    out, warns = [], []
    try:
        lines = inbox.read_sections().get("habit", [])
    except FileNotFoundError:
        lines = []
    for _, _, text in lines:
        try:
            out.append(parse(text))
        except ValueError as e:
            warns.append(str(e))
    r = {"enabled": True, "minutes": 15, "window": "21-23", **(load_timetable().get("daily_review") or {})}
    if r["enabled"] and not any(h["title"] == REVIEW for h in out):
        a, b = (int(x) for x in str(r["window"]).split("-"))
        out.append({"title": REVIEW, "minutes": int(r["minutes"]), "every": "daily", "per_week": None, "days": None,
                    "window": (a * 60, b * 60), "review": True})
    return out, warns


def done(conn, since):
    """{(이름, 날짜)} — [했음] 누른 것."""
    out = set()
    for r in conn.execute("SELECT detail FROM events WHERE type = 'habit_done' AND ts >= ?", (since.isoformat(),)):
        d = json.loads(r["detail"] or "{}")
        out.add((d.get("name"), d.get("day")))
    return out


def mark_done(conn, key):
    """계획 키 'h:<이름>@<날짜>' → 그날 했음."""
    m = re.match(r"h:(.+)@(\d{4}-\d\d-\d\d)", key)
    if not m:
        raise ValueError("습관 블록이 아님")
    db.log(conn, "habit_done", key, name=m[1], day=m[2])


def candidates(habits, cfg, t_now, done_set, days=7):
    """앞으로 days 일의 습관 후보 Task (그날 시간대 안, 이미 했거나 지난 것 빼고)."""
    ds, de = (int(x[:2]) * 60 + int(x[3:]) for x in (cfg["day_start"], cfg["day_end"]))
    out = []
    for h in habits:
        a, b = h["window"] or (ds, de)
        for k in range(days):
            d = (t_now + timedelta(days=k)).date()
            if h["every"] == "days" and d.weekday() not in h["days"]:
                continue
            if (h["title"], d.isoformat()) in done_set:
                continue
            start = datetime.combine(d, time(0), KST) + timedelta(minutes=a)
            end = datetime.combine(d, time(0), KST) + timedelta(minutes=min(b, 24 * 60))
            if end - timedelta(minutes=h["minutes"]) <= t_now:
                continue
            out.append((h, Task(key=f"h:{h['title']}@{d.isoformat()}", kind="todo", course="", title=f"🔁 {h['title']}",
                                due=end, minutes=h["minutes"], earliest=max(start, t_now))))
    return out


def plan(conn, busy, cfg, t_now, main_plan):
    """습관 블록 [(할 일, 시작, 끝)], 이유 {키: 문장}. 이미 놓은 계획은 피하고, 하루 최대 시간이 차면 건너뛴다 (바쁘면 안 함)."""
    from pa.plan import make_plan
    habits, _ = load()
    if not habits:
        return [], {}
    week0 = (t_now - timedelta(days=t_now.weekday())).date()
    done_set = done(conn, datetime.combine(week0, time(0), KST))
    pinned = {t.key: (s, e) for t, s, e in main_plan}
    got, why = [], {}
    weekly = {}
    for h, task in sorted(candidates(habits, cfg, t_now, done_set), key=lambda x: x[1].due):
        if h["every"] == "weekly":  # 주N회: 그 주에 이미 했거나 놓은 만큼 빼고
            d = task.due.date()
            wk = d - timedelta(days=d.weekday())
            did = sum(1 for (n, day) in done_set if n == h["title"] and wk <= datetime.fromisoformat(day).date() < wk + timedelta(days=7))
            if did + weekly.get((h["title"], wk), 0) >= h["per_week"]:
                continue
        placed, _, _ = make_plan([task], busy, cfg, t_now, pinned)
        if not placed:
            continue  # 그날 바쁨 → 건너뜀
        t, s, e = placed[0]
        t = replace(t, key=task.key)
        got.append((t, s, e))
        pinned[task.key] = (s, e)
        why[task.key] = "습관 — 그날 빈 시간에 (바쁘면 건너뜀)"
        if h["every"] == "weekly":
            wk = task.due.date() - timedelta(days=task.due.date().weekday())
            weekly[(h["title"], wk)] = weekly.get((h["title"], wk), 0) + 1
    return got, why


def signature(conn):
    habits, _ = load()
    t = now()
    return [sorted(json.dumps(h, sort_keys=True, ensure_ascii=False) for h in habits),
            sorted(done(conn, t - timedelta(days=8)))]
