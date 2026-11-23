"""자동 실행 블록.

run(full)  휴대폰 입력 → inbox → 퀴즈 기록 → (full 이면 Canvas·공지·자료) → 계획 → 마감 캘린더
           → TODAY.md·대시보드 → 휴대폰. 단계마다 따로 — 한 단계가 실패해도 나머지는 돈다.
watch()    시작할 때 full 실행 후, inbox.md 가 저장될 때마다 빠른 실행, PLAN_EVERY 마다 확인,
           canvas.check_every_hours 마다 full 실행 (켤 때는 항상), 대시보드 서버(pa/server.py)도 함께.
           pa/*.py 가 바뀌면 스스로 다시 시작한다 (VSCode 를 다시 열 필요 없음).
           VSCode 작업 공간을 열면 자동으로 켜진다.
"""
import threading
import time
import traceback
from datetime import datetime, timedelta

from pa import collect_canvas, db, deadlines, inbox, jobs, learningx, materials, mobile, osutil, peer, plan, portal, quiz, render, server
from pa.canvas import CanvasAuthError
from pa.config import ROOT
from pa.gcal import GoogleAuthError, get_service
from pa.model import now

PLAN_EVERY = 15 * 60        # 이때마다 '다시 계획할 필요가 있나' 확인 (필요할 때만 Google 에 요청) + 곧 마감인 것 제출 확인
QUICK_SOON = 3 * 60         # 30분 안에 마감이 있으면 이때마다 제출·수강 확인 (끝낸 일의 촘촘한 알림을 빨리 지우게)
PHONE_EVERY = 3 * 60
AUTOOPEN_EVERY = 30           # 학습 계획 블록이 시작됐나 (강의·퀴즈·과제 자동 열기, pa/autoopen.py)
DOWNLOADS_EVERY = 30
POLL = 1.0

LOG_FILE = db.PATH.parent / "pa.log"


def log(msg):
    line = f"[{datetime.now():%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:  # 창 없이(작업 스케줄러) 돌 때도 남도록 파일에도. 1MB 넘으면 뒤쪽 절반만 남김
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 1_000_000:
            LOG_FILE.write_text(LOG_FILE.read_text(encoding="utf-8")[-500_000:], encoding="utf-8")
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def run(full=False, force_plan=False, quick=False):
    # 실행은 한 번에 하나만 (감시기·수동 실행·작업 스케줄러가 겹쳐도 캘린더에 중복으로 쓰지 않게)
    db.PATH.parent.mkdir(exist_ok=True)
    with open(db.PATH.parent / "run.lock", "a", encoding="utf-8") as lock:
        osutil.lock(lock)
        if not peer.is_leader():  # 두 PC: 대기 PC 는 화면만 (계획·캘린더·Canvas·휴대폰은 일하는 PC 가)
            peer.get().inbox_changed()
            _render_only()
            return
        STATE["full"] = full
        try:
            _run(full, force_plan or full, quick)
        finally:
            STATE["full"] = False


def _run(full, force_plan, quick=False):
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
        if quick and not full:  # 곧 마감인 것만 제출·수강 확인 (몇 번의 짧은 요청)
            n = step("제출 확인", lambda: collect_canvas.quick_done(conn))
            if n:
                steps.append(f"제출·수강 확인 → 완료 {n}")
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
            got = step("포털 시간표", lambda: portal.weekly(conn))  # 그 주의 첫 전체 확인에서 한 번
            if got:
                steps.append(f"포털 시간표 {got[0]}건" + (f" ⚠️새 과목 {len(got[1])}" if got[1] else ""))
            last = db.get_meta(conn, "events_pruned_at")
            if not last or last[:10] != datetime.now().strftime("%Y-%m-%d"):  # 하루 한 번: 1년 넘은 기록 정리
                step("기록 정리", lambda: db.prune_events(conn))
        need_plan = force_plan or step("계획 확인", lambda: plan.needed(conn))
        need_deadlines = force_plan or step("마감 확인", lambda: deadlines.needed(conn))
        tt_new = db.get_meta(conn, "portal_classes") and portal.cfg()["enabled"] and \
            db.get_meta(conn, "portal_calendar_hash") != portal.digest(conn)
        if need_plan or need_deadlines or tt_new:
            service = step("Google", get_service)
            if service and tt_new:  # 수업 시간표가 바뀌면 계획보다 먼저 캘린더에 (계획이 수업을 피하게)
                res = step("수업 시간표", lambda: portal.sync_calendar(conn, service))
                if res:
                    steps.append(f"수업 시간표 +{res[0]} -{res[1]}")
                    need_plan = True
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


def _render_only():
    conn = db.connect()
    try:
        render.write(conn)
    finally:
        conn.close()


def _peer_loop(seen):
    """두 PC: 30초마다 저장소와 맞춘다. 넘겨받으면 바로 전체 확인, 기록을 받아 오면 화면 갱신."""
    p = peer.get()
    while True:
        try:
            res = p.tick()
            warns = res.get("warnings") or []
            conn = db.connect()
            try:
                if (db.get_meta(conn, "peer_warnings") or "") != "\n".join(warns):
                    db.set_meta(conn, "peer_warnings", "\n".join(warns))
                    conn.commit()
            finally:
                conn.close()
            if res.get("became"):
                log(f"두 PC: 이 PC 는 이제 {'일하는 PC' if res['became'] == 'leader' else '대기 PC'}")
            if res.get("became") == "leader":
                seen["full"] = True
            elif res.get("restored") or res.get("became") or res.get("replayed"):
                seen["mtime"] = _mtime()  # 받아 온 inbox.md 를 '저장'으로 보지 않게
                seen["dirty"] = True
        except Exception as e:
            log(f"⚠️ 두 PC 맞추기 실패 (계속 시도): {str(e)[:120]}")
        time.sleep(peer.TICK)


_quick_memo = {"at": 0, "v": None}


def _quick_every():
    """제출·수강 빠른 확인 간격(초): 30분 안에 마감인 Canvas 일이 있으면 3분, 아니면 15분(=PLAN_EVERY 때 같이).
    감시 루프가 자주 부르므로 1분 동안은 기억한 값을 쓴다."""
    if time.time() - _quick_memo["at"] < 60 and _quick_memo["v"]:
        return _quick_memo["v"]
    conn = db.connect()
    try:
        soon = [t for t in collect_canvas.quick_targets(conn) if timedelta(0) < t.due - now() <= timedelta(minutes=30)]
    finally:
        conn.close()
    _quick_memo.update(at=time.time(), v=QUICK_SOON if soon else PLAN_EVERY)
    return _quick_memo["v"]


def _pull_phone():
    """휴대폰 입력(GitHub phone-inbox)을 inbox.md 로. 실패해도 계속."""
    if not peer.is_leader():
        return 0
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


def _auto_open():
    """30초마다: 계획 시간 자동 열기 · 끝난 블록 확인 · 자동 제출 (일하는 PC 만)."""
    from pa import autoopen, autosubmit, power, schedules
    if not peer.is_leader():  # 두 PC 가 같이 켜져 있으면 일하는 PC 에서만 연다
        return
    conn = db.connect()
    try:
        for key in autoopen.check(conn, now()):
            log(f"계획 시간 — 열었음: {key}")
        if autoopen.review_due(conn, now()):  # 하루 마무리 시간 → 대시보드를 띄움 (마무리 카드)
            open_dashboard("하루 마무리 시간")
        ended = autoopen.ended(conn, now())
        if ended:  # 블록이 끝남 → 수강·제출을 바로 확인 (끝냈으면 완료로, 안 잡혔으면 알림)
            threading.Thread(target=lambda: _safe(lambda: _quick_check(ended)), daemon=True).start()
        for title, issues in autoopen.precheck(conn, now()):  # 퀴즈·시험 30분 전 점검
            log(f"시험·퀴즈 점검: {title} — " + (" / ".join(issues) or "문제 없음"))
            STATE["job_done"] = True
        for key in autosubmit.tick(conn, now()):
            log(f"자동 제출함 (확인 필요): {key}")
            STATE["job_done"] = True  # 화면·휴대폰에 바로
        try:
            autosubmit.sync_calendar(conn)  # 확인 알림 (바뀌었을 때만 Google 에)
        except Exception as e:
            log(f"자동 제출 확인 알림 실패 (다음에 다시): {str(e)[:100]}")
        for sid, title, what in schedules.tick(conn, now()):  # 고급 예약
            log(f"예약 실행: {title} — {what}")
            STATE["job_done"] = True
        if time.time() - _wake_memo["at"] > WAKE_EVERY:  # 예약 전에 PC 깨우기 (작업 스케줄러, 바뀌었을 때만)
            _wake_memo["at"] = time.time()
            try:
                n = power.sync_wakes(conn)
                if n is not None:
                    log(f"예약 전 깨우기 {n}개로 맞춤")
            except Exception as e:
                log(f"⚠️ 예약 전 깨우기 실패: {str(e)[:120]}")
    finally:
        conn.close()


_wake_memo = {"at": 0}
WAKE_EVERY = 300


def _quick_check(keys=()):
    """끝난 블록의 일: 끝냈으면 완료. 강의인데 출석이 안 잡혔거나, 퀴즈·과제가 하루 안 마감인데 안 냈으면 알림."""
    conn = db.connect()
    try:
        n = collect_canvas.quick_done(conn)
        if n:
            log(f"블록이 끝나 확인 — 끝낸 것 {n}개 완료")
        for k in keys:
            t = next(iter(db.tasks(conn, "key = ? AND status = 'open'", (k,))), None)
            if not t:
                continue
            if t.kind == "lecture":
                db.log(conn, "attendance_missing", k, title=t.title, due=t.due.isoformat() if t.due else None)
            elif t.kind in ("quiz", "assignment") and t.due and t.due - now() < timedelta(hours=24):
                db.log(conn, "submit_missing", k, title=t.title, due=t.due.isoformat())
        conn.commit()
        STATE["job_done"] = True
    finally:
        conn.close()


def _job_runner(quick=False):
    """에이전트 작업을 하나씩 처리하는 스레드 (보고서 초안 등은 몇 분 걸릴 수 있음).
    quick=True 는 퀴즈 풀이만 처리하는 두 번째 스레드 — 사진을 찍고 바로 답을 보게."""
    conn = db.connect()
    if not quick:
        jobs.reset_stuck(conn)
    last_tab = 0
    while True:
        try:
            if quick:
                from pa import quizhelp
                if quizhelp.scan(conn):
                    log("퀴즈 도움 — 새 스크린샷")
                if time.time() - last_tab >= quizhelp.TAB_EVERY:
                    last_tab = time.time()
                    if quizhelp.watch_tab(conn):
                        log("퀴즈 탭을 닫아 퀴즈 도움 끔")
            if jobs.run_next(conn, quick=quick):
                log("에이전트 작업 하나 처리")
                STATE["job_done"] = True  # 감시 순환이 화면(휴대폰 포함)을 다시 올리게
                continue
        except Exception as e:
            log(f"작업 처리 오류: {e}")
        time.sleep(2)


RESTART_FLAG = ROOT / "data" / "restart.flag"
_canvas_memo = {"at": 0, "v": None}


def canvas_every():
    """켜 둔 동안 Canvas 전체 확인 간격(초). config/timetable.yaml 의 canvas.check_every_hours (0 = 켤 때·⟳ 때만). 1분 기억."""
    if time.time() - _canvas_memo["at"] > 60 or _canvas_memo["v"] is None:
        from pa.config import load_timetable
        try:
            h = float((load_timetable().get("canvas") or {}).get("check_every_hours", 3))
        except (TypeError, ValueError):
            h = 3
        _canvas_memo.update(at=time.time(), v=int(max(0, h) * 3600))
    return _canvas_memo["v"]


STARTUP_WAIT = 60   # 켤 때: 대시보드 창이 뜰 때까지 최대 이만큼 기다렸다가 최신화 시작
WINDOW_GRACE = 3    # 창이 뜬 뒤 이만큼 더 (그려지는 동안 겹치지 않게)
STATE = {"full": False}  # 대시보드 상태 줄 '최신화 중' 표시용


def dash_mode():
    """대시보드를 어디에: 'vscode' (VSCode 안 탭, 비서 확장이 엶) | 'app' (Edge 앱 창). config dashboard.mode"""
    from pa.config import load_timetable
    m = (load_timetable().get("dashboard") or {}).get("mode", "vscode")
    return m if m in ("vscode", "app") else "vscode"


def open_dashboard(reason=""):
    """bin/pa open 등 직접 열 때. mode=vscode: VSCode 가 켜져 있으면 안 탭(확장에게 요청 — 비서 폴더 창이 먼저).
    꺼져 있으면 아무것도 안 함. mode=app: Edge 앱 창."""
    if dash_mode() == "vscode":
        if server.vscode_alive() and server.request_open():
            log(f"대시보드 탭 열기 (VSCode 안){' — ' + reason if reason else ''}")
        return
    log(f"대시보드 창 열기{' — ' + reason if reason else ''}")
    osutil.open_app(f"http://localhost:{server.PORT}/")


def _wait_for_window():
    """창이 먼저: 대시보드 탭이 신호를 보낼 때까지(최대 STARTUP_WAIT초) 기다린 뒤 최신화를 시작한다.
    창이 없으면 STARTUP_WAIT 뒤에 그냥 시작. 창은 저절로 열지 않는다 — 버튼으로만 (2026-11-23 사용자가 정함)."""
    end = time.time() + STARTUP_WAIT
    while time.time() < end:
        if server.viewer_count():
            time.sleep(WINDOW_GRACE)
            return
        time.sleep(1)


def _was_restart():
    """코드가 바뀌어 스스로 다시 시작한 것인가 (2분 안에 남긴 표시). 표시는 지운다."""
    try:
        fresh = time.time() - RESTART_FLAG.stat().st_mtime < 120
        RESTART_FLAG.unlink()
        return fresh
    except OSError:
        return False


def _safe(fn):
    try:
        return fn()
    except Exception as e:
        log(f"⚠️ 오류 (계속 감시함): {e}")
        traceback.print_exc()


def _new_code_ok():
    """바뀐 코드를 다른 프로세스에서 불러 봐서 문법·import 오류가 없는지. (저장 도중의 덜 고친 코드로 다시 시작해 꺼지지 않게)"""
    import subprocess
    import sys
    try:
        r = subprocess.run([sys.executable, "-c", "import pa.pipeline, pa.server, pa.render, pa.jobs, pa.__main__"],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    return r.returncode == 0, (r.stderr or "").strip().splitlines()[-1:] or [""]


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
    ok, err = _new_code_ok()
    if not ok:
        state["code"] = m  # 다음에 또 바뀌면 다시 시험
        log(f"⚠️ 바뀐 코드에 오류가 있어 다시 시작하지 않고 예전 코드로 계속합니다: {err[0] if isinstance(err, list) else err}")
        return
    log("코드가 바뀌어 엔진을 새 코드로 다시 시작합니다")
    RESTART_FLAG.parent.mkdir(exist_ok=True)
    RESTART_FLAG.touch()
    osutil.restart_self(["watch"])  # 잠금·서버는 새 프로세스가 다시 잡는다


def watch():
    # 감시기는 하나만 (VSCode 창을 여러 개 열어도 캘린더에 중복으로 쓰지 않게)
    db.PATH.parent.mkdir(exist_ok=True)
    lock = open(db.PATH.parent / "watch.lock", "a", encoding="utf-8")
    got = osutil.lock(lock, wait=False)
    if not got and RESTART_FLAG.exists() and time.time() - RESTART_FLAG.stat().st_mtime < 120:
        for _ in range(100):  # 새 코드로 다시 시작하는 중 → 이전 프로세스가 잠금을 풀 때까지 (최대 20초)
            time.sleep(0.2)
            if osutil.lock(lock, wait=False):
                got = True
                break
    if not got:
        log("이미 다른 창에서 감시 중 — 이 창에서는 실행하지 않습니다.")
        return

    seen = {"mtime": _mtime()}
    code_state = {"code": _code_mtime()}

    def after_input():
        # 대시보드 입력 → 다음 순환에서 한 번만 다시 계획 (연달아 눌러도 한 번으로 합침)
        seen["mtime"] = _mtime()  # inbox 저장 감지로 또 돌지 않게
        seen["dirty"] = True

    serving = server.start(after_input, on_sync=lambda: run(full=True))
    if serving:
        log(f"대시보드: http://localhost:{server.PORT}")
    else:
        log(f"포트 {server.PORT} 사용 중 — 대시보드 서버는 켜지 않음")
    threading.Thread(target=_download_watcher, daemon=True).start()
    threading.Thread(target=_job_runner, daemon=True).start()
    threading.Thread(target=_job_runner, args=(True,), daemon=True).start()
    if peer.enabled():
        try:  # 켤 때 한 번은 기다려서 맞춘다 → 대기 PC 가 잠깐이라도 캘린더를 쓰지 않게
            peer.get().tick()
        except Exception as e:
            log(f"⚠️ 두 PC 맞추기 실패 (계속 시도): {str(e)[:120]}")
        threading.Thread(target=_peer_loop, args=(seen,), daemon=True).start()
        log("두 PC 같이 쓰기 — 이 PC 는 " + ("일하는 PC" if peer.is_leader() else "대기 PC"))
    every = canvas_every()
    log("비서 감시 시작 — inbox.md 저장 시 반영, 15분마다 확인(바뀐 게 있을 때만 다시 계획), "
        + (f"Canvas {every // 3600}시간마다" if every else "Canvas 는 켤 때와 ⟳ 누를 때만"))
    restarted = _was_restart()
    if not restarted:  # 켤 때 한 번: 휴대폰·클라우드에서 바꾼 기록·보고서를 내려받기 (뒤에서)
        from pa import repos
        threading.Thread(target=lambda: _safe(lambda: repos.pull_all(log)), daemon=True).start()
    from pa.model import parse_dt
    conn = db.connect()
    try:
        last = db.get_meta(conn, "canvas_synced_at")
    finally:
        conn.close()
    age = (now() - parse_dt(last)).total_seconds() if last else None
    # 켤 때는 항상 Canvas 까지 (창은 서버가 먼저 떠서 바로 보이고, 이건 뒤에서 돈다. 로그인이 끊겼으면 여기서 자동 로그인).
    # 코드가 바뀌어 스스로 다시 시작한 때만 방금 확인했으면 건너뛴다.
    full = not (restarted and age is not None and age < (every or 3 * 3600))
    if full and serving:
        STATE["full"] = True  # 창이 뜨자마자 '최신화 중' (기다리는 동안도) → 화면이 5초마다 새로 읽음
        _wait_for_window()
    _safe(lambda: run(full=full))
    last_full = time.time() if full else time.time() - age
    last_plan = last_phone = last_code = last_quick = time.time()
    last_open = 0
    login_file = db.PATH.parent / "browser-state.json"  # 강의 플랫폼 로그인
    login_seen = login_file.stat().st_mtime if login_file.exists() else 0
    while True:
        time.sleep(POLL)
        try:  # 한 번 실패해도 감시는 계속 (예전엔 오류 하나로 엔진이 꺼졌다)
            if time.time() - last_code >= 5:
                last_code = time.time()
                _restart_if_code_changed(code_state)
            if time.time() - last_open >= AUTOOPEN_EVERY:
                last_open = time.time()
                _safe(_auto_open)
            if time.time() - last_phone >= PHONE_EVERY:  # 휴대폰 입력이 있으면 바로 반영
                last_phone = time.time()
                if _pull_phone():
                    seen["mtime"] = _mtime()
                    seen["dirty"] = True
            if STATE.pop("job_done", False):
                seen["dirty"] = True
            if seen.pop("full", False):  # 두 PC: 방금 넘겨받음 → Canvas 까지
                run(full=True)
                last_full = last_plan = time.time()
            if seen.pop("dirty", False):
                log("입력 반영")
                run(full=False)
                last_plan = time.time()
            mtime = _mtime()
            if mtime and mtime != seen["mtime"]:
                time.sleep(0.5)  # 저장이 끝나길 잠깐 기다림
                seen["mtime"] = _mtime()
                log("inbox.md 저장 감지" + (" — 일하는 PC 로 보냄" if peer.standby() else ""))
                run(full=False)
                last_plan = time.time()
            lm = login_file.stat().st_mtime if login_file.exists() else 0
            from pa import browser
            if lm != login_seen and abs(lm - browser.AUTO["at"]) < 30:  # 엔진이 스스로 로그인한 것 → 이미 그 확인 안에서 반영됨
                login_seen = lm
            if lm != login_seen and time.time() - lm > 5:  # 사용자가 방금 다시 로그인함 → 바로 확인
                login_seen = lm
                log("강의 플랫폼 로그인 감지 — 바로 확인")
                run(full=True)
                last_full = last_plan = time.time()
            every = canvas_every()
            if every and time.time() - last_full >= every:
                run(full=True)
                last_full = last_plan = time.time()
            elif time.time() - last_plan >= PLAN_EVERY:
                run(full=False, quick=True)  # 바뀐 게 없으면 Google 에 요청하지 않고 화면만 갱신
                last_plan = last_quick = time.time()
            elif time.time() - last_quick >= _quick_every():  # 마감이 30분 안이면 3분마다 제출 확인
                run(full=False, quick=True)
                last_quick = time.time()
        except Exception as e:
            log(f"⚠️ 감시 중 오류 (계속 감시함): {e}")
            traceback.print_exc()
            last_plan = last_quick = time.time()  # 같은 오류를 1초마다 되풀이하지 않게
            time.sleep(5)
