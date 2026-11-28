"""학습 계획 블록이 시작되면 그 일을 PC 에서 열어 준다 — 정해 둔 시간에 까먹지 않게 (엔진이 30초마다 확인).

  강의     → 강의 페이지 (평소 브라우저, 학교 로그인이 남아 있는 곳) + 플레이어 ▶ 누르기 (pa/autoplay.py)
  퀴즈     → Canvas 퀴즈 페이지 / 퀴즈 복습 → 퀴즈 앱
  과제     → 미리 써 둔 초안 파일 + 탐색기(파일 선택된 채) + Canvas 제출 페이지

- 과제 초안은 블록 draft_hours_before 시간 전에 미리 쓴다 (대시보드 ✍ 와 같은 작업, 그때는 열지 않음).
- 여는 것까지만 한다. 강의 시청·퀴즈 풀이·제출은 사용자가 한다.
- PC 가 꺼져 있으면 아무것도 안 한다 (휴대폰에는 Google Calendar 블록 알림이 간다: reminders.plan_minutes_before).
- 노트북이 자다가 늦게 깨면 late_limit_minutes 안일 때만 연다. 그보다 늦으면 열지 않고 기록만 (autoopen_missed).
- 블록마다 한 번만 (meta 'autoopen:<계획 키>:<시작>').

설정: config/timetable.yaml 의 auto_open (없으면 꺼짐).
"""
import threading
from datetime import timedelta

from pa import db, osutil
from pa.config import load_timetable
from pa.model import parse_dt

DEFAULTS = {"lecture": True, "play": True, "quiz": True, "assignment": True, "draft_hours_before": 3, "late_limit_minutes": 15,
            "watch": True, "idle_seconds": 120, "speed": {}, "exam_check_minutes": 30}


def cfg():
    c = load_timetable().get("auto_open")
    if not c or c.get("enabled") is False:
        return None
    return {**DEFAULTS, **c}


def _kind_on(c, kind):
    return c["quiz"] if kind in ("quiz", "review") else bool(c.get(kind))


def _blocks(conn):
    """(계획 키, 시작, 끝, 할 일) — 아직 남은 할 일의 블록만."""
    for p in conn.execute("SELECT key, start, end FROM plan ORDER BY start").fetchall():
        t = conn.execute("SELECT * FROM tasks WHERE key = ? AND status = 'open'", (p["key"].split("#")[0],)).fetchone()
        if t:
            yield p["key"], parse_dt(p["start"]), parse_dt(p["end"]), dict(t)


def open_task(conn, task):
    """그 일을 연다. 무엇을 열었는지 목록으로 돌려준다."""
    from pa import jobs, materials, quiz
    opened = []
    if task["kind"] == "assignment":
        path = jobs.report_path(task, conn) if task["source"] == "canvas" else None
        if path and path.exists():
            materials.open_file(path)
            materials.reveal(path)
            opened += ["초안", "탐색기"]
    if task["kind"] == "quiz":
        from pa import quizhelp
        if quizhelp.start(conn, task):
            opened.append("퀴즈 도움")
    url = quiz.cfg()["url"] if task["kind"] == "review" else task["url"]
    if url:
        osutil.open_url(url)
        opened.append("제출 페이지" if task["kind"] == "assignment" else "페이지")
    if url and task["kind"] == "lecture" and (cfg() or {}).get("play"):
        threading.Thread(target=_play, args=(task["title"], task.get("_end"), task.get("course", "")), daemon=True).start()
        opened.append("재생")
    return opened


def _play(title, end=None, course=""):
    """▶ → (과목 배속) → 블록 동안 절전 막기 · 확인창 지켜보기 (자리에 없으면 누르지 않고 알림)."""
    from pa import autoplay, power
    from pa.model import now
    from pa.pipeline import log
    c = cfg() or DEFAULTS
    if autoplay.play_when_ready(title, log=log) not in ("invoked", "clicked"):
        return
    speed = next((v for k, v in (c.get("speed") or {}).items() if k and k in (course or "")), None)
    if speed:
        time.sleep(3)
        autoplay.set_speed(title, speed, log=log)
    until = parse_dt(end) if end else None
    if until and until > now():
        power.keep_awake(int((until - now()).total_seconds() // 60) + 5)
        if c.get("watch"):
            def alert(msg):
                conn = db.connect()
                try:
                    db.log(conn, "lecture_alert", None, msg=msg)
                    conn.commit()
                finally:
                    conn.close()
                log(msg)
            autoplay.watch(title, until, idle_limit=int(c.get("idle_seconds", 120)), log=log, alert=alert)


def ended(conn, t_now, window=timedelta(minutes=10)):
    """방금 끝난 강의·퀴즈·과제 블록의 할 일 키 (블록마다 한 번) → 엔진이 수강·제출을 바로 확인한다 ('끝날 때')."""
    keys = []
    for pkey, start, end, task in _blocks(conn):
        if task["kind"] in ("lecture", "quiz", "assignment") and task["source"] == "canvas" and end <= t_now < end + window:
            mark = f"autoopen:end:{pkey}:{end.isoformat()}"
            if not db.get_meta(conn, mark):
                db.set_meta(conn, mark, t_now.isoformat())
                keys.append(task["key"])
    conn.commit()
    return keys


def precheck(conn, t_now):
    """퀴즈·시험 블록 exam_check_minutes(30)분 전 점검 (한 번): 배터리·충전 · 인터넷·Canvas · 그 시간 동안 절전 막기.
    걸리는 것을 events 'exam_check' 로 (대시보드 알림). 시험 중에는 아무것도 대신 누르지 않는다."""
    c = cfg()
    if not c:
        return []
    ahead = timedelta(minutes=float(c.get("exam_check_minutes", 30)))
    out = []
    for pkey, start, end, task in _blocks(conn):
        if task["kind"] != "quiz" or not (start - ahead <= t_now < start - ahead + timedelta(minutes=10)):
            continue
        mark = f"autoopen:check:{pkey}:{start.isoformat()}"
        if db.get_meta(conn, mark):
            continue
        db.set_meta(conn, mark, t_now.isoformat())
        from pa import canvas, power
        issues = []
        pct, plugged = power.battery()
        if pct is not None and not plugged and pct < 80:
            issues.append(f"배터리 {pct}% — 충전기를 꽂아 두세요")
        try:
            canvas.get("/users/self")
        except Exception as e:
            issues.append(f"Canvas 연결 안 됨 ({str(e)[:60]}) — 인터넷·로그인 확인")
        power.keep_awake(int((end - t_now).total_seconds() // 60) + 10)
        db.log(conn, "exam_check", task["key"], title=task["title"], start=start.isoformat(), issues=issues)
        out.append((task["title"], issues))
    conn.commit()
    return out


def review_due(conn, t_now):
    """하루 마무리 블록이 막 시작됨 (블록마다 한 번) → 엔진이 대시보드를 띄운다 (사용자가 정함: 그 시간이 되면 띄워 주기)."""
    for p in conn.execute("SELECT key, start, end FROM plan WHERE key LIKE 'h:하루 마무리@%'"):
        s, e = parse_dt(p["start"]), parse_dt(p["end"])
        mark = f"autoopen:{p['key']}"
        if s <= t_now < e and not db.get_meta(conn, mark):
            db.set_meta(conn, mark, t_now.isoformat())
            conn.commit()
            return True
    return False


def check(conn, t_now, opener=open_task, viewing=True):
    """지금 시작한 블록을 열고, 곧 시작할 과제 블록의 초안을 미리 맡긴다. 연 할 일 키 목록을 돌려준다.
    viewing: PC 대시보드가 열려 있나. 닫혀 있으면 열지 않는다 (2026-11-28 사용자가 정함 — VSCode 를 닫아도 그렇게).
    표시를 남기지 않으므로 늦게(late_limit_minutes 안에) 대시보드를 열면 그때 연다."""
    c = cfg()
    if not c:
        return []
    from pa import jobs
    late = timedelta(minutes=int(c["late_limit_minutes"]))
    draft_before = timedelta(hours=float(c["draft_hours_before"] or 0))
    done = []
    for pkey, start, end, task in _blocks(conn):
        if not _kind_on(c, task["kind"]):
            continue
        if (draft_before and task["kind"] == "assignment" and task["source"] == "canvas"
                and start - draft_before <= t_now < start and not db.get_meta(conn, "autodraft:" + task["key"])):
            db.set_meta(conn, "autodraft:" + task["key"], t_now.isoformat())
            if not jobs.report_path(task, conn).exists():
                jobs.enqueue(conn, "report-auto", task["key"], task["title"])
        if not start <= t_now < end:
            continue
        mark = f"autoopen:{pkey}:{start.isoformat()}"
        if db.get_meta(conn, mark):
            continue
        if not viewing and t_now - start <= late:
            continue
        db.set_meta(conn, mark, t_now.isoformat())
        if t_now - start > late:
            db.log(conn, "autoopen_missed", task["key"], start=start.isoformat())
            continue
        try:
            what = opener(conn, {**task, "_end": end.isoformat()})
            db.log(conn, "autoopen", task["key"], opened=what, start=start.isoformat(), end=end.isoformat())
            done.append(task["key"])
        except Exception as e:  # 열기 실패해도 엔진은 계속
            db.log(conn, "autoopen_failed", task["key"], error=str(e)[:200])
    conn.commit()
    return done
