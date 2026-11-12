"""출력 블록: TODAY.md (VSCode 미리보기용), dashboard/data.js (HTML 대시보드용)."""
import json
from datetime import timedelta

from pa import db, jobs, materials
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
        t = tasks.get(k)
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
    plan = [{"key": k, "start": s.isoformat(), "end": e.isoformat(), "summary": summ,
             "kind": by_key[k].kind if k in by_key else "todo"} for k, s, e, summ in load_plan(conn)]
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
    lx = db.get_meta(conn, "learningx_error") or db.get_meta(conn, "learningx_lecture_error")
    if lx:
        warns.append(f"강의 플랫폼(LearningX) 연결 문제: {lx} — 터미널에서 bin/pa browser login 으로 다시 로그인")
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
        "courseFolders": [c["match"][0] for c in materials._cfg()["courses"]],
        "todayDone": [task_json(by_key[r["key"]]) for r in conn.execute(
            "SELECT key FROM tasks WHERE status = 'done' AND done_at >= ? ORDER BY done_at",
            (t_now.replace(hour=0, minute=0).isoformat(),)) if r["key"] in by_key],
        "sessionsToday": [dict(r) for r in conn.execute(
            "SELECT key, start, end, minutes FROM sessions WHERE start >= ? ORDER BY start",
            (t_now.replace(hour=0, minute=0).isoformat(),))],
    }


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
