"""마감 캘린더: 비서의 할 일 전체(과제·퀴즈·강의 출석·직접 넣은 할 일)의 마감을 Google Calendar '마감' 에.

- 마감마다 '마감 30분 전 ~ 마감' 일정 + 알림 (config/timetable.yaml reminders.deadline_minutes_before:
  하루 전·3시간 전·1시간 전). 휴대폰 Google Calendar 앱이 알려 준다 — PC 가 꺼져 있어도.
- 끝냈거나 제외한 것은 앞으로의 일정에서 지운다. 지난 마감은 기록으로 남긴다.
- 예전 '과제' 캘린더(Canvas 피드 기반)는 이름만 '마감' 으로 바꿔 그대로 쓴다 (휴대폰 체크 설정 유지).
"""
from datetime import timedelta

from pa import db
from pa.config import popup, reminders
from pa.gcal import get_or_create_calendar, get_service
from pa.model import KIND_LABEL, now, parse_dt, short_course

TZ = "Asia/Seoul"
CALENDAR_NAME = "마감"
OLD_NAME = "과제"
KINDS = ("assignment", "quiz", "lecture", "todo")
ICON = {"assignment": "📚", "quiz": "❓", "lecture": "🎬", "todo": "✅"}
DAYS_AHEAD = 60


def calendar_id(service):
    cals = {c["summary"]: c["id"] for c in service.calendarList().list().execute().get("items", [])}
    if CALENDAR_NAME in cals:
        return cals[CALENDAR_NAME]
    if OLD_NAME in cals:  # 같은 캘린더의 이름만 바꾼다
        service.calendars().patch(calendarId=cals[OLD_NAME], body={"summary": CALENDAR_NAME}).execute()
        return cals[OLD_NAME]
    return get_or_create_calendar(service, CALENDAR_NAME, TZ)


def event_body(t):
    summary = f"{ICON[t.kind]} {t.title}" + (f" [{short_course(t.course)}]" if t.course else "")
    return {
        "summary": summary,
        "start": {"dateTime": (t.due - timedelta(minutes=30)).isoformat(), "timeZone": TZ},
        "end": {"dateTime": t.due.isoformat(), "timeZone": TZ},
        "description": f"{KIND_LABEL[t.kind]} 마감 {t.due:%m/%d %H:%M}\n{t.url}".strip(),
        "transparency": "transparent",  # 마감 표시일 뿐 — '바쁨'으로 잡지 않음
        "extendedProperties": {"private": {"pa_source": "deadline", "pa_key": t.key}},
        # 일정이 마감 30분 전에 시작하므로 30분을 뺀다
        "reminders": popup([m - 30 for m in reminders()["deadline"]]),
    }


def same(ev, body):
    return (ev.get("summary") == body["summary"] and ev.get("description", "") == body["description"]
            and ev.get("reminders") == body["reminders"]
            and all(parse_dt(ev[k].get("dateTime")) == parse_dt(body[k]["dateTime"]) for k in ("start", "end")))


def _list(service, cal_id, source):
    out, token = {}, None
    while True:
        page = service.events().list(calendarId=cal_id, privateExtendedProperty=f"pa_source={source}",
                                     pageToken=token, maxResults=2500).execute()
        for ev in page.get("items", []):
            out[ev["extendedProperties"]["private"]["pa_key"]] = ev
        token = page.get("nextPageToken")
        if not token:
            return out


def sync(conn, service=None):
    """(생성, 갱신, 삭제) 수."""
    t_now = now()
    marks = ",".join("?" * len(KINDS))
    tasks = [t for t in db.tasks(conn, f"status = 'open' AND due IS NOT NULL AND kind IN ({marks})", KINDS)
             if t_now < t.due <= t_now + timedelta(days=DAYS_AHEAD)]
    service = service or get_service()
    cal = calendar_id(service)
    removed = 0
    for ev in _list(service, cal, "canvas").values():  # 예전 Canvas 피드 일정 (한 번만 정리)
        service.events().delete(calendarId=cal, eventId=ev["id"]).execute()
        removed += 1
    existing = _list(service, cal, "deadline")
    created = updated = 0
    for t in tasks:
        body = event_body(t)
        ev = existing.get(t.key)
        if ev is None:
            service.events().insert(calendarId=cal, body=body).execute()
            created += 1
        elif not same(ev, body):
            service.events().update(calendarId=cal, eventId=ev["id"], body=body).execute()
            updated += 1
    wanted = {t.key for t in tasks}
    for key, ev in existing.items():  # 끝냈거나 제외한 것: 앞으로의 일정만 지움
        end = parse_dt(ev["end"].get("dateTime"))
        if key not in wanted and end and end > t_now:
            service.events().delete(calendarId=cal, eventId=ev["id"]).execute()
            removed += 1
    return created, updated, removed
