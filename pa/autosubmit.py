"""자동 제출 — 먼저 내고, 사용자가 나중에 ✅ 완성으로 확인한다 (2026-11-23 사용자가 정함). 엔진이 30초마다 (일하는 PC 만).

대상 (config/timetable.yaml 의 auto_submit.scope):
  reserved (기본) = 시간을 정한 Canvas 과제(시간 정하기·시간표에서 옮김) + ⋯ '자동 제출 켜기' 한 과제 ('끄기' 한 과제는 빼고)
  all             = 제외하지 않은 모든 Canvas 파일 제출 과제
언제: 정한 시간이 끝날 때, 늦어도 마감 hours_before_due(6)시간 전. 그보다 늦게 켰으면 바로.
초안: 보고서 파일이 없으면 draft_lead_minutes(90)분 전에 AI 초안을 맡긴다 — 빈칸 없이 다 채운 초안 (draft_if_missing).
      내가 쓴 파일에 '✍ 내 생각' 빈칸이 남아 있으면 내지 않고 알린다.
낸 뒤: Canvas 에서 다시 읽어 확인 (pa/submit.py) → 대시보드 '확인 필요' + '마감 알림' 캘린더 알림 (바로 · 1시간 뒤 · 마감 3시간 전).
       ✅ 완성을 누르거나 직접 다시 내면 사라진다. 안 눌러도 제출은 그대로.
"""
import json
import re
from datetime import timedelta

from pa import db, jobs, submit
from pa.config import load_timetable
from pa.model import now, parse_dt, short_course

DEFAULTS = {"enabled": True, "scope": "reserved", "hours_before_due": 6, "draft_if_missing": True,
            "draft_lead_minutes": 90, "remind_after_hours": 1, "remind_before_due_hours": 3}
BLANK = "✍ 내 생각"
RE_CANVAS = re.compile(r"/courses/\d+/assignments/\d+")


def cfg():
    return {**DEFAULTS, **(load_timetable().get("auto_submit") or {})}


def state(conn, key):
    return json.loads(db.get_meta(conn, "autosubmit_state:" + key) or "{}")


def _set_state(conn, key, **st):
    db.set_meta(conn, "autosubmit_state:" + key, json.dumps({**st, "at": now().isoformat()}, ensure_ascii=False))


def set_flag(conn, key, on):
    """⋯ 자동 제출 켜기/끄기. 다시 켜면 지난 결과(실패 등)를 지우고 다시 시도."""
    db.set_meta(conn, "autosubmit:" + key, "on" if on else "off")
    if on:
        conn.execute("DELETE FROM meta WHERE k = ?", ("autosubmit_state:" + key,))
    db.log(conn, "autosubmit_flag", key, on=bool(on))


def reserved_end(conn, t):
    """사용자가 정한 시간이 끝나는 시각 (없으면 None)."""
    ends = [parse_dt(r["end"]) for r in db.slots(conn, key=t.key)]
    if t.slot_end:
        ends.append(t.slot_end)
    return max(ends) if ends else None


def candidates(conn, c=None):
    c = c or cfg()
    out = []
    for t in db.tasks(conn, "status = 'open' AND kind = 'assignment' AND source = 'canvas' AND due IS NOT NULL"):
        flag = db.get_meta(conn, "autosubmit:" + t.key)
        if not RE_CANVAS.search(t.url or "") or flag == "off":
            continue
        if c["scope"] == "all" or flag == "on" or reserved_end(conn, t):
            out.append(t)
    return out


def submit_at(conn, t, c=None):
    c = c or cfg()
    latest = t.due - timedelta(hours=float(c["hours_before_due"]))
    end = reserved_end(conn, t)
    return min(end, latest) if end else latest


def _report(conn, key):
    return jobs.report_path(dict(conn.execute("SELECT * FROM tasks WHERE key = ?", (key,)).fetchone()), conn)


def tick(conn, t_now):
    """때가 된 것을 낸다 (초안이 없으면 먼저 맡김). 낸 할 일 키 목록."""
    c = cfg()
    if not c["enabled"]:
        return []
    did = []
    for t in candidates(conn, c):
        st = state(conn, t.key)
        if st.get("state") in ("done", "failed", "skipped"):
            continue
        at = submit_at(conn, t, c)
        path = _report(conn, t.key)
        ready = path.exists() or path.with_suffix(".pdf").exists()
        if not ready:
            if t_now < at - timedelta(minutes=float(c["draft_lead_minutes"])):
                continue
            if not c["draft_if_missing"]:
                if t_now >= at:
                    _set_state(conn, t.key, state="failed", why="보고서 파일이 없음 (AI 초안 자동 쓰기가 꺼져 있음)")
                continue
            job = conn.execute("SELECT status, error FROM jobs WHERE id = ?", (st.get("job") or 0,)).fetchone()
            if st.get("state") != "drafting" or not job:
                _set_state(conn, t.key, state="drafting", job=jobs.enqueue(conn, "report-submit", t.key, t.title))
                db.log(conn, "autosubmit_draft", t.key)
            elif job["status"] == "failed":
                _set_state(conn, t.key, state="failed", why="AI 초안 실패: " + (job["error"] or "")[:150])
            continue
        if t_now < at:
            continue
        if path.suffix == ".md" and path.exists() and BLANK in path.read_text(encoding="utf-8"):
            _set_state(conn, t.key, state="failed", why=f"보고서에 '{BLANK}' 빈칸이 남아 있음 — 채운 뒤 ⋯ 📤 제출")
            continue
        try:
            r = submit.submit(conn, t.key, reveal=False, auto=True)
            _set_state(conn, t.key, state="done", file=r["name"])
            did.append(t.key)
        except submit.SubmitError as e:
            same = "이미 같은 파일" in str(e)
            _set_state(conn, t.key, state="skipped" if same else "failed", why=str(e)[:200])
        except Exception as e:  # 연결 문제 등 → 다음 번에 다시 (마감 30분 전까지)
            db.log(conn, "autosubmit_error", t.key, error=str(e)[:200])
            if t_now >= t.due - timedelta(minutes=30):
                _set_state(conn, t.key, state="failed", why="Canvas 연결 실패: " + str(e)[:150])
    conn.commit()
    return did


def reviews(conn):
    """자동으로 냈는데 아직 ✅ 완성을 안 누른 것 (직접 다시 냈으면 빠짐)."""
    last = {}
    for r in conn.execute("SELECT ts, type, key, detail FROM events WHERE type IN ('submitted', 'submit_confirmed') ORDER BY id"):
        last[r["key"]] = r
    out = []
    for key, r in last.items():
        d = json.loads(r["detail"] or "{}")
        if r["type"] != "submitted" or not d.get("auto"):
            continue
        t = conn.execute("SELECT title, course, due, url FROM tasks WHERE key = ?", (key,)).fetchone()
        out.append({"key": key, "ts": r["ts"], "title": t["title"] if t else key, "course": short_course(t["course"]) if t else "",
                    "due": t["due"] if t else None, "url": d.get("url") or (t["url"] if t else ""),
                    **{k: d.get(k) for k in ("name", "size", "pages", "attempt", "late", "drafted")}})
    return sorted(out, key=lambda x: x["ts"], reverse=True)


def confirm(conn, key):
    db.log(conn, "submit_confirmed", key)


def upcoming(conn, t_now=None):
    """화면용: 자동 제출 예정·결과 [{key, title, at, state, why, draft}] (마감 지난 것 빼고)."""
    t_now = t_now or now()
    c = cfg()
    out = []
    for t in candidates(conn, c):
        st = state(conn, t.key)
        if t.due <= t_now:
            continue
        path = _report(conn, t.key)
        out.append({"key": t.key, "title": t.title, "course": short_course(t.course), "due": t.due.isoformat(),
                    "at": submit_at(conn, t, c).isoformat(), "state": st.get("state", "waiting"), "why": st.get("why", ""),
                    "draft": path.exists() or path.with_suffix(".pdf").exists(),
                    "on": db.get_meta(conn, "autosubmit:" + t.key) == "on"})
    return sorted(out, key=lambda x: x["at"])


# ---- 휴대폰 알림: '마감 알림' 캘린더에 확인 알림 (바로 · 1시간 뒤 · 마감 3시간 전) ----------------------------

def wanted_events(conn, t_now, c=None):
    from pa import deadlines
    c = c or cfg()
    out = {}
    for r in reviews(conn):
        ts, due = parse_dt(r["ts"]), parse_dt(r["due"])
        times = {"now": ts + timedelta(minutes=2), "later": ts + timedelta(hours=float(c["remind_after_hours"]))}
        if due:
            times["due"] = due - timedelta(hours=float(c["remind_before_due_hours"]))
        for tag, at in times.items():
            if at <= t_now - timedelta(hours=6) or (tag == "due" and at <= ts + timedelta(minutes=30)):
                continue  # 울린 지 오래된 것만 지운다 (방금 울린 것을 지우면 휴대폰 알림이 사라질 수 있음)
            out[f"{r['key']}|{tag}"] = {
                "summary": f"📤 확인해 주세요 · {r['title']}" + (f" [{r['course']}]" if r["course"] else "") + " (자동 제출함)",
                "start": {"dateTime": at.isoformat(), "timeZone": deadlines.TZ},
                "end": {"dateTime": at.isoformat(), "timeZone": deadlines.TZ},
                "description": f"비서가 {ts:%m/%d %H:%M} 에 자동 제출했어요: {r.get('name') or ''}\n"
                               f"Canvas 에서 낸 파일을 열어 보고, 대시보드 '확인 필요'에서 ✅ 완성 (안 눌러도 제출은 그대로)\n{r['url']}".strip(),
                "transparency": "transparent",
                "extendedProperties": {"private": {"pa_source": "review", "pa_key": f"{r['key']}|{tag}"}},
                "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]},
            }
    return out


def sync_calendar(conn, service=None, t_now=None):
    """바뀌었을 때만 Google 에 반영. (만듦, 지움) — 로그인 문제 등은 조용히 다음에."""
    import hashlib
    t_now = t_now or now()
    wanted = wanted_events(conn, t_now)
    sig = hashlib.sha1(json.dumps(sorted((k, v["start"]["dateTime"]) for k, v in wanted.items())).encode()).hexdigest()
    if db.get_meta(conn, "review_cal_sig") == sig:
        return 0, 0
    from pa import deadlines, gcal
    service = service or gcal.get_service()
    cal = gcal.get_or_create_calendar(service, deadlines.REMIND_NAME, deadlines.TZ)
    existing = deadlines._list(service, cal, "review")
    made = gone = 0
    for k, body in wanted.items():
        if k not in existing:
            service.events().insert(calendarId=cal, body=body).execute()
            made += 1
    for k, ev in existing.items():
        if k not in wanted:
            service.events().delete(calendarId=cal, eventId=ev["id"]).execute()
            gone += 1
    db.set_meta(conn, "review_cal_sig", sig)
    conn.commit()
    return made, gone
