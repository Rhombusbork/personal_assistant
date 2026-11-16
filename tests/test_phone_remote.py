"""휴대폰 원격: Tailscale 로 연 대시보드(REMOTE)와 GitHub 휴대폰 화면의 대기열·결과 글."""
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from pa import db, jobs, materials, mobile, server

REMOTE = "mypc.tail1234.ts.net"


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    monkeypatch.setattr(server, "remote_hosts", lambda: {REMOTE, REMOTE + ":443"})
    root = tmp_path / "report"
    root.mkdir()
    (root / "초안.md").write_text("# 초안\n본문", encoding="utf-8")
    monkeypatch.setattr(materials, "allowed_roots", lambda: [root.resolve()])
    db.connect().close()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1], root
    httpd.shutdown()


def raw(port, method, path, host="localhost:8765", body=None):
    h = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h.request(method, path, body=json.dumps(body or {}).encode() if method == "POST" else None,
              headers={"Host": host, "X-PA": "1", "Content-Type": "application/json"})
    r = h.getresponse()
    return r.status, r.getheader("Content-Type"), r.read()


def test_remote_host_allowed_only_when_configured(srv):
    port, _ = srv
    assert raw(port, "GET", "/api/viewers", host=REMOTE)[0] == 200
    assert raw(port, "GET", "/api/viewers", host="other.ts.net")[0] == 403


def test_engine_page_is_marked(srv):
    port, _ = srv
    st, ctype, body = raw(port, "GET", "/", host=REMOTE)
    assert st == 200 and "text/html" in ctype and b"window.PA_ENGINE = 1" in body


def test_remote_cannot_pop_things_on_pc(srv):
    port, root = srv
    st, _, body = raw(port, "POST", "/api/open-file", host=REMOTE, body={"path": str(root / "초안.md")})
    assert st == 400 and "PC" in json.loads(body)["error"]
    assert raw(port, "POST", "/api/reveal", host=REMOTE, body={"path": str(root / "초안.md")})[0] == 400


def test_file_view_respects_scope(srv, tmp_path):
    port, root = srv
    from urllib.parse import quote
    st, ctype, body = raw(port, "GET", "/api/file?path=" + quote(str(root / "초안.md")), host=REMOTE)
    assert st == 200 and ctype.startswith("text/plain") and "본문" in body.decode()
    (tmp_path / "secret.md").write_text("x", encoding="utf-8")
    assert raw(port, "GET", "/api/file?path=" + quote(str(tmp_path / "secret.md")), host=REMOTE)[0] == 400
    assert raw(port, "GET", "/api/file?path=" + quote(str(root / "../secret.md")), host=REMOTE)[0] == 400


def test_remote_tab_is_not_a_pc_viewer(srv):
    port, _ = srv
    server.VIEWERS.clear()
    raw(port, "GET", "/api/ping?v=phone1", host=REMOTE)
    assert "phone1" not in server.VIEWERS
    raw(port, "GET", "/api/ping?v=pc1")
    assert "pc1" in server.VIEWERS


def test_phone_queue_only_allows_listed_actions(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    db.connect().close()
    with pytest.raises(ValueError):
        mobile.apply_entry({"op": "act", "action": "/api/open-file", "body": {"path": "/etc/passwd"}})
    mobile.apply_entry({"op": "act", "action": "/api/job/notices"})
    conn = db.connect()
    assert [r["kind"] for r in conn.execute("SELECT kind FROM jobs")] == ["notices"]
    conn.close()


def test_results_carry_finished_drafts(tmp_path):
    md = tmp_path / "초안.md"
    md.write_text("본문", encoding="utf-8")
    big = tmp_path / "big.md"
    big.write_text("x" * (mobile.RESULT_MAX + 1), encoding="utf-8")
    out = mobile.results([{"status": "done", "result": str(md)}, {"status": "running", "result": str(md)},
                          {"status": "done", "result": str(big)}, {"status": "done", "result": str(tmp_path / "a.pdf")}])
    assert out == {str(md): "본문"}


def test_record_done_shows_in_recent(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    conn = db.connect()
    jobs.record_done(conn, "summary", "k", "내용정리(이미 있음): 3강", tmp_path / "3강.md")
    assert [(j["status"], j["result"]) for j in jobs.recent(conn)] == [("done", str(tmp_path / "3강.md"))]
    conn.close()


def test_proxy_header_marks_remote(srv):
    port, root = srv
    h = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h.request("POST", "/api/reveal", body=json.dumps({"path": str(root / "초안.md")}).encode(),
              headers={"Host": "localhost:8765", "X-PA": "1", "X-Forwarded-For": "100.64.0.2"})
    assert h.getresponse().status == 400  # tailscale serve 가 Host 를 바꿔 넘겨도 원격으로 본다


def test_remote_hosts_from_tailscale(monkeypatch):
    monkeypatch.setattr(server, "tailscale_name", lambda: "mypc.tail1234.ts.net")
    monkeypatch.setattr(server, "_remote_memo", {"at": 0.0, "hosts": set()})
    assert "mypc.tail1234.ts.net" in server.remote_hosts()


def test_proxy_header_does_not_open_other_hosts(srv):
    port, _ = srv
    h = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h.request("GET", "/api/viewers", headers={"Host": "evil.example", "X-Forwarded-For": "1.2.3.4"})
    assert h.getresponse().status == 403
