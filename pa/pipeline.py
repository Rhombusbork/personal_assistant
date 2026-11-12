"""자동 실행 블록.

run(full)  inbox → (full 이면 Canvas·과제 캘린더) → 계획 → TODAY.md·대시보드
watch()    시작할 때 full 실행 후, inbox.md 가 저장될 때마다 빠른 실행,
           PLAN_EVERY 마다 계획 갱신, CANVAS_EVERY 마다 full 실행, 대시보드 서버(pa/server.py)도 함께.
           VSCode 작업 공간을 열면 자동으로 켜진다.
"""
import fcntl
import threading
import time
import traceback
from datetime import datetime

from pa import collect_canvas, db, inbox, jobs, learningx, materials, plan, render, server, sync_canvas
from pa.gcal import get_service

CANVAS_EVERY = 3 * 60 * 60  # 초
PLAN_EVERY = 15 * 60
POLL = 1.0


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def run(full=False):
    # 실행은 한 번에 하나만 (감시기·수동 실행·작업 스케줄러가 겹쳐도 캘린더에 중복으로 쓰지 않게)
    db.PATH.parent.mkdir(exist_ok=True)
    with open(db.PATH.parent / "run.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _run(full)


def _run(full):
    conn = db.connect()
    steps = []
    try:
        warns = inbox.sync(conn)
        steps.append(f"inbox{' ⚠️' + str(len(warns)) if warns else ''}")
        service = None
        if full:
            steps.append(f"Canvas {collect_canvas.sync(conn)}건")
            conn.commit()
            n = collect_canvas.sync_notices(conn)
            if n:
                steps.append(f"새 공지 {n}")
            got, err = learningx.sync(conn, collect_canvas.online_courses())
            steps.append(f"자료 +{got}" + (f" ⚠️{err}" if err else ""))
            service = get_service()
            c, u, r = sync_canvas.run(conn, service)
            steps.append(f"과제 캘린더 +{c} ~{u} -{r}")
        result, failed = plan.run(conn, service)
        steps.append(f"계획 {len(result)}건" + (f" (자리 부족 {len(failed)})" if failed else ""))
    except Exception as e:  # 네트워크 오류 등 — 화면은 가진 데이터로라도 갱신
        steps.append(f"오류: {e}")
        traceback.print_exc()
    finally:
        render.write(conn)
        conn.close()
    log(" · ".join(steps))


def _mtime():
    try:
        return inbox.PATH.stat().st_mtime
    except FileNotFoundError:
        return 0


def _download_watcher():
    """다운로드 폴더를 5초마다 본다 — 따로 도는 스레드라 동기화 중에도 멈추지 않는다."""
    while True:
        conn = db.connect()
        try:
            materials.scan_downloads(conn)
        except Exception as e:
            log(f"다운로드 폴더 확인 실패: {e}")
        finally:
            conn.close()
        time.sleep(5)


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


def watch():
    # 감시기는 하나만 (VSCode 창을 여러 개 열어도 캘린더에 중복으로 쓰지 않게)
    lock = open(db.PATH.parent / "watch.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("이미 다른 창에서 감시 중 — 이 창에서는 실행하지 않습니다.")
        return

    seen = {"mtime": _mtime()}

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
    log("비서 감시 시작 — inbox.md 저장 시 자동 반영, 15분마다 계획 갱신, Canvas 는 3시간마다 확인")
    run(full=True)
    last_full = last_plan = time.time()
    while True:
        time.sleep(POLL)
        if seen.pop("dirty", False):
            log("대시보드 입력")
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
            # 시간이 흐르면 지난 블록·날짜가 바뀌므로 주기적으로 다시 계획
            run(full=False)
            last_plan = time.time()
