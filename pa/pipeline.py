"""자동 실행 블록.

run(full)  inbox → (full 이면 Canvas·과제 캘린더) → 계획 → TODAY.md·대시보드
watch()    시작할 때 full 실행 후, inbox.md 가 저장될 때마다 빠른 실행,
           CANVAS_EVERY 마다 full 실행. VSCode 작업 공간을 열면 자동으로 켜진다.
"""
import fcntl
import time
import traceback
from datetime import datetime

from pa import collect_canvas, db, inbox, plan, render, sync_canvas
from pa.gcal import get_service

CANVAS_EVERY = 3 * 60 * 60  # 초
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


def watch():
    # 감시기는 하나만 (VSCode 창을 여러 개 열어도 캘린더에 중복으로 쓰지 않게)
    lock = open(db.PATH.parent / "watch.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("이미 다른 창에서 감시 중 — 이 창에서는 실행하지 않습니다.")
        return
    log("비서 감시 시작 — inbox.md 저장 시 자동 반영, Canvas 는 3시간마다 확인")
    run(full=True)
    last_full = time.time()
    last_mtime = inbox.PATH.stat().st_mtime if inbox.PATH.exists() else 0
    while True:
        time.sleep(POLL)
        try:
            mtime = inbox.PATH.stat().st_mtime
        except FileNotFoundError:
            continue
        if mtime != last_mtime:
            time.sleep(0.5)  # 저장이 끝나길 잠깐 기다림
            last_mtime = inbox.PATH.stat().st_mtime
            log("inbox.md 저장 감지")
            run(full=False)
        if time.time() - last_full >= CANVAS_EVERY:
            run(full=True)
            last_full = time.time()
