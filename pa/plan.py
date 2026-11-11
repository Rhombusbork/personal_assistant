"""남은 강의·퀴즈·과제를 빈 시간에 배치해 Google Calendar '학습 계획' 캘린더에 넣는다.

규칙
- 마감이 가장 가까운 항목부터 배치 (EDF)
- 월·수·금·토(main_days)의 빈 시간에 먼저 넣고, 마감 전까지 자리가 없으면 일요일(fallback_days) 사용
- 대면 수업·약속 등 Google Calendar 의 '바쁨' 시간은 피함
- 실행할 때마다 앞으로의 계획을 지우고 다시 만든다

사용법: python -m pa.plan [--dry-run]
"""
import argparse
from datetime import datetime, time, timedelta

from pa import tasks as T
from pa.config import load_timetable
from pa.gcal import get_or_create_calendar, get_service

TZ = "Asia/Seoul"
CALENDAR_NAME = "학습 계획"
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
BUSY_CALENDARS = ["primary", "수업 시간표"]


def busy_intervals(service, start, end):
    cals = {c["summary"]: c["id"] for c in service.calendarList().list().execute().get("items", [])}
    ids = [{"id": "primary"}] + [{"id": cals[n]} for n in BUSY_CALENDARS[1:] if n in cals]
    fb = service.freebusy().query(body={
        "timeMin": start.isoformat(), "timeMax": end.isoformat(), "timeZone": TZ, "items": ids,
    }).execute()
    out = []
    for cal in fb["calendars"].values():
        for b in cal.get("busy", []):
            out.append((T.parse_dt(b["start"]), T.parse_dt(b["end"])))
    return sorted(out)


def free_slots(now, until, cfg, busy, allowed_days):
    """allowed_days 요일의 [day_start, day_end] 중 busy 를 뺀 빈 구간 목록."""
    ds, de = (time.fromisoformat(cfg[k]) for k in ("day_start", "day_end"))
    slots, day = [], now.date()
    while day <= until.date():
        if DAYS[day.weekday()] in allowed_days:
            s = max(datetime.combine(day, ds, T.KST), now)
            e = datetime.combine(day, de, T.KST)
            for bs, be in busy:
                if be <= s or bs >= e:
                    continue
                if bs > s:
                    slots.append([s, bs])
                s = max(s, be)
            if s < e:
                slots.append([s, e])
        day += timedelta(days=1)
    return [sl for sl in slots if sl[1] > sl[0]]


def place(task, slots, cfg, days, used, not_before):
    """days 요일 중 not_before 이후, 마감 전에 끝나고 하루 한도를 넘지 않는 가장 이른 자리."""
    need = timedelta(minutes=task.minutes)
    for sl in slots:
        start = max(sl[0], not_before)
        end = start + need
        day = start.date()
        if (DAYS[start.weekday()] not in days or end > sl[1] or end > task.due
                or used.get(day, 0) + task.minutes > cfg["max_minutes_per_day"]):
            continue
        if start == sl[0]:
            sl[0] = end + timedelta(minutes=cfg["break_minutes"])
        else:  # 구간 중간에 넣는 경우 앞부분은 남겨 둔다
            slots.insert(slots.index(sl) + 1, [end + timedelta(minutes=cfg["break_minutes"]), sl[1]])
            sl[1] = start
        used[day] = used.get(day, 0) + task.minutes
        return start, end
    return None


def make_plan(service, now):
    cfg = load_timetable()["planner"]
    items = T.collect()
    until = max([t.due for t in items], default=now)
    busy = busy_intervals(service, now, until + timedelta(days=1))
    slots = free_slots(now, until, cfg, busy, cfg["main_days"] + cfg["fallback_days"])
    plan, failed, used = [], [], {}
    lecture_end = {}  # 과목별 마지막 강의 종료 시각 — 퀴즈·과제는 그 이후에
    for t in items:
        not_before = now if t.kind == "lecture" else lecture_end.get(t.course, now)
        got = (place(t, slots, cfg, cfg["main_days"], used, not_before)
               or place(t, slots, cfg, cfg["main_days"] + cfg["fallback_days"], used, not_before))
        if not got:
            failed.append(t)
            continue
        plan.append((t, *got))
        if t.kind == "lecture":
            lecture_end[t.course] = max(lecture_end.get(t.course, now), got[1])
    return sorted(plan, key=lambda x: x[1]), failed


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="캘린더에 쓰지 않고 출력만")
    args = p.parse_args()

    now = datetime.now(T.KST).replace(second=0, microsecond=0)
    service = get_service()
    plan, failed = make_plan(service, now)

    day = None
    for t, s, e in plan:
        if s.date() != day:
            day = s.date()
            print(f"\n📅 {T.kday(s)}")
        print(f"  {s:%H:%M}–{e:%H:%M}  [{T.KIND_LABEL[t.kind]}] {T.short_course(t.course)} · {t.title}"
              f"  (마감 {T.kday(t.due)} {t.due:%H:%M})")
    for t in failed:
        print(f"\n⚠️ 마감 전 빈 시간 부족: {T.fmt(t).strip()}")
    if args.dry_run:
        return

    cal_id = get_or_create_calendar(service, CALENDAR_NAME, TZ)
    old = service.events().list(calendarId=cal_id, timeMin=now.isoformat(),
                                privateExtendedProperty="pa_source=plan", maxResults=2500).execute()
    for ev in old.get("items", []):
        service.events().delete(calendarId=cal_id, eventId=ev["id"]).execute()
    for t, s, e in plan:
        service.events().insert(calendarId=cal_id, body={
            "summary": f"[{T.KIND_LABEL[t.kind]}] {T.short_course(t.course)} · {t.title}",
            "start": {"dateTime": s.isoformat(), "timeZone": TZ},
            "end": {"dateTime": e.isoformat(), "timeZone": TZ},
            "description": f"마감: {t.due:%Y-%m-%d %H:%M}\n키: {t.key}\n{t.url}",
            "extendedProperties": {"private": {"pa_source": "plan", "pa_key": t.key}},
        }).execute()
    print(f"\n✅ '{CALENDAR_NAME}' 캘린더에 {len(plan)}건 반영 (기존 계획 {len(old.get('items', []))}건 교체)")


if __name__ == "__main__":
    main()
