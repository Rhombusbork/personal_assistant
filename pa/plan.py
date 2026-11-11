"""남은 할 일을 빈 시간에 배치해 Google Calendar '학습 계획' 캘린더에 넣는다.

규칙
- 마감이 가장 가까운 항목부터 배치 (EDF)
- 월·수·금·토(main_days)의 빈 시간에 먼저 넣고, 마감 전까지 자리가 없으면 일요일(fallback_days) 사용
- 날짜가 정해진 반복 할 일은 그 날짜에만 배치
- 대면 수업·약속 시간은 피하고, 하루 최대 max_minutes_per_day
- 같은 과목의 퀴즈·과제는 그 과목 강의 뒤에
- 이미 시작한 계획 블록은 움직이지 않음
- 캘린더에는 바뀐 것만 반영
"""
from datetime import datetime, time, timedelta

from pa import db
from pa.config import load_timetable
from pa.gcal import get_or_create_calendar, get_service
from pa.model import KIND_LABEL, KST, label, now, parse_dt

TZ = "Asia/Seoul"
CALENDAR_NAME = "학습 계획"
BUSY_CALENDARS = ["primary", "수업 시간표"]
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def fetch_busy(service, start, end):
    """대면 수업·약속을 (시작, 끝, 이름) 목록으로. 종일 일정과 '한가함' 일정은 제외."""
    cals = {c["summary"]: c["id"] for c in service.calendarList().list().execute().get("items", [])}
    out = []
    for name in BUSY_CALENDARS:
        cal_id = "primary" if name == "primary" else cals.get(name)
        if not cal_id:
            continue
        items = service.events().list(calendarId=cal_id, timeMin=start.isoformat(), timeMax=end.isoformat(),
                                      singleEvents=True, orderBy="startTime", maxResults=2500).execute()
        for ev in items.get("items", []):
            if "dateTime" not in ev["start"] or ev.get("transparency") == "transparent":
                continue
            out.append((parse_dt(ev["start"]["dateTime"]), parse_dt(ev["end"]["dateTime"]),
                        ev.get("summary", "일정")))
    return sorted(out)


def free_slots(t_now, until, cfg, busy):
    ds, de = (time.fromisoformat(cfg[k]) for k in ("day_start", "day_end"))
    slots, day = [], t_now.date()
    while day <= until.date():
        s = max(datetime.combine(day, ds, KST), t_now)
        e = datetime.combine(day, de, KST)
        for bs, be, _ in busy:
            if be <= s or bs >= e:
                continue
            if bs > s:
                slots.append([s, bs])
            s = max(s, be)
        if s < e:
            slots.append([s, e])
        day += timedelta(days=1)
    return slots


def place(task, slots, cfg, days, used, not_before):
    """days 요일 중 not_before 이후, 마감 전에 끝나고 하루 한도를 넘지 않는 가장 이른 자리."""
    need = timedelta(minutes=task.minutes)
    brk = timedelta(minutes=cfg["break_minutes"])
    for sl in slots:
        start = max(sl[0], not_before)
        end = start + need
        day = start.date()
        if (DAYS[start.weekday()] not in days or end > sl[1] or end > task.due
                or used.get(day, 0) + task.minutes > cfg["max_minutes_per_day"]):
            continue
        if start == sl[0]:
            sl[0] = end + brk
        else:  # 구간 중간에 넣는 경우 앞부분은 남겨 둔다
            slots.insert(slots.index(sl) + 1, [end + brk, sl[1]])
            sl[1] = start
        used[day] = used.get(day, 0) + task.minutes
        return start, end
    return None


def make_plan(items, busy, cfg, t_now, pinned):
    """pinned: 이미 진행 중이라 고정하는 {key: (start, end)}."""
    until = max([t.due for t in items], default=t_now)
    blocks = busy + [(s, e, "진행 중") for s, e in pinned.values()]
    slots = free_slots(t_now, until, cfg, sorted(blocks))
    used = {}
    for s, e in pinned.values():
        used[s.date()] = used.get(s.date(), 0) + int((e - s).total_seconds() // 60)
    main = cfg["main_days"]
    every = main + cfg["fallback_days"]
    plan, failed, lecture_end = [], [], {}
    for t in items:
        if t.key in pinned:
            continue
        not_before = t_now if t.kind == "lecture" else lecture_end.get(t.course, t_now)
        if t.earliest:
            not_before = max(not_before, t.earliest)
        if t.earliest and t.earliest.date() == t.due.date():  # 날짜가 정해진 할 일
            got = place(t, slots, cfg, DAYS, used, not_before)
        else:
            got = place(t, slots, cfg, main, used, not_before) or place(t, slots, cfg, every, used, not_before)
        if not got:
            failed.append(t)
            continue
        plan.append((t, *got))
        if t.kind == "lecture":
            lecture_end[t.course] = max(lecture_end.get(t.course, t_now), got[1])
    return sorted(plan, key=lambda x: x[1]), failed


def summary(t):
    return f"[{KIND_LABEL[t.kind]}] {label(t)}"


def run(conn, service=None, write=True):
    """계획을 다시 짜서 저장소(plan, busy)와 캘린더에 반영. (plan, failed) 반환."""
    cfg = load_timetable()["planner"]
    t_now = now()
    horizon = t_now + timedelta(days=cfg["horizon_days"])
    items = [t for t in db.tasks(conn, "status = 'open' AND due IS NOT NULL")
             if t_now < t.due <= horizon and (t.earliest is None or t.earliest <= horizon)]
    by_key = {t.key: t for t in items}

    old = {r["key"]: r for r in conn.execute("SELECT * FROM plan").fetchall()}
    pinned = {}
    for k, r in old.items():
        s, e = parse_dt(r["start"]), parse_dt(r["end"])
        if k in by_key and s <= t_now < e:
            pinned[k] = (s, e)
        elif k in by_key and e <= t_now:
            db.log(conn, "plan_missed", k, start=r["start"])

    service = service or get_service()
    busy = fetch_busy(service, t_now.replace(hour=0, minute=0), horizon + timedelta(days=1))
    plan, failed = make_plan(items, busy, cfg, t_now, pinned)
    plan += [(by_key[k], s, e) for k, (s, e) in pinned.items()]
    plan.sort(key=lambda x: x[1])

    conn.execute("DELETE FROM busy")
    conn.executemany("INSERT INTO busy VALUES (?, ?, ?)", [(s.isoformat(), e.isoformat(), n) for s, e, n in busy])
    if write:
        sync_calendar(conn, service, plan, old, t_now)
    db.set_meta(conn, "planned_at", t_now.isoformat())
    db.set_meta(conn, "plan_failed", ",".join(t.key for t in failed))
    conn.commit()
    return plan, failed


def sync_calendar(conn, service, plan, old, t_now):
    """바뀐 블록만 캘린더에 반영하고 plan 표를 새 계획으로 교체한다."""
    cal_id = get_or_create_calendar(service, CALENDAR_NAME, TZ)
    keep_ids = set()
    rows = []
    for t, s, e in plan:
        body = {
            "summary": summary(t),
            "start": {"dateTime": s.isoformat(), "timeZone": TZ},
            "end": {"dateTime": e.isoformat(), "timeZone": TZ},
            "description": f"마감: {t.due:%Y-%m-%d %H:%M}\n키: {t.key}\n{t.url}",
            "extendedProperties": {"private": {"pa_source": "plan", "pa_key": t.key}},
        }
        o = old.get(t.key)
        ev_id = o["event_id"] if o else None
        same = o and o["start"] == s.isoformat() and o["end"] == e.isoformat() and o["summary"] == body["summary"]
        if ev_id and not same:
            try:
                service.events().update(calendarId=cal_id, eventId=ev_id, body=body).execute()
            except Exception:
                ev_id = None
        if not ev_id:
            ev_id = service.events().insert(calendarId=cal_id, body=body).execute()["id"]
        keep_ids.add(ev_id)
        rows.append((t.key, s.isoformat(), e.isoformat(), body["summary"], ev_id))

    # 앞으로의 계획 중 새 계획에 없는 블록은 삭제 (지난 블록은 기록으로 남김)
    page = service.events().list(calendarId=cal_id, timeMin=t_now.isoformat(), maxResults=2500,
                                 privateExtendedProperty="pa_source=plan").execute()
    for ev in page.get("items", []):
        if ev["id"] not in keep_ids and parse_dt(ev["start"]["dateTime"]) >= t_now:
            service.events().delete(calendarId=cal_id, eventId=ev["id"]).execute()

    conn.execute("DELETE FROM plan")
    conn.executemany("INSERT INTO plan VALUES (?, ?, ?, ?, ?)", rows)
