"""대시보드 서버 요청 단위 시험: 막아야 할 것은 막고, 자료 연결 요청이 범위를 지키는지."""
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from pa import db, links, server


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    mat = tmp_path / "materials"
    (mat / "bio").mkdir(parents=True)
    (mat / "bio" / "3강.pdf").write_bytes(b"x")
    c = {"roots": [{"name": "자료", "path": mat.resolve(), "ext": {".pdf"}}], "skip": [],
         "downloads": {"recent_days": 7, "ext": {".pdf"}}, "max_links": 3}
    monkeypatch.setattr(links, "cfg", lambda: c)
    links._index.update(at=0.0, files=None)
    conn = db.connect()
    db.sync_source(conn, "canvas", [{"key": "m1", "kind": "lecture", "course": "", "title": "3강",
                                     "due": "2099-01-01T23:59:00+09:00", "earliest": None, "minutes": 50, "url": ""}])
    conn.close()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1], mat
    httpd.shutdown()


def req(port, method, path, body=None, host="localhost:8765", pa=True):
    h = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host, "Content-Type": "application/json"}
    if pa:
        headers["X-PA"] = "1"
    h.request(method, path, body=json.dumps(body or {}).encode() if method == "POST" else None, headers=headers)
    r = h.getresponse()
    return r.status, json.loads(r.read() or b"{}")


def test_blocks_other_hosts_and_plain_posts(srv):
    port, _ = srv
    assert req(port, "GET", "/api/files", host="evil.example")[0] == 403
    assert req(port, "POST", "/api/link", {"key": "m1", "path": "/etc/passwd"}, pa=False)[0] == 403
    assert req(port, "POST", "/api/ack", {"what": "x; DROP"})[0] == 400


def test_link_flow_respects_scope(srv, tmp_path):
    port, mat = srv
    st, j = req(port, "GET", "/api/files")
    assert st == 200 and [f["rel"] for f in j["files"]] == ["bio/3강.pdf"]
    assert req(port, "GET", "/api/ls?root=" + "%EC%9E%90%EB%A3%8C" + "&path=..")[0] == 400  # 범위 밖 폴더
    outside = tmp_path / "x.pdf"
    outside.write_bytes(b"x")
    st, j = req(port, "POST", "/api/link", {"key": "m1", "path": str(outside)})
    assert st == 400 and "범위 밖" in j["error"]
    f = str((mat / "bio" / "3강.pdf").resolve())
    assert req(port, "POST", "/api/link", {"key": "m1", "paths": [f]})[0] == 200
    st, j = req(port, "GET", "/api/links?key=m1")
    assert st == 200 and [x["p"] for x in j["links"]] == [f] and j["max"] == 3
    assert req(port, "POST", "/api/unlink", {"key": "m1", "path": f})[0] == 200
    assert req(port, "GET", "/api/links?key=m1")[1]["links"] == []
