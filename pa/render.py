"""출력 블록: TODAY.md (VSCode 미리보기용), dashboard/data.js (HTML 대시보드용)."""
import json
import re
from datetime import datetime, timedelta

from pa import calibrate, db, jobs, materials, quiz
from pa.config import ROOT, load_timetable
from pa.model import KIND_LABEL, kday, label, now, parse_dt, short_course

TODAY_PATH = ROOT / "TODAY.md"
EVENT_LABEL = {"task_added": "🆕 새 항목", "task_done": "✅ 완료", "task_ignored": "🚫 제외",
               "task_reopened": "↩️ 다시 열림", "task_removed": "🗑 삭제", "due_changed": "🔁 마감 변경",
               "plan_missed": "⏭ 계획 놓침"}


def dday(due, t_now):
    days = (due.date() - t_now.date()).days
    if days == 0:
        return "🔴 오늘"
    return f"🟠 D-{days}" if days <= 2 else f"D-{days}"


def load_plan(conn):
    return [(r["key"], parse_dt(r["start"]), parse_dt(r["end"]), r["summary"])
            for r in conn.execute("SELECT * FROM plan ORDER BY start")]


def today_md(conn):
    t_now = now()
    cfg = load_timetable()["planner"]
    tasks = {t.key: t for t in db.tasks(conn)}
    open_due = [t for t in tasks.values() if t.status == "open" and t.due and t.due >= t_now]
    plan = load_plan(conn)
    busy = [(parse_dt(r["start"]), parse_dt(r["end"]), r["label"]) for r in conn.execute("SELECT * FROM busy")]
    today = t_now.date()
    today_plan = [p for p in plan if p[1].date() == today]
    today_min = sum(int((e - s).total_seconds() // 60) for _, s, e, _ in today_plan)

    L = [f"# {kday(t_now)} 오늘",
         "",
         f"> 남은 할 일 **{len(open_due)}** · 오늘 계획 **{today_min // 60}시간 {today_min % 60}분** / 한도 "
         f"{cfg['max_minutes_per_day'] // 60}시간 · 갱신 {t_now:%H:%M}"
         f" · Canvas 확인 {fmt_time(db.get_meta(conn, 'canvas_synced_at'))}",
         "> 입력은 [inbox.md](inbox.md) 에서 — 저장하면 자동 반영",
         ""]

    # 주의할 것
    warns = [w for w in (db.get_meta(conn, "inbox_warnings") or "").split("\n") if w]
    failed = [tasks[k] for k in (db.get_meta(conn, "plan_failed") or "").split(",") if k in tasks]
    if warns or failed:
        L += ["## ⚠️ 확인 필요", ""]
        L += [f"- {w}" for w in warns]
        L += [f"- 마감 전 빈 시간 부족: **{label(t)}** (마감 {kday(t.due)} {t.due:%H:%M}) `{t.key}`" for t in failed]
        L.append("")

    # 오늘 일정 (수업·약속 + 학습 계획)
    rows = [(s, e, f"🏫 {n}", "") for s, e, n in busy if s.date() == today]
    for k, s, e, summ in today_plan:
        t = tasks.get(k.split("#")[0])
        rows.append((s, e, summ, f"{dday(t.due, t_now)} {t.due:%H:%M}" if t else ""))
    L += ["## 📅 오늘 일정", ""]
    if rows:
        L += ["| 시간 | 내용 | 마감 |", "|---|---|---|"]
        for s, e, what, due in sorted(rows):
            mark = " ◀ 지금" if s <= t_now < e else ""
            L.append(f"| {s:%H:%M}–{e:%H:%M} | {what}{mark} | {due} |")
    else:
        L.append("오늘 남은 일정이 없습니다.")
    L.append("")

    # 3일 안 마감
    soon = [t for t in open_due if (t.due.date() - today).days <= 3]
    L += ["## ⏰ 3일 안 마감", ""]
    L += [f"- {dday(t.due, t_now)} {t.due:%H:%M} · [{KIND_LABEL[t.kind]}] {label(t)} `{t.key}`" for t in soon] or ["없음"]
    L.append("")

    # 앞으로의 계획 (오늘 이후)
    L += ["## 🗓 앞으로의 계획", ""]
    day = None
    for k, s, e, summ in plan:
        if s.date() <= today:
            continue
        if s.date() != day:
            day = s.date()
            L.append(f"\n**{kday(s)}**\n")
        L.append(f"- {s:%H:%M}–{e:%H:%M} {summ}")
    L.append("")

    # 기한 없는 할 일
    someday = [t for t in tasks.values() if t.status == "open" and not t.due]
    if someday:
        L += ["## 📌 기한 없는 할 일", ""] + [f"- {label(t)}" for t in someday] + [""]

    # 최근 변화 (24시간)
    since = (t_now - timedelta(hours=24)).isoformat()
    evs = conn.execute("SELECT * FROM events WHERE ts >= ? AND type IN ({}) ORDER BY id DESC LIMIT 15".format(
        ",".join("?" * len(EVENT_LABEL))), (since, *EVENT_LABEL)).fetchall()
    if evs:
        L += ["## 🧾 최근 24시간 기록", ""]
        for ev in evs:
            t = tasks.get(ev["key"])
            name = label(t) if t else ev["key"]
            extra = ""
            if ev["type"] == "due_changed" and ev["detail"]:
                d = json.loads(ev["detail"])
                extra = f" ({fmt_time(d.get('old'))} → {fmt_time(d.get('new'))})"
            L.append(f"- {parse_dt(ev['ts']):%H:%M} {EVENT_LABEL[ev['type']]} {name}{extra}")
        L.append("")

    L += ["---", "", "<sub>자동 생성 파일 — 직접 고치지 마세요. 완료·제외는 inbox.md 의 `## 완료`, `## 제외` 에 키를 적으면 됩니다.</sub>", ""]
    return "\n".join(L)


def fmt_time(iso):
    dt = parse_dt(iso) if iso else None
    return f"{kday(dt)} {dt:%H:%M}" if dt else "-"


def write(conn):
    TODAY_PATH.write_text(today_md(conn))
    write_dashboard(conn)


DASH_DATA = ROOT / "dashboard" / "data.js"


def dashboard_data(conn):
    t_now = now()
    cfg = load_timetable()["planner"]
    all_tasks = db.tasks(conn)
    by_key = {t.key: t for t in all_tasks}

    def task_json(t):
        return {"key": t.key, "kind": t.kind, "course": short_course(t.course), "title": t.title,
                "due": t.due.isoformat() if t.due else None, "status": t.status, "minutes": t.minutes,
                "source": t.source, "url": t.url}

    upcoming = [task_json(t) for t in all_tasks
                if t.status == "open" and t.due and t_now - timedelta(days=1) <= t.due <= t_now + timedelta(days=21)]
    why = json.loads(db.get_meta(conn, "plan_why") or "{}")
    plan = [{"key": k, "task": k.split("#")[0], "start": s.isoformat(), "end": e.isoformat(), "summary": summ,
             "why": why.get(k, ""), "kind": by_key[k.split("#")[0]].kind if k.split("#")[0] in by_key else "todo"}
            for k, s, e, summ in load_plan(conn)]
    busy = [{"start": r["start"], "end": r["end"], "label": r["label"]} for r in conn.execute("SELECT * FROM busy")]

    # 과목별 진행: 추적한 항목 중 완료 비율 (제외·삭제 빼고)
    progress = {}
    for t in all_tasks:
        if t.status in ("ignored", "gone") or not t.course:
            continue
        p = progress.setdefault(short_course(t.course), {"done": 0, "total": 0})
        p["total"] += 1
        p["done"] += t.status == "done"

    since = (t_now - timedelta(days=13)).date()
    done_by_day = {}
    for r in conn.execute("SELECT ts FROM events WHERE type = 'task_done' AND ts >= ?", (since.isoformat(),)):
        d = r["ts"][:10]
        done_by_day[d] = done_by_day.get(d, 0) + 1

    warns = [w for w in (db.get_meta(conn, "inbox_warnings") or "").split("\n") if w]
    if db.get_meta(conn, "last_error"):
        warns.append(f"마지막 동기화 실패: {db.get_meta(conn, 'last_error')} (자세한 내용: data/pa.log)")
    lx = db.get_meta(conn, "learningx_error") or db.get_meta(conn, "learningx_lecture_error")
    if lx and "로그인" in lx:  # 로그인 만료 → 다시 로그인 버튼
        warns.append(f"강의 플랫폼(LearningX) 로그인 필요: {lx}")
    elif lx:  # 시간 초과 같은 일시적 오류
        warns.append(f"강의 플랫폼 확인 중 일시적 오류 ({lx}) — 다음 확인 때 다시 시도합니다")
    warns += [f"마감 전 빈 시간 부족: {label(by_key[k])}" for k in (db.get_meta(conn, "plan_failed") or "").split(",")
              if k in by_key]
    return {
        "generated": t_now.isoformat(), "canvasSynced": db.get_meta(conn, "canvas_synced_at"),
        "cap": cfg["max_minutes_per_day"], "dayStart": cfg["day_start"], "dayEnd": cfg["day_end"],
        "tasks": upcoming, "plan": plan, "busy": busy, "warnings": warns,
        "progress": [{"course": c, **v} for c, v in sorted(progress.items())],
        "doneByDay": done_by_day,
        "someday": [task_json(t) for t in all_tasks if t.status == "open" and not t.due],
        "plannedAt": db.get_meta(conn, "planned_at"),
        "courses": sorted({short_course(t.course) for t in all_tasks if t.course}),
        "active": active_json(conn, by_key),
        "downloads": materials.pending_downloads(conn),
        "jobs": jobs.recent(conn),
        "excluded": inbox_excluded(conn),
        "quiz": quiz.status(conn),
        "semester": semester_weeks(all_tasks, t_now),
        "notices": [dict(r) for r in conn.execute(
            "SELECT id, course, title, posted_at, summary FROM notices WHERE status = 'new' ORDER BY posted_at DESC")],
        "suggestions": json.loads(db.get_meta(conn, "notice_suggestions") or "[]"),
        "slack": json.loads(db.get_meta(conn, "slack") or "null"),
        "calibration": calibrate.describe(conn),
        "eveningReview": cfg.get("evening_review", "21:00"),
        "recent": recent_changes(conn, by_key, t_now),
        "courseFolders": [c["match"][0] for c in materials._cfg()["courses"]],
        "todayDone": [task_json(by_key[r["key"]]) for r in conn.execute(
            "SELECT key FROM tasks WHERE status = 'done' AND done_at >= ? ORDER BY done_at",
            (t_now.replace(hour=0, minute=0).isoformat(),)) if r["key"] in by_key],
        "sessionsToday": [dict(r) for r in conn.execute(
            "SELECT key, start, end, minutes FROM sessions WHERE start >= ? ORDER BY start",
            (t_now.replace(hour=0, minute=0).isoformat(),))],
    }


CHANGE_LABEL = {"task_added": "🆕 새로 생김", "due_changed": "🔁 마감 바뀜", "material_downloaded": "📥 자료 받음",
                "job_done": "🤖 작업 완료"}


def recent_changes(conn, by_key, t_now):
    """지난 24시간 동안 바뀐 것 (아침 브리핑용). 자동 완료(제출·수강 감지)도 포함."""
    rows = conn.execute("SELECT ts, type, key, detail FROM events WHERE ts >= ? ORDER BY id DESC LIMIT 60",
                        ((t_now - timedelta(hours=24)).isoformat(),)).fetchall()
    out = []
    for r in rows:
        d = json.loads(r["detail"]) if r["detail"] else {}
        t = by_key.get(r["key"])
        name = label(t) if t else d.get("file") or r["key"] or ""
        if r["type"] == "task_done" and d.get("by") == "auto":
            out.append({"ts": r["ts"], "label": "✅ 자동 완료 (제출·수강 확인)", "name": name})
        elif r["type"] in CHANGE_LABEL and not (r["type"] == "task_added" and t and t.source == "inbox"):
            out.append({"ts": r["ts"], "label": CHANGE_LABEL[r["type"]], "name": name})
    return out[:20]


EXAM = re.compile(r"(?<!임상)시험|고사")  # '임상시험' 같은 말은 시험이 아님


def semester_weeks(all_tasks, t_now):
    """종강까지 주별 마감 (지난 주 포함 — 이번 학기 전체 모습)."""
    tt = load_timetable()
    start = datetime.fromisoformat(tt["semester_start"]).date()
    end = datetime.fromisoformat(tt["semester_end"]).date()
    start -= timedelta(days=start.weekday())  # 월요일부터
    weeks = []
    d = start
    while d <= end:
        nxt = d + timedelta(days=7)
        its = [{"key": t.key, "title": t.title, "course": short_course(t.course), "kind": t.kind, "status": t.status,
                "due": t.due.isoformat(), "url": t.url, "source": t.source, "minutes": t.minutes,
                "exam": bool(EXAM.search(t.title)) and "@복습" not in t.key}
               for t in all_tasks if t.due and d <= t.due.date() < nxt and t.status in ("open", "done")
               and "@복습" not in t.key]
        weeks.append({"start": d.isoformat(), "items": sorted(its, key=lambda x: x["due"]),
                      "minutes": sum(t.minutes for t in all_tasks if t.due and d <= t.due.date() < nxt and t.status == "open")})
        d = nxt
    return weeks


def inbox_excluded(conn):
    from pa import inbox
    try:
        return inbox.excluded(conn)
    except OSError:
        return []


def active_json(conn, by_key):
    row = db.active_session(conn)
    if not row:
        return None
    t = by_key.get(row["key"])
    return {"key": row["key"], "start": row["start"], "title": label(t) if t else row["key"],
            "kind": t.kind if t else "todo", "estimate": t.minutes if t else None}


def write_dashboard(conn):
    DASH_DATA.parent.mkdir(exist_ok=True)
    data = json.dumps(dashboard_data(conn), ensure_ascii=False, indent=1)
    DASH_DATA.write_text(f"// 자동 생성 — 직접 고치지 마세요\nwindow.PA_DATA = {data};\n")
