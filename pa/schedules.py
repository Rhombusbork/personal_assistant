"""고급 예약 — 할 일과 따로, 정한 시각에 AI 에게 지시하거나 만들어 둔 기능을 실행한다 (엔진이 30초마다, 일하는 PC 만).

동작 (action) · args:
  prompt        AI 에게 지시 · {prompt, folder}  — AI 는 읽기만 한다. 답은 엔진이 data/ai-results/ 에 파일로 저장 (🤖 작업 칸에서 열기)
  open_task     할 일 열기 (강의면 ▶ 재생까지 — 자동 열기와 같음) · {key}
  report_draft  보고서 초안 (✍ 와 같음, 지금 열지는 않음) · {key}
  summary       강의 자료 내용정리 · {key}
  notices       새 공지 정리 (AI)
  sync          Canvas 전체 확인
  timetable     학교 포털 시간표 읽기
  open_link     링크(https://…) 열기 또는 폴더를 VSCode 새 창으로 · {target}
  awake         그 시간 동안 PC 가 절전하지 않게 (pa/power.py)
반복: '' (한 번) · daily · weekly. 늦게 깨면 late_minutes(15) 안일 때만 실행, 더 늦으면 건너뛰고 기록 (schedule_missed).
"""
import json
import re
import subprocess
from datetime import timedelta
from pathlib import Path

from pa import db
from pa.config import ROOT, load_timetable
from pa.model import now, parse_dt

ACTIONS = {
    "prompt": "AI 에게 지시", "open_task": "할 일 열기 (강의는 ▶ 재생)", "report_draft": "보고서 초안", "summary": "자료 내용정리",
    "notices": "새 공지 정리", "sync": "Canvas 전체 확인", "timetable": "학교 시간표 읽기", "open_link": "링크·폴더 열기",
    "awake": "PC 깨어 있기",
}
NEEDS_TASK = {"open_task", "report_draft", "summary"}
EVERY = {"": "한 번", "daily": "매일", "weekly": "매주"}
RESULTS = ROOT / "data" / "ai-results"
LATE = timedelta(minutes=15)

def folders():
    """AI 지시를 할 수 있는 폴더 {이름: 경로} — 있는 것만. config/timetable.yaml 의 schedules.folders 로 바꿀 수 있음."""
    conf = (load_timetable().get("schedules") or {}).get("folders")
    base = conf or {"비서": str(ROOT), "공부 (study_system)": "~/study_system", "보고서 (report)": "~/report",
                    "퀴즈 (pharmacy)": "~/quiz_system_project/pharmacy", "HRA": "~/hra"}
    out = {}
    for name, p in base.items():
        path = Path(p).expanduser()
        if path.is_dir():
            out[name] = path
    return out


def _row(r):
    d = dict(r)
    d["args"] = json.loads(d.get("args") or "{}")
    return d


def all_rows(conn):
    return [_row(r) for r in conn.execute("SELECT * FROM schedules ORDER BY start")]


def get(conn, sid):
    r = conn.execute("SELECT * FROM schedules WHERE id = ?", (sid,)).fetchone()
    return _row(r) if r else None


def validate(d):
    if d.get("action") not in ACTIONS:
        raise ValueError("무엇을 할지 골라 주세요")
    if d.get("every", "") not in EVERY:
        raise ValueError("반복이 올바르지 않음")
    s, e = parse_dt(d["start"]), parse_dt(d["end"])
    if not s or not e or e <= s or e - s > timedelta(hours=24):
        raise ValueError("시간이 올바르지 않아요 (끝이 시작보다 늦게, 하루 안에서)")
    a = d.get("args") or {}
    if d["action"] == "prompt":
        if not str(a.get("prompt", "")).strip():
            raise ValueError("AI 에게 할 말을 적어 주세요")
        if a.get("folder") not in folders():
            raise ValueError("작업 폴더를 골라 주세요")
    if d["action"] in NEEDS_TASK and not a.get("key"):
        raise ValueError("어떤 할 일인지 골라 주세요")
    if d["action"] == "open_link" and not str(a.get("target", "")).strip():
        raise ValueError("열 링크나 폴더를 적어 주세요")
    return s, e


def save(conn, d):
    """새로 만들거나(id 없음) 고친다. → id"""
    s, e = validate(d)
    title = (d.get("title") or "").strip() or ACTIONS[d["action"]]
    args = json.dumps(d.get("args") or {}, ensure_ascii=False)
    if d.get("id"):
        conn.execute("UPDATE schedules SET title=?, start=?, end=?, every=?, action=?, args=?, enabled=1, "
                     "last_run = CASE WHEN start = ? THEN last_run ELSE NULL END WHERE id=?",
                     (title, s.isoformat(), e.isoformat(), d.get("every", ""), d["action"], args, s.isoformat(), int(d["id"])))
        sid = int(d["id"])
    else:
        sid = conn.execute("INSERT INTO schedules (title, start, end, every, action, args, created) VALUES (?,?,?,?,?,?,?)",
                           (title, s.isoformat(), e.isoformat(), d.get("every", ""), d["action"], args, now().isoformat())).lastrowid
    db.log(conn, "schedule_saved", f"s{sid}", title=title, action=d["action"], start=s.isoformat(), every=d.get("every", ""))
    return sid


def move(conn, sid, start, end, orig=None):
    """시간표에서 끌어 옮김. orig = 끌기 시작한 회차의 시작. 반복 예약은 모든 회차를 같은 만큼 옮긴다."""
    r = get(conn, sid)
    if not r:
        raise ValueError("예약이 없어졌어요 (화면을 새로 고쳐 주세요)")
    if end <= start or end - start > timedelta(hours=24):
        raise ValueError("시간이 올바르지 않아요")
    old = parse_dt(r["start"])
    shift = start - (orig or old)
    s, e = old + shift, old + shift + (end - start)
    conn.execute("UPDATE schedules SET start = ?, end = ?, last_run = NULL WHERE id = ?", (s.isoformat(), e.isoformat(), sid))
    db.log(conn, "schedule_moved", f"s{sid}", start=s.isoformat())


def delete(conn, sid):
    conn.execute("DELETE FROM schedules WHERE id = ?", (sid,))
    db.log(conn, "schedule_deleted", f"s{sid}")


def _step(r):
    return {"daily": timedelta(days=1), "weekly": timedelta(days=7)}.get(r["every"])


def occurrences(r, frm, to):
    """frm~to 사이에 시작하는 회차 [(시작, 끝)]."""
    s, e = parse_dt(r["start"]), parse_dt(r["end"])
    step = _step(r)
    if not step:
        return [(s, e)] if frm <= s < to else []
    if s < frm:
        k = (frm - s) // step
        s, e = s + step * k, e + step * k
    out = []
    while s < to:
        if s >= frm:
            out.append((s, e))
        s, e = s + step, e + step
    return out


def next_occurrence(r, after):
    got = occurrences(r, after, after + timedelta(days=400))
    return got[0][0] if got else None


def _latest_start(r, t_now):
    got = occurrences(r, t_now - timedelta(days=8), t_now + timedelta(seconds=1))
    return got[-1][0] if got else None


def tick(conn, t_now, runner=None):
    """때가 된 예약을 실행한다. [(id, 제목, 결과)]"""
    runner = runner or run_action
    done = []
    for r in all_rows(conn):
        if not r["enabled"]:
            continue
        s = _latest_start(r, t_now)
        last = parse_dt(r["last_run"]) if r["last_run"] else None
        if not s or (last and s <= last):
            continue
        conn.execute("UPDATE schedules SET last_run = ? WHERE id = ?", (s.isoformat(), r["id"]))
        if t_now - s > LATE:
            db.log(conn, "schedule_missed", f"s{r['id']}", title=r["title"], start=s.isoformat())
            continue
        try:
            what = runner(conn, r, s)
            db.log(conn, "schedule_run", f"s{r['id']}", title=r["title"], result=str(what)[:200])
            done.append((r["id"], r["title"], what))
        except Exception as e:  # 실패해도 엔진은 계속
            db.log(conn, "schedule_failed", f"s{r['id']}", title=r["title"], error=str(e)[:200])
    conn.commit()
    return done


def run_action(conn, r, occ):
    """예약 하나를 실행. 무엇을 했는지 짧은 글."""
    from pa import jobs, osutil, server
    a, act = r["args"], r["action"]
    task = None
    if act in NEEDS_TASK:
        row = conn.execute("SELECT * FROM tasks WHERE key = ?", (a.get("key"),)).fetchone()
        if not row:
            raise ValueError("할 일을 찾지 못함 (끝냈거나 없어짐)")
        task = dict(row)
    if act == "prompt":
        jid = jobs.enqueue(conn, "prompt", f"s{r['id']}@{occ.isoformat()}", r["title"])
        return f"AI 작업 #{jid}"
    if act == "open_task":
        from pa import autoopen
        return ", ".join(autoopen.open_task(conn, task)) or "열 것이 없음"
    if act == "report_draft":
        return f"초안 작업 #{jobs.enqueue(conn, 'report-auto', task['key'], task['title'])}"
    if act == "summary":
        out = server.side_action("/api/job/summary-for", {"key": task["key"]}, remote=True)
        return out.get("message") or ("자료를 골라야 함" if out.get("choose") else "내용정리 맡김")
    if act == "notices":
        server.side_action("/api/job/notices", {}, remote=True)
        return "공지 정리 맡김"
    if act == "sync":
        server.side_action("/api/sync", {}, remote=True)
        return "Canvas 확인 시작"
    if act == "timetable":
        subprocess.Popen(osutil.pa_command("timetable"), cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "시간표 읽기 시작"
    if act == "open_link":
        target = str(a["target"]).strip()
        if re.match(r"https?://", target):
            osutil.open_url(target)
            return "링크 열기"
        folder = Path(target).expanduser()
        if not folder.is_dir():
            raise ValueError(f"폴더가 없음: {target}")
        osutil.launch_vscode(folder)
        return "폴더 열기"
    if act == "awake":
        from pa import power
        mins = int((parse_dt(r["end"]) - parse_dt(r["start"])).total_seconds() // 60)
        power.keep_awake(mins)
        return f"{mins}분 깨어 있기"
    raise ValueError(f"모르는 동작: {act}")


def prompt_job(conn, job):
    """jobs 의 'prompt' 작업: 예약한 지시를 AI 에게 (읽기만) → 답을 data/ai-results/ 에 저장. 파일 경로 반환."""
    from pa import ai
    sid = int(re.match(r"s(\d+)@", job["key"]).group(1))
    r = get(conn, sid)
    if not r:
        raise ValueError("예약이 지워짐")
    folder = folders().get(r["args"].get("folder"))
    if not folder:
        raise ValueError("작업 폴더가 없음")
    text = ai.ask(r["args"]["prompt"] + "\n\n(결과는 답으로만 낸다 — 파일을 고치거나 명령을 실행하지 않는다)",
                  cwd=folder, add_dirs=[folder], timeout=900)
    conn.execute("UPDATE jobs SET claude = claude + 1 WHERE id = ?", (job["id"],))
    RESULTS.mkdir(parents=True, exist_ok=True)
    t = now()
    safe = re.sub(r"[\\/:*?\"<>|\s]+", "_", r["title"]).strip("_")[:40] or "AI"
    out = RESULTS / f"{t:%Y-%m-%d_%H%M}_{safe}.md"
    out.write_text(f"# {r['title']}\n\n- 예약 실행 {t:%Y-%m-%d %H:%M} · 폴더 {r['args'].get('folder')} · {ai.name()}\n"
                   f"- 지시: {r['args']['prompt']}\n\n---\n\n{text.strip()}\n", encoding="utf-8")
    return out


def blocks(conn, frm, to):
    """시간표·화면용 회차 [{id, title, start, end, action, every, args}]."""
    out = []
    for r in all_rows(conn):
        if not r["enabled"]:
            continue
        for s, e in occurrences(r, frm, to):
            out.append({"id": r["id"], "title": r["title"], "start": s.isoformat(), "end": e.isoformat(),
                        "action": r["action"], "every": r["every"], "args": r["args"]})
    return sorted(out, key=lambda x: x["start"])


def listing(conn, t_now=None):
    """화면의 '예약' 목록: 다음 회차 · 마지막 결과."""
    t_now = t_now or now()
    last = {}
    for ev in conn.execute("SELECT key, type, ts, detail FROM events WHERE type IN ('schedule_run', 'schedule_failed', 'schedule_missed') ORDER BY id"):
        last[ev["key"]] = {"type": ev["type"], "ts": ev["ts"], **json.loads(ev["detail"] or "{}")}
    out = []
    for r in all_rows(conn):
        nxt = next_occurrence(r, t_now)
        out.append({**r, "next": nxt.isoformat() if nxt else None, "last": last.get(f"s{r['id']}"),
                    "actionName": ACTIONS.get(r["action"], r["action"]), "everyName": EVERY.get(r["every"], "")})
    return out
