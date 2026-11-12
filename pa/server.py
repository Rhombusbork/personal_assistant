"""대시보드 로컬 서버 (http://localhost:8765) — 감시기 안에서 함께 돈다.

GET  /               대시보드 (dashboard/index.html)
GET  /api/data       지금 시각 기준 대시보드 데이터 (요청마다 새로 계산)
POST /api/add        할 일 추가 → inbox.md 에 한 줄
POST /api/done       완료 (inbox 할 일은 체크, 그 밖은 ## 완료)
POST /api/ignore     계속 제외 (## 제외)
POST /api/remove     inbox 할 일 삭제

입력은 모두 inbox.md 를 고치는 방식이라, inbox.md 를 직접 고치는 것과 결과가 같다.
"""
import json
import threading
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from pa import db, inbox, render
from pa.config import ROOT
from pa.model import KST

PORT = 8765
DASH = ROOT / "dashboard"
ALLOWED_HOSTS = {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}


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
        if self.path.split("?")[0] == "/api/data":
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
            elif action == "/api/ignore":
                inbox.ignore(body["key"]); msg = "제외"
            elif action == "/api/remove":
                inbox.remove(body["key"]); msg = "삭제"
            else:
                return self._json(404, {"error": "없는 요청"})
        except (ValueError, KeyError) as e:
            return self._json(400, {"error": str(e)})
        if Handler.on_change:
            Handler.on_change()
        self._json(200, {"ok": True, "message": msg})


def start(on_change=None):
    """백그라운드 스레드로 서버 시작. 포트를 쓰는 중이면 None."""
    Handler.on_change = on_change
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        return None
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
