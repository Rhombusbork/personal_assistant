"""Canvas 에서 온라인 강의·퀴즈·과제를 읽어 저장소에 반영한다.

- 과제·퀴즈: 마감이 있는 것 (지난 7일 이내 마감 포함). 제출했으면 자동 완료 처리.
- 강의: 온라인 수업의 이번 주·다음 주 강의 영상 (배포용 자료는 제외).
"""
import re
from datetime import date, datetime, time, timedelta

from pa import canvas, db
from pa.config import load_timetable
from pa.model import KST, now, parse_dt

SKIP_TYPES = {"none", "on_paper", "not_graded", "wiki_page"}
MATERIAL = re.compile(r"배포용|handout|\[강의자료\]", re.I)


def lecture_deadline(module_name, week, sem_start):
    """모듈명 끝의 마지막 'MM/DD(요일) HH:MM' 을 출석 마감으로 본다. 없으면 해당 주 시작+6일 23:59."""
    found = re.findall(r"(\d{1,2})/(\d{1,2})\([^)]*\)\s*(\d{1,2}):(\d{2})", module_name)
    if found:
        mo, d, h, mi = map(int, found[-1])
        return datetime(sem_start.year, mo, d, h, mi, tzinfo=KST)
    end = sem_start + timedelta(days=(week - 1) * 7 + 6)
    return datetime.combine(end, time(23, 59), KST)


def collect():
    tt = load_timetable()
    minutes = tt["planner"]["minutes"]
    sem_start = date.fromisoformat(tt["semester_start"])
    t_now = now()
    this_week = (t_now.date() - sem_start).days // 7 + 1
    online = tt.get("online_classes", [])
    items = []

    for c in canvas.active_courses():
        cname = c["name"]
        for a in canvas.get(f"/courses/{c['id']}/assignments", **{"include[]": "submission"}):
            due = parse_dt(a.get("due_at"))
            if not due or due < t_now - timedelta(days=7) or SKIP_TYPES & set(a.get("submission_types", [])):
                continue
            sub = a.get("submission") or {}
            kind = "quiz" if a.get("quiz_id") else "assignment"
            items.append({
                "key": f"a{a['id']}", "kind": kind, "course": cname, "title": a["name"].strip(),
                "due": due.isoformat(), "earliest": None, "minutes": minutes[kind],
                "url": a.get("html_url", ""),
                "done": bool(sub.get("submitted_at") or sub.get("workflow_state") in ("submitted", "graded")),
            })

        if not any(n in cname for n in online):
            continue
        for m in canvas.get(f"/courses/{c['id']}/modules", **{"include[]": "items"}):
            wk = re.match(r"(\d+)주차", m["name"])
            if not wk or not this_week <= int(wk.group(1)) <= this_week + 1:
                continue
            due = lecture_deadline(m["name"], int(wk.group(1)), sem_start)
            for i in m.get("items", []):
                if i["type"] != "ExternalTool" or MATERIAL.search(i["title"]):
                    continue
                items.append({
                    "key": f"m{i['id']}", "kind": "lecture", "course": cname, "title": i["title"].strip(),
                    "due": due.isoformat(), "earliest": None, "minutes": minutes["lecture"],
                    "url": i.get("html_url", ""),
                })
    return items


def sync(conn):
    items = collect()
    db.sync_source(conn, "canvas", items)
    db.set_meta(conn, "canvas_synced_at", now().isoformat())
    return len(items)
