"""마감 캘린더: 비서의 할 일 전체(과제·퀴즈·강의 출석·직접 넣은 할 일)의 마감을 Google Calendar '마감' 에.

- 마감마다 '마감 30분 전 ~ 마감' 일정 (알림 없음 — 보기용).
- 알림은 '마감 알림' 캘린더에 따로: 알림 시점(config/timetable.yaml reminders.deadline_minutes_before:
  하루 전·3시간 전·1시간 전)마다 '⏰ 하루 전 · 과제명' 같은 0분짜리 일정 + 그 시각 알림.
  Google 알림 문구는 바꿀 수 없어서, 제목에 '며칠 전'을 넣어 알림만 봐도 알 수 있게 (사용자 요청 2026-11-15).
  휴대폰 Google Calendar 앱이 알려 준다 — PC 가 꺼져 있어도.
- 끝냈거나 제외한 것은 앞으로의 일정에서 지운다. 지난 마감은 기록으로 남긴다.
- 예전 '과제' 캘린더(Canvas 피드 기반)는 이름만 '마감' 으로 바꿔 그대로 쓴다 (휴대폰 체크 설정 유지).
"""
from datetime import timedelta

from pa import db
from pa.config import reminders
from pa.gcal import get_or_create_calendar, get_service
from pa.model import KIND_LABEL, now, parse_dt, short_course

TZ = "Asia/Seoul"
CALENDAR_NAME = "마감"
REMIND_NAME = "마감 알림"
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
    from pa.plan import is_exam
    icon = "📝" if is_exam(t) else ICON[t.kind]
    summary = f"{icon} {t.title}" + (f" [{short_course(t.course)}]" if t.course else "")
    return {
        "summary": summary,
        "start": {"dateTime": (t.due - timedelta(minutes=30)).isoformat(), "timeZone": TZ},
        "end": {"dateTime": t.due.isoformat(), "timeZone": TZ},
        "description": f"{KIND_LABEL[t.kind]} 마감 {t.due:%m/%d %H:%M}\n{t.url}".strip(),
        "transparency": "transparent",  # 마감 표시일 뿐 — '바쁨'으로 잡지 않음
        "extendedProperties": {"private": {"pa_source": "deadline", "pa_key": t.key}},
        "reminders": {"useDefault": False, "overrides": []},  # 알림은 '마감 알림' 캘린더에서
    }


def ahead_label(m):
    """알림 시점 이름: 1440 → '하루 전', 4320 → '3일 전', 180 → '3시간 전', 30 → '30분 전'."""
    if m % 1440 == 0:
        return "하루 전" if m == 1440 else f"{m // 1440}일 전"
    if m % 60 == 0:
        return f"{m // 60}시간 전"
    return f"{m}분 전"


def remind_body(t, m):
    from pa.plan import is_exam
    at = (t.due - timedelta(minutes=m)).isoformat()
    icon = "📝" if is_exam(t) else ICON[t.kind]
    return {
        "summary": f"⏰ {ahead_label(m)} · {icon} {t.title}" + (f" [{short_course(t.course)}]" if t.course else ""),
        "start": {"dateTime": at, "timeZone": TZ},
        "end": {"dateTime": at, "timeZone": TZ},
        "description": f"{KIND_LABEL[t.kind]} 마감 {t.due:%m/%d %H:%M} ({ahead_label(m)} 알림)\n{t.url}".strip(),
        "transparency": "transparent",
        "extendedProperties": {"private": {"pa_source": "remind", "pa_key": f"{t.key}|{m}"}},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]},
    }


def _remind_minutes(r):
    """알림 비교용 — Google 은 알림 목록 순서를 섞어서 돌려주므로 정렬해서 비교한다."""
    r = r or {}
    return (bool(r.get("useDefault")), sorted(o.get("minutes", 0) for o in r.get("overrides", [])))


def same(ev, body):
    return (ev.get("summary") == body["summary"] and ev.get("description", "") == body["description"]
            and _remind_minutes(ev.get("reminders")) == _remind_minutes(body["reminders"])
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


def signature(conn):
    import hashlib
    import json
    rows = conn.execute("SELECT key, kind, course, title, due, url FROM tasks WHERE status = 'open' AND due IS NOT NULL "
                        "ORDER BY key").fetchall()
    return hashlib.sha1(json.dumps([[tuple(r) for r in rows], reminders()], default=str).encode()).hexdigest()


def needed(conn, max_age_hours=6):
    """마감이 바뀌었거나 6시간이 지났을 때만 캘린더를 확인한다 (다른 곳에서 일정을 지웠어도 하루 몇 번은 바로잡힘)."""
    last = parse_dt(db.get_meta(conn, "deadlines_synced_at"))
    return (db.get_meta(conn, "deadlines_sig") != signature(conn)
            or not last or now() - last >= timedelta(hours=max_age_hours))


DENSE_WINDOW = timedelta(hours=30)  # 촘촘한 알림은 이 안의 마감만 (6시간마다 맞추므로 늘 24시간 전에는 생겨 있음)


def dense_ticks(tasks, t_now, frm, every):
    """마감 frm 분 전부터 every 분마다 울릴 시각 → 그때 남은 마감들 [(마감 분, 할 일)].
    여러 마감의 시각이 가까우면(every 의 3/4 안) 하나로 합친다 → 마감이 몇 개든 every 분에 알림 하나."""
    if frm <= 0:
        return {}
    dues = [(t.due.replace(second=0, microsecond=0), t) for t in tasks if t_now < t.due <= t_now + DENSE_WINDOW]
    raw = sorted({d - timedelta(minutes=m) for d, _ in dues for m in range(every, frm + 1, every)})
    kept = []
    for tk in raw:
        if tk > t_now and not (kept and tk - kept[-1] < timedelta(minutes=every * 0.75)):
            kept.append(tk)
    out = {}
    for tk in kept:
        hit = sorted([(d, t) for d, t in dues if timedelta(0) < d - tk <= timedelta(minutes=frm)], key=lambda x: (x[0], x[1].title))
        if hit:
            out[tk] = hit
    return out


def dense_body(tk, hit):
    from pa.plan import is_exam
    groups = {}
    for d, t in hit:
        groups.setdefault(d, []).append(f"{'📝' if is_exam(t) else ICON[t.kind]} {t.title}")
    parts = []
    for d, names in groups.items():
        m = int((d - tk).total_seconds() // 60)
        parts.append(f"{m}분 전 · " + (names[0] if len(names) == 1 else f"마감 {len(names)}개 · " + ", ".join(names)))
    summary = "⏰ " + " | ".join(parts)
    if len(summary) > 140:
        summary = summary[:139] + "…"
    at = tk.isoformat()
    return {
        "summary": summary,
        "start": {"dateTime": at, "timeZone": TZ},
        "end": {"dateTime": at, "timeZone": TZ},
        "description": "\n".join(f"{t.title} — 마감 {t.due:%m/%d %H:%M} {t.url}".strip() for _, t in hit),
        "transparency": "transparent",
        "extendedProperties": {"private": {"pa_source": "remind", "pa_key": f"dense|{at}"}},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]},
    }


def sync_reminders(service, tasks, t_now):
    """'마감 알림' 캘린더: 앞으로 울릴 알림만 둔다 (울린 것·끝낸 일의 알림은 지움).
    마감마다 정해 둔 알림(하루 전 등) + 마감 직전 촘촘한 알림(합쳐서, 30시간 안 마감만)."""
    cal = get_or_create_calendar(service, REMIND_NAME, TZ)
    existing = _list(service, cal, "remind")
    rem = reminders()
    wanted = {}
    for t in tasks:
        for m in rem["deadline"]:
            if m <= rem["dense_from"]:  # 촘촘한 알림이 그 시간을 덮음 → 겹쳐 울리지 않게
                continue
            if t.due - timedelta(minutes=m) > t_now:
                wanted[f"{t.key}|{m}"] = remind_body(t, m)
    for tk, hit in dense_ticks(tasks, t_now, rem["dense_from"], rem["dense_every"]).items():
        wanted[f"dense|{tk.isoformat()}"] = dense_body(tk, hit)
    created = updated = removed = 0
    for k, body in wanted.items():
        ev = existing.get(k)
        if ev is None:
            service.events().insert(calendarId=cal, body=body).execute()
            created += 1
        elif not (ev.get("summary") == body["summary"] and parse_dt(ev["start"].get("dateTime")) == parse_dt(body["start"]["dateTime"])):
            service.events().update(calendarId=cal, eventId=ev["id"], body=body).execute()
            updated += 1
    for k, ev in existing.items():
        if k not in wanted:
            service.events().delete(calendarId=cal, eventId=ev["id"]).execute()
            removed += 1
    return created, updated, removed


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
    c2, u2, r2 = sync_reminders(service, tasks, t_now)
    created, updated, removed = created + c2, updated + u2, removed + r2
    db.set_meta(conn, "deadlines_sig", signature(conn))
    db.set_meta(conn, "deadlines_synced_at", t_now.isoformat())
    return created, updated, removed
