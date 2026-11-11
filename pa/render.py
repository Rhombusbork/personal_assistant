"""출력 블록: TODAY.md (VSCode 미리보기용)."""
import json
from datetime import timedelta

from pa import db
from pa.config import ROOT, load_timetable
from pa.model import KIND_LABEL, kday, label, now, parse_dt

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
