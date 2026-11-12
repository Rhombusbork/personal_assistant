"""남은 할 일을 빈 시간에 배치해 Google Calendar '학습 계획' 캘린더에 넣는다.

규칙
- 마감이 가장 가까운 항목부터 배치 (EDF)
- 월·수·금·토(main_days)의 빈 시간에 먼저 넣고, 마감 전까지 자리가 없으면 일요일(fallback_days),
  그래도 없으면 나머지 요일 사용
- 날짜가 정해진 반복 할 일은 그 날짜에만 배치
- 대면 수업·약속 시간은 피하고, 하루 최대 max_minutes_per_day
- 같은 과목의 퀴즈·과제는 그 과목 강의 뒤에
- 이미 시작한 계획 블록은 움직이지 않음
- 캘린더에는 바뀐 것만 반영
"""
import json
import re
from dataclasses import replace
from datetime import datetime, time, timedelta

from pa import calibrate, db
from pa.config import load_timetable, popup, reminders
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
    """(계획 [(할 일, 시작, 끝)], 자리 없는 할 일, 이유 {키: 문장}).

    pinned: 이미 진행 중이라 고정하는 {계획 키: (시작, 끝)}.
    큰 일(split_over 분 초과)은 chunk 분 이하로 나눠 되도록 다른 날에 배치한다 → 키 '원래키#번호'.
    """
    until = max([t.due for t in items], default=t_now)
    blocks = busy + [(s, e, "진행 중") for s, e in pinned.values()]
    slots = free_slots(t_now, until, cfg, sorted(blocks))
    used = {}
    for s, e in pinned.values():
        used[s.date()] = used.get(s.date(), 0) + int((e - s).total_seconds() // 60)
    main = cfg["main_days"]
    every = main + cfg["fallback_days"]
    split_over, chunk = cfg.get("split_over", 120), cfg.get("chunk_minutes", 90)
    plan, failed, why, lecture_end = [], [], {}, {}
    # 마감 순. 같은 날 마감이면 강의 먼저 (17강 퀴즈 23:59:00 < 17강 강의 23:59:59 같은 경우에도 강의 → 퀴즈)
    items = sorted(items, key=lambda t: (t.due.date(), t.kind != "lecture", t.due))

    def put(t, not_before):
        """요일 단계별로 배치. (시작, 끝, 이유) 또는 None."""
        if t.earliest and t.earliest.date() == t.due.date():  # 날짜가 정해진 할 일
            got = place(t, slots, cfg, DAYS, used, not_before)
            return got and (*got, "정해진 날")
        for days, reason in ((main, "월·수·금·토 중 마감 전 가장 이른 빈 시간"),
                             (every, "월수금토에 자리가 없어 일요일"),
                             (DAYS, "마감 전 월수금토·일에 자리가 없어 다른 요일")):
            got = place(t, slots, cfg, days, used, not_before)
            if got:
                return (*got, reason)
        return None

    for t in items:
        pinned_parts = [k for k in pinned if k == t.key or k.startswith(t.key + "#")]
        done_min = sum(int((pinned[k][1] - pinned[k][0]).total_seconds() // 60) for k in pinned_parts)
        remaining = t.minutes - done_min
        if remaining <= 0 or (pinned_parts and remaining < 15):
            continue
        not_before = t_now if t.kind == "lecture" else lecture_end.get(t.course, t_now)
        after_lecture = not_before > t_now
        if t.earliest:
            not_before = max(not_before, t.earliest)

        big = remaining > split_over and t.kind in ("todo", "assignment")
        n = -(-remaining // chunk) if big else 1
        size = -(-remaining // n)
        parts = [replace(t, minutes=size) for _ in range(n)] if big else [replace(t, minutes=remaining)]
        first = len(pinned_parts) + 1
        total = len(pinned_parts) + n
        chunked = big or bool(pinned_parts)  # 진행 중 블록과 키가 겹치지 않게
        placed = []
        for i, part in enumerate(parts):
            if chunked:
                part.key = f"{t.key}#{first + i}"
                part.title = f"{t.title} ({first + i}/{total})"
            got = None
            if placed:  # 나눈 조각은 되도록 다음 날부터, 안 되면 같은 날 이어서
                prev_end = placed[-1][2]
                next_day = datetime.combine(prev_end.date() + timedelta(days=1), time(0, 0), KST)
                got = put(part, max(not_before, next_day)) or put(part, max(not_before, prev_end))
            else:
                got = put(part, not_before)
            if not got:
                failed.append(t)
                break
            placed.append((part, got[0], got[1]))
            reason = got[2] + (" · 같은 과목 강의 뒤" if after_lecture else "") + (f" · 큰 일이라 {total}번으로 나눔" if big else "")
            if getattr(t, "factor", 1.0) != 1.0:
                reason += f" · 예상 시간 보정 ×{t.factor:.1f}"
            why[part.key] = reason
        plan += placed
        if t.kind == "lecture" and placed:
            lecture_end[t.course] = max(lecture_end.get(t.course, t_now), placed[-1][2])
    return sorted(plan, key=lambda x: x[1]), failed, why


def capacity(t_now, cfg, busy, days=7):
    """앞으로 days 일 동안 계획에 쓸 수 있는 분 (하루 한도 적용)."""
    per_day = {}
    for s, e in free_slots(t_now, t_now + timedelta(days=days - 1), cfg, busy):
        per_day[s.date()] = per_day.get(s.date(), 0) + int((e - s).total_seconds() // 60)
    return sum(min(cfg["max_minutes_per_day"], m) for m in per_day.values())


def summary(t):
    return f"[{KIND_LABEL[t.kind]}] {label(t)}"


def run(conn, service=None, write=True):
    """계획을 다시 짜서 저장소(plan, busy)와 캘린더에 반영. (plan, failed) 반환.

    Google 과 통신하는 동안에는 DB 에 쓰지 않는다 — 쓰기 잠금을 오래 잡으면
    대시보드 버튼이 그동안 기다리게 되기 때문. 쓰기는 맨 끝에 한꺼번에.
    """
    cfg = load_timetable()["planner"]
    t_now = now()
    horizon = t_now + timedelta(days=cfg["horizon_days"])
    items = [t for t in db.tasks(conn, "status = 'open' AND due IS NOT NULL")
             if t_now < t.due <= horizon and (t.earliest is None or t.earliest <= horizon)]
    # 예상 시간: 직접 정한 값(time 명령)은 그대로, 아니면 ⏱ 기록으로 보정. 이미 한 시간은 뺀다.
    fs = calibrate.factors(conn)
    spent = calibrate.tracked(conn)
    fixed = {r["key"] for r in conn.execute("SELECT key FROM tasks WHERE minutes_override IS NOT NULL")}
    for t in items:
        t.factor = 1.0 if t.key in fixed else calibrate.factor_for(fs, t.kind, t.course)
        t.minutes = round(t.minutes * t.factor)
        if spent.get(t.key):
            t.minutes = max(15, t.minutes - spent[t.key])
    by_key = {t.key: t for t in items}

    old = {r["key"]: r for r in conn.execute("SELECT * FROM plan").fetchall()}
    pinned, pinned_task, missed = {}, {}, []
    for k, r in old.items():
        base = k.split("#")[0]
        s, e = parse_dt(r["start"]), parse_dt(r["end"])
        if base in by_key and s <= t_now < e:
            pinned[k] = (s, e)
            m = re.search(r"\((\d+/\d+)\)$", r["summary"])
            pinned_task[k] = replace(by_key[base], key=k, minutes=int((e - s).total_seconds() // 60),
                                     title=by_key[base].title + (f" ({m.group(1)})" if m else ""))
        elif base in by_key and e <= t_now:
            missed.append((k, r["start"]))

    # --- 통신 (DB 쓰기 없음)
    service = service or get_service()
    # 수업·약속은 이번 주 월요일부터 (주차별 화면에서 지난 요일도 보이게). 계획은 지금부터만.
    week_start = (t_now - timedelta(days=t_now.weekday())).replace(hour=0, minute=0)
    busy = fetch_busy(service, week_start, horizon + timedelta(days=1))
    plan, failed, why = make_plan(items, busy, cfg, t_now, pinned)
    plan += [(pinned_task[k], s, e) for k, (s, e) in pinned.items()]
    for k in pinned:
        why[k] = "이미 시작한 블록이라 그대로 둠"
    plan.sort(key=lambda x: x[1])
    week_end = t_now + timedelta(days=7)
    slack = {"capacity": capacity(t_now, cfg, busy),
             "need": sum(t.minutes for t in items if t.due <= week_end)}
    remind = reminders()["plan"]
    remind_changed = db.get_meta(conn, "plan_reminder") != str(remind)
    rows = sync_calendar(service, plan, old, t_now, remind, force=remind_changed) if write else None

    # --- DB 쓰기 (짧게)
    for k, start in missed:
        db.log(conn, "plan_missed", k, start=start)
    conn.execute("DELETE FROM busy")
    conn.executemany("INSERT INTO busy VALUES (?, ?, ?)", [(s.isoformat(), e.isoformat(), n) for s, e, n in busy])
    if rows is not None:
        conn.execute("DELETE FROM plan")
        conn.executemany("INSERT INTO plan VALUES (?, ?, ?, ?, ?)", rows)
    db.set_meta(conn, "planned_at", t_now.isoformat())
    db.set_meta(conn, "plan_failed", ",".join(t.key for t in failed))
    db.set_meta(conn, "plan_why", json.dumps(why, ensure_ascii=False))
    if rows is not None:
        db.set_meta(conn, "plan_reminder", str(remind))
    db.set_meta(conn, "slack", json.dumps(slack))
    conn.commit()
    return plan, failed


def sync_calendar(service, plan, old, t_now, remind=0, force=False):
    """바뀐 블록만 캘린더에 반영하고, 새 plan 표에 넣을 줄들을 돌려준다.
    remind: 시작 몇 분 전 알림. force: 알림 설정이 바뀌었을 때 모든 블록을 다시 쓴다."""
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
            "reminders": popup(remind),
        }
        o = old.get(t.key)
        ev_id = o["event_id"] if o else None
        same = (not force and o and o["start"] == s.isoformat() and o["end"] == e.isoformat()
                and o["summary"] == body["summary"])
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
    return rows
