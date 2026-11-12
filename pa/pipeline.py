"""자동 실행 블록.

run(full)  휴대폰 입력 → inbox → 퀴즈 기록 → (full 이면 Canvas·공지·자료) → 계획 → 마감 캘린더
           → TODAY.md·대시보드 → 휴대폰. 단계마다 따로 — 한 단계가 실패해도 나머지는 돈다.
watch()    시작할 때 full 실행 후, inbox.md 가 저장될 때마다 빠른 실행, PLAN_EVERY 마다 확인,
           CANVAS_EVERY 마다 full 실행, 대시보드 서버(pa/server.py)도 함께.
           pa/*.py 가 바뀌면 스스로 다시 시작한다 (VSCode 를 다시 열 필요 없음).
           VSCode 작업 공간을 열면 자동으로 켜진다.
"""
import fcntl
import os
import sys
import threading
import time
import traceback
from datetime import datetime

from pa import collect_canvas, db, deadlines, inbox, jobs, learningx, materials, mobile, plan, quiz, render, server
from pa.canvas import CanvasAuthError
from pa.config import ROOT
from pa.gcal import GoogleAuthError, get_service

CANVAS_EVERY = 3 * 60 * 60  # 초
PLAN_EVERY = 15 * 60        # 이때마다 '다시 계획할 필요가 있나' 확인 (필요할 때만 Google 에 요청)
PHONE_EVERY = 3 * 60
DOWNLOADS_EVERY = 30
POLL = 1.0

LOG_FILE = db.PATH.parent / "pa.log"


def log(msg):
    line = f"[{datetime.now():%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:  # 창 없이(작업 스케줄러) 돌 때도 남도록 파일에도. 1MB 넘으면 뒤쪽 절반만 남김
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 1_000_000:
            LOG_FILE.write_text(LOG_FILE.read_text()[-500_000:])
        with LOG_FILE.open("a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def run(full=False, force_plan=False):
    # 실행은 한 번에 하나만 (감시기·수동 실행·작업 스케줄러가 겹쳐도 캘린더에 중복으로 쓰지 않게)
    db.PATH.parent.mkdir(exist_ok=True)
    with open(db.PATH.parent / "run.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _run(full, force_plan or full)


def _run(full, force_plan):
    conn = db.connect()
    steps, errors = [], []

    def step(name, fn):
        """한 단계 실행. 실패하면 기록만 하고 다음 단계로."""
        try:
            return fn()
        except (GoogleAuthError, CanvasAuthError) as e:
            errors.append(str(e))
        except Exception as e:  # 네트워크 오류 등
            errors.append(f"{name}: {e}")
            traceback.print_exc()
        return None

    try:
        n = step("휴대폰 입력", mobile.pull_phone_inbox)
        if n:
            steps.append(f"휴대폰 입력 {n}")
        warns = step("inbox", lambda: inbox.sync(conn))
        steps.append(f"inbox{' ⚠️' + str(len(warns)) if warns else ''}")
        n = step("퀴즈 기록", lambda: quiz.sync(conn))
        if n:
            steps.append(f"퀴즈 기록 +{n}")
        if full:
            n = step("Canvas", lambda: collect_canvas.sync(conn))
            if n is not None:
                steps.append(f"Canvas {n}건")
                conn.commit()
                n = step("공지", lambda: collect_canvas.sync_notices(conn))
                if n:
                    steps.append(f"새 공지 {n}")
                got = step("강의 자료", lambda: learningx.sync(conn, collect_canvas.online_courses()))
                if got:
                    steps.append(f"자료 +{got[0]}" + (f" ⚠️{got[1]}" if got[1] else ""))
        need_plan = force_plan or step("계획 확인", lambda: plan.needed(conn))
        need_deadlines = force_plan or step("마감 확인", lambda: deadlines.needed(conn))
        if need_plan or need_deadlines:
            service = step("Google", get_service)
            if service and need_plan:
                res = step("계획", lambda: plan.run(conn, service))
                if res:
                    steps.append(f"계획 {len(res[0])}건" + (f" (자리 부족 {len(res[1])})" if res[1] else ""))
            if service and need_deadlines:
                res = step("마감 캘린더", lambda: deadlines.sync(conn, service))  # 모든 마감 + 알림
                if res and any(res):
                    steps.append(f"마감 캘린더 +{res[0]} ~{res[1]} -{res[2]}")
        if errors:
            steps.append("⚠️ " + " / ".join(e[:60] for e in errors))
        db.set_meta(conn, "last_error", f"{datetime.now():%m/%d %H:%M} " + " / ".join(errors) if errors else "")
        conn.commit()
    finally:
        try:
            render.write(conn)
        finally:
            conn.close()
    try:
        if mobile.publish():
            steps.append("휴대폰 화면 올림")
    except Exception as e:  # 인터넷·GitHub 문제로 나머지가 멈추지 않게
        steps.append(f"휴대폰 화면 올리기 실패: {str(e)[:80]}")
    log(" · ".join(steps))


def _pull_phone():
    """휴대폰 입력(GitHub phone-inbox)을 inbox.md 로. 실패해도 계속."""
    try:
        return mobile.pull_phone_inbox()
    except Exception as e:
        log(f"휴대폰 입력 가져오기 실패: {str(e)[:80]}")
        return 0


def _mtime():
    try:
        return inbox.PATH.stat().st_mtime
    except FileNotFoundError:
        return 0


def _code_mtime():
    return max(p.stat().st_mtime for p in (ROOT / "pa").glob("*.py"))


def _download_watcher():
    """다운로드 폴더를 30초마다 (맨 위만) — 새 자료 알림 + 최근 받은 파일 목록을 기억해 둔다.
    자료 연결 창은 이 기억을 쓰므로 Windows 폴더를 따로 열지 않는다."""
    while True:
        conn = db.connect()
        try:
            materials.scan_downloads(conn)
        except Exception as e:
            log(f"다운로드 폴더 확인 실패: {e}")
        finally:
            conn.close()
        time.sleep(DOWNLOADS_EVERY)


def _job_runner():
    """에이전트 작업을 하나씩 처리하는 스레드 (보고서 초안 등은 몇 분 걸릴 수 있음)."""
    conn = db.connect()
    jobs.reset_stuck(conn)
    while True:
        try:
            if jobs.run_next(conn):
                log("에이전트 작업 하나 처리")
                continue
        except Exception as e:
            log(f"작업 처리 오류: {e}")
        time.sleep(2)


def _restart_if_code_changed(state):
    """pa/*.py 가 바뀌었고 (3초 동안 더 안 바뀜) 진행 중인 에이전트 작업이 없으면 새 코드로 다시 시작."""
    m = _code_mtime()
    if m == state["code"]:
        return
    if time.time() - m < 3:
        return  # 아직 저장 중일 수 있음
    conn = db.connect()
    try:
        busy = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'running'").fetchone()[0]
    finally:
        conn.close()
    if busy:
        return  # 보고서 초안 등이 끝난 뒤에
    log("코드가 바뀌어 엔진을 새 코드로 다시 시작합니다")
    os.execv(sys.executable, [sys.executable, "-m", "pa", "watch"])  # 잠금·서버는 새 프로세스가 다시 잡는다


def watch():
    # 감시기는 하나만 (VSCode 창을 여러 개 열어도 캘린더에 중복으로 쓰지 않게)
    lock = open(db.PATH.parent / "watch.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("이미 다른 창에서 감시 중 — 이 창에서는 실행하지 않습니다.")
        return

    seen = {"mtime": _mtime()}
    code_state = {"code": _code_mtime()}

    def after_input():
        # 대시보드 입력 → 다음 순환에서 한 번만 다시 계획 (연달아 눌러도 한 번으로 합침)
        seen["mtime"] = _mtime()  # inbox 저장 감지로 또 돌지 않게
        seen["dirty"] = True

    if server.start(after_input, on_sync=lambda: run(full=True)):
        log(f"대시보드: http://localhost:{server.PORT}")
    else:
        log(f"포트 {server.PORT} 사용 중 — 대시보드 서버는 켜지 않음")
    threading.Thread(target=_download_watcher, daemon=True).start()
    threading.Thread(target=_job_runner, daemon=True).start()
    log("비서 감시 시작 — inbox.md 저장 시 반영, 15분마다 확인(바뀐 게 있을 때만 다시 계획), Canvas 3시간마다")
    # 다시 시작(코드 변경)한 경우엔 방금 full 을 했을 수 있으니, 마지막 Canvas 확인 시각을 본다
    conn = db.connect()
    try:
        last = db.get_meta(conn, "canvas_synced_at")
    finally:
        conn.close()
    from pa.model import now, parse_dt
    recent = last and (now() - parse_dt(last)).total_seconds() < CANVAS_EVERY
    run(full=not recent)
    last_full = time.time() if not recent else time.time() - (now() - parse_dt(last)).total_seconds()
    last_plan = last_phone = last_code = time.time()
    while True:
        time.sleep(POLL)
        if time.time() - last_code >= 5:
            last_code = time.time()
            _restart_if_code_changed(code_state)
        if time.time() - last_phone >= PHONE_EVERY:  # 휴대폰 입력이 있으면 바로 반영
            last_phone = time.time()
            if _pull_phone():
                seen["mtime"] = _mtime()
                seen["dirty"] = True
        if seen.pop("dirty", False):
            log("입력 반영")
            run(full=False)
            last_plan = time.time()
        mtime = _mtime()
        if mtime and mtime != seen["mtime"]:
            time.sleep(0.5)  # 저장이 끝나길 잠깐 기다림
            seen["mtime"] = _mtime()
            log("inbox.md 저장 감지")
            run(full=False)
            last_plan = time.time()
        if time.time() - last_full >= CANVAS_EVERY:
            run(full=True)
            last_full = last_plan = time.time()
        elif time.time() - last_plan >= PLAN_EVERY:
            run(full=False)  # 바뀐 게 없으면 Google 에 요청하지 않고 화면만 갱신
            last_plan = time.time()
