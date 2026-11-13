"""대시보드 로컬 서버 (http://localhost:8765) — 감시기 안에서 함께 돈다.

GET  /               대시보드 (dashboard/index.html)
GET  /api/data       지금 시각 기준 대시보드 데이터 (요청마다 새로 계산). ?v=<id> 로 '열려 있음' 신호
GET  /api/viewers    최근 45초 안에 신호를 보낸 대시보드 탭 수 (VSCode 가 중복으로 열지 않게)
POST /api/add        할 일 추가 → inbox.md 에 한 줄
POST /api/done       완료 (inbox 할 일은 체크, 그 밖은 ## 완료)
POST /api/ignore     계속 제외 (## 제외). pattern=true 면 같은 이름의 앞으로 생길 과제도
POST /api/unignore   제외 취소 (## 제외 의 그 줄을 지움)
POST /api/remove     inbox 할 일 삭제
POST /api/quick      빠른 입력 한 줄 ('@내일 18시 ~2h #과목')
POST /api/timer/start, /api/timer/stop   ⏱ 실제로 한 시간 기록 (stop 에 done=true 면 완료까지)
POST /api/open       항목의 Canvas 페이지를 Windows 브라우저로 열기
POST /api/sync       Canvas 까지 전체 동기화 (뒤에서 실행)
GET  /api/links?key=…  📄 자료 창: 연결된 자료 + 추천 + 시작 폴더 (config/materials.yaml 범위)
GET  /api/report-info?key=…  ✍ 창: Canvas 과제 설명 · 보고서 파일 이름·있는지 · 저장한 작성 지침
POST /api/report-brief, /api/report-file   작성 지침 저장 / Claude 없이 규칙 이름의 빈 파일 만들고 열기
GET  /api/note-for?key=…  강의를 들은 뒤 열 내 노트 (번호가 맞는 notes/<과목>/ 파일)
GET  /api/files       찾기 범위의 파일 이름 목록 (1분 보관 — 실시간 찾기는 화면이 이 목록으로)
GET  /api/ls?root=&path=   📁 둘러보기: 폴더 하나의 바로 아래 (범위 밖 거부)
GET  /api/downloads   다운로드 폴더의 최근 받은 문서 (엔진의 30초 감시 결과 — 폴더를 다시 열지 않음)
POST /api/link, /api/unlink   자료 연결·빼기 (paths 로 여러 개)
POST /api/link-download   다운로드 파일을 그 과목 자료 폴더로 옮긴 뒤 연결
POST /api/open-file  자료 파일을 VSCode 탭으로 열기 (study_system·report·최근 다운로드만)
POST /api/move-download, /api/dismiss-download   다운로드 폴더의 새 파일 정리
POST /api/job/report 보고서 준비 + 초안 (에이전트 작업 대기열에 넣음)
POST /api/job/notices 새 공지 요약 + 제외 후보 찾기 (Claude, 버튼으로만)
POST /api/job/summary 자료 PDF 요약 (Claude, 버튼으로만)
POST /api/job/summary-for  강의·과제에 맞는 자료를 찾아 바로 요약 (이미 있으면 그 정리를 연다)
POST /api/notice/read, /api/notice/open, /api/suggest/dismiss
POST /api/today      💭 하고 싶은 일을 오늘 하기 (오늘 23:59 마감을 붙임)
POST /api/open-quiz  퀴즈 앱을 Windows 브라우저로 열기
POST /api/browser-login  LearningX 다시 로그인 창 열기

입력은 모두 inbox.md 를 고치는 방식이라, inbox.md 를 직접 고치는 것과 결과가 같다.
"""
import json
import subprocess
import threading
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pa import db, inbox, jobs, links, materials, render
from pa.config import ROOT
from pa.model import KST

PORT = 8765
DASH = ROOT / "dashboard"
ALLOWED_HOSTS = {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}
VIEWERS = {}  # 대시보드 탭 id → 마지막 신호 시각


def viewer_count(window=45):
    cutoff = time.time() - window
    return sum(1 for t in VIEWERS.values() if t >= cutoff)


def parse_add(body):
    """폼 입력 → inbox.add_task 인자."""
    due = None
    if body.get("date"):
        t = body.get("time") or "23:59"
        due = datetime.fromisoformat(f"{body['date']}T{t}").replace(tzinfo=KST)
    return {
        "title": str(body.get("title", "")),
        "due": due,
        "minutes": int(body["minutes"]) if body.get("minutes") else None,
        "course": str(body.get("course", "")).strip(),
        "every": [int(d) for d in body.get("every", [])] or None,
    }


class Handler(SimpleHTTPRequestHandler):
    on_change = None  # 입력 후 호출할 함수 (계획 다시 짜기)
    on_sync = None    # 전체 동기화 함수

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(DASH), **kw)

    def log_message(self, *a):  # 요청 로그는 감시기 화면에 찍지 않음
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        # 다른 사이트가 이 서버에 요청을 보내는 것(DNS rebinding 등)을 막는다
        return self.headers.get("Host") in ALLOWED_HOSTS

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "host"})
        if self.path.startswith(("/api/files", "/api/downloads", "/api/ls", "/api/links")):
            return self._links_get()
        if self.path.startswith("/api/note-for"):  # 강의를 들은 뒤: 그 강의의 내 노트가 있으면 (study_system/notes)
            key = parse_qs(urlparse(self.path).query).get("key", [""])[0]
            conn = db.connect()
            try:
                row = conn.execute("SELECT course, title FROM tasks WHERE key = ?", (key,)).fetchone()
            finally:
                conn.close()
            dirs = materials.course_dirs(row["course"]) if row else None
            best = next((f for sc, f in materials.scan(dirs[1], row["title"]) if sc >= 10), None) if dirs else None
            return self._json(200, {"path": str(best), "name": best.name} if best else
                              {"folder": dirs[1].name if dirs else ""})
        if self.path.startswith("/api/report-info"):  # ✍ 창: 과제 설명·파일·지침
            key = parse_qs(urlparse(self.path).query).get("key", [""])[0]
            conn = db.connect()
            try:
                row = conn.execute("SELECT * FROM tasks WHERE key = ?", (key,)).fetchone()
                if not row:
                    raise ValueError("할 일을 찾지 못함")
                t = dict(row)
                p = jobs.report_path(t, conn)
                try:
                    desc = jobs.assignment_text(t) if t["kind"] == "assignment" else ""
                except Exception as e:  # Canvas 가 안 돼도 창은 연다
                    desc = f"(Canvas 과제 설명을 읽지 못함: {str(e)[:80]})"
                return self._json(200, {"title": t["title"], "due": t["due"], "kind": t["kind"], "desc": desc,
                                        "exists": p.exists(), "path": str(p), "name": p.name, "brief": jobs.brief(conn, key)})
            except Exception as e:
                return self._json(400, {"error": str(e)})
            finally:
                conn.close()
        if self.path.startswith("/api/viewers"):
            return self._json(200, {"count": viewer_count()})
        if self.path.split("?")[0] == "/api/data":
            vid = parse_qs(urlparse(self.path).query).get("v", [""])[0][:40]
            if vid:
                VIEWERS[vid] = time.time()
            conn = db.connect()
            try:
                data = render.dashboard_data(conn)
            finally:
                conn.close()
            return self._json(200, data)
        return super().do_GET()

    def do_POST(self):
        # 사용자 정의 헤더를 요구 → 다른 사이트의 폼·스크립트는 브라우저가 막는다 (CORS)
        if not self._host_ok() or self.headers.get("X-PA") != "1":
            return self._json(403, {"error": "forbidden"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            action = self.path.split("?")[0]
            if action == "/api/add":
                msg = inbox.add_task(**parse_add(body))
            elif action == "/api/done":
                inbox.mark_done(body["key"]); msg = "완료"
            elif action == "/api/ignore" and body.get("pattern"):
                conn = db.connect()
                try:
                    msg = "앞으로도 제외: " + inbox.ignore_like(conn, body["key"])
                finally:
                    conn.close()
            elif action == "/api/ignore":
                inbox.ignore(body["key"]); msg = "제외"
            elif action == "/api/exam-add":  # 시험 일정 후보 → inbox (시험 모드가 복습을 배치)
                when = datetime.fromisoformat(f"{body['date']}T{body.get('time') or '09:00'}").replace(tzinfo=KST)
                msg = inbox.add_task(title=body["title"], due=when, minutes=None, course=body.get("course", ""), every=None)
            elif action == "/api/keep":
                inbox.keep(body["key"]); msg = "이 과제는 계속 보이기"
            elif action == "/api/unignore":
                inbox.unignore(body["text"]); msg = "제외 취소"
            elif action == "/api/remove":
                inbox.remove(body["key"]); msg = "삭제"
            elif action == "/api/today":
                inbox.set_due(body["key"], datetime.now(KST).replace(hour=23, minute=59, second=0, microsecond=0))
                msg = "오늘 하기"
            elif action == "/api/quick":
                msg = inbox.add_task_line(inbox.quick_line(str(body.get("text", ""))))
            elif action in ("/api/timer/start", "/api/timer/stop", "/api/open", "/api/sync", "/api/open-file",
                            "/api/move-download", "/api/dismiss-download", "/api/job/report", "/api/job/notices", "/api/job/summary", "/api/job/summary-for",
                            "/api/notice/read", "/api/notice/open", "/api/suggest/dismiss", "/api/browser-login", "/api/open-quiz",
                            "/api/google-login", "/api/ack", "/api/exam-dismiss",
                            "/api/link", "/api/unlink", "/api/link-download", "/api/report-brief", "/api/report-file"):
                return self._json(200, self.side_action(action, body))
            else:
                return self._json(404, {"error": "없는 요청"})
        except (ValueError, KeyError) as e:
            return self._json(400, {"error": str(e)})
        self._applied()
        self._json(200, {"ok": True, "message": msg})

    def _applied(self):
        """inbox 를 바꾼 뒤: 저장소에는 바로 반영(빠름), 계획·캘린더는 뒤에서 (몇 초)."""
        conn = db.connect()
        try:
            inbox.sync(conn)
        finally:
            conn.close()
        if Handler.on_change:
            threading.Thread(target=Handler.on_change, daemon=True).start()


    def _links_get(self):
        """자료 연결 창용 (읽기만): 파일 목록 · 최근 다운로드 · 폴더 하나 · 연결된 자료와 추천."""
        q = parse_qs(urlparse(self.path).query)
        arg = lambda k, d="": q.get(k, [d])[0]
        try:
            if self.path.startswith("/api/files"):
                return self._json(200, {"files": links.index(), "roots": [r["name"] for r in links.cfg()["roots"]]})
            if self.path.startswith("/api/downloads"):
                return self._json(200, {"files": links.recent_downloads(),
                                        "days": links.cfg()["downloads"]["recent_days"]})
            if self.path.startswith("/api/ls"):
                return self._json(200, links.ls(arg("root", "자료"), arg("path")))
            conn = db.connect()
            try:
                key = arg("key")
                row = conn.execute("SELECT course, title, kind FROM tasks WHERE key = ?", (key,)).fetchone()
                dirs = materials.course_dirs(row["course"]) if row else None
                start = links.root_of(dirs[0]) if dirs else None
                deleted = json.loads(db.get_meta(conn, "deleted_materials") or "{}").get(row["course"], []) if row else []
                linked = links.get(conn, key)
                for x in linked:  # PDF 는 🤖 요약 / 📝 요약 열기
                    x["pdf"] = x["p"].lower().endswith(".pdf")
                    sp = jobs.summary_path(x["p"]) if x["pdf"] else None
                    x["summary"] = str(sp) if sp and sp.exists() else ""
                scope = [f"{r[0]}/{r[1]}" for d in (dirs or []) for r in [links.root_of(d)] if r]
                return self._json(200, {"links": linked, "suggest": links.suggest(conn, key), "scope": scope,
                                        "max": links.cfg()["max_links"], "days": links.cfg()["downloads"]["recent_days"],
                                        "title": row["title"] if row else key,
                                        "kind": row["kind"] if row else "", "deleted": deleted,
                                        "start": {"root": start[0], "path": start[1]} if start else {"root": "자료", "path": ""}})
            finally:
                conn.close()
        except (ValueError, OSError) as e:
            return self._json(400, {"error": str(e)})

    def side_action(self, action, body):
        """inbox 를 바꾸지 않는 요청 — 계획을 다시 짤 필요가 없다 (완료 처리 제외)."""
        conn = db.connect()
        try:
            if action == "/api/timer/start":
                db.start_session(conn, body["key"])
                conn.commit()
                return {"ok": True}
            if action == "/api/timer/stop":
                got = db.stop_session(conn)
                conn.commit()
                if got and body.get("done"):
                    inbox.mark_done(got[0])
                    self._applied()
                return {"ok": True, "minutes": got[1] if got else 0}
            if action == "/api/open":
                row = conn.execute("SELECT url FROM tasks WHERE key = ?", (body["key"],)).fetchone()
                if not row or not row["url"]:
                    raise ValueError("열 수 있는 링크가 없음")
                subprocess.Popen(["explorer.exe", row["url"]])  # Windows 기본 브라우저 (학교 로그인 유지)
                return {"ok": True}
            if action == "/api/report-brief":
                jobs.save_brief(conn, body["key"], body.get("text", ""), body.get("blanks", True))
                return {"ok": True}
            if action == "/api/report-file":
                path = jobs.blank_report(conn, body["key"])
                return {"ok": True, "path": str(path), "where": materials.open_file(path)}
            if action == "/api/job/report":
                if "text" in body:  # ✍ 창의 지침을 저장한 뒤 초안
                    jobs.save_brief(conn, body["key"], body["text"], body.get("blanks", True))
                row = conn.execute("SELECT title FROM tasks WHERE key = ?", (body["key"],)).fetchone()
                if not row:
                    raise ValueError("할 일을 찾지 못함")
                jobs.enqueue(conn, "report-force" if body.get("force") else "report", body["key"], row["title"])
                return {"ok": True, "message": "보고서 작업을 시작합니다 (🤖 작업 칸)"}
            if action == "/api/link":  # 자료 연결 (여러 개 한 번에도)
                for p in body.get("paths") or [body["path"]]:
                    links.add(conn, body["key"], p)
                return {"ok": True}
            if action == "/api/unlink":
                links.remove(conn, body["key"], body["path"])
                return {"ok": True}
            if action == "/api/link-download":  # 다운로드 파일 → 과목 폴더로 옮겨서 연결
                return links.add_download(conn, body["key"], body["path"], body.get("course"))
            if action == "/api/exam-dismiss":
                from pa import exams
                exams.dismiss(conn, body["id"])
                return {"ok": True}
            if action == "/api/google-login":
                subprocess.Popen([str(ROOT / "bin" / "pa"), "google-login"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return {"ok": True, "message": "Windows 브라우저에 Google 로그인 창이 열립니다 — 허용하면 끝 (10분 안에)"}
            if action == "/api/ack":  # 알림 확인 (휴대폰 입력 실패·새 점수 등) — 이 시각 이전 것은 더 안 보여 줌
                if not str(body["what"]).isidentifier():
                    raise ValueError("잘못된 확인 요청")
                db.set_meta(conn, f"ack_{body['what']}", datetime.now(KST).isoformat())
                conn.commit()
                return {"ok": True}
            if action == "/api/open-quiz":
                from pa import quiz
                subprocess.Popen(["explorer.exe", quiz.cfg()["url"]])
                return {"ok": True}
            if action == "/api/browser-login":
                subprocess.Popen([str(ROOT / "bin" / "pa"), "browser", "login"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return {"ok": True, "message": "로그인 창을 엽니다 — 로그인하면 저절로 닫힙니다"}
            if action == "/api/job/summary-for":
                row = conn.execute("SELECT course, title FROM tasks WHERE key = ?", (body["key"],)).fetchone()
                if not row:
                    raise ValueError("할 일을 찾지 못함")
                linked = [f for f in links.paths(conn, body["key"]) if f.suffix.lower() == ".pdf"]
                if len(linked) > 1:  # 연결된 PDF 가 여러 개 → 자료 창에서 고르게
                    return {"ok": True, "choose": True}
                if linked:
                    pdfs = linked
                else:
                    _, scored = materials.find(row["course"], row["title"])
                    pdfs = [f for sc, f in scored if sc >= 10 and f.suffix.lower() == ".pdf" and "요약" not in f.parts]
                if not pdfs:
                    raise ValueError("이 강의의 자료(PDF)가 아직 없습니다 — 📄 자료 에서 연결하거나, 받으면 그때 정리할 수 있어요")
                existing = jobs.summary_path(pdfs[0])
                if existing.exists():
                    materials.open_file(existing)
                    return {"ok": True, "message": "이미 만든 정리를 열었습니다"}
                jobs.enqueue(conn, "summary", str(pdfs[0]), "내용정리: " + pdfs[0].stem)
                return {"ok": True, "message": f"내용정리 시작: {pdfs[0].name} (🤖 작업 칸)"}
            if action == "/api/job/summary":
                jobs.enqueue(conn, "summary", body["path"], "요약: " + Path(body["path"]).stem)
                return {"ok": True}
            if action == "/api/job/notices":
                jobs.enqueue(conn, "notices", "notices", "새 공지 정리")
                return {"ok": True}
            if action == "/api/notice/read":
                if body.get("id") == "all":
                    conn.execute("UPDATE notices SET status = 'read' WHERE status = 'new'")
                else:
                    conn.execute("UPDATE notices SET status = 'read' WHERE id = ?", (str(body["id"]),))
                conn.commit()
                return {"ok": True}
            if action == "/api/notice/open":
                row = conn.execute("SELECT url FROM notices WHERE id = ?", (str(body["id"]),)).fetchone()
                if row and row["url"]:
                    subprocess.Popen(["explorer.exe", row["url"]])
                return {"ok": True}
            if action == "/api/suggest/dismiss":
                sugg = [x for x in json.loads(db.get_meta(conn, "notice_suggestions") or "[]") if x["key"] != body["key"]]
                db.set_meta(conn, "notice_suggestions", json.dumps(sugg, ensure_ascii=False))
                conn.commit()
                return {"ok": True}
            if action == "/api/open-file":
                return {"ok": True, "where": materials.open_file(body["path"])}
            if action == "/api/move-download":
                dst = materials.move_download(conn, body["path"], body["course"])
                return {"ok": True, "message": f"옮김: {dst}"}
            if action == "/api/dismiss-download":
                materials.dismiss_download(conn, body["path"])
                return {"ok": True}
            if action == "/api/sync" and Handler.on_sync:
                threading.Thread(target=Handler.on_sync, daemon=True).start()
                return {"ok": True, "message": "Canvas 확인 시작 (30초쯤 걸림)"}
            return {"ok": False}
        finally:
            conn.close()


def start(on_change=None, on_sync=None):
    """백그라운드 스레드로 서버 시작. 포트를 쓰는 중이면 None."""
    Handler.on_change = on_change
    Handler.on_sync = on_sync
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        return None
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
