"""시간 정하기 (slots): Canvas 항목도 고정 · 겹쳐도 됨 · 조각 하나만 옮기면 나머지는 자동 · 지난 시간은 무시.
진짜 Google 캘린더는 쓰지 않는다 (plan.fetch_busy 를 가짜로, write=False)."""
from datetime import timedelta

import pytest

from pa import db, inbox, plan, server
from pa.model import now


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    monkeypatch.setattr(inbox, "PATH", tmp_path / "inbox.md")
    monkeypatch.setattr(plan, "fetch_busy", lambda service, s, e: BUSY)
    c = db.connect()
    due = (now() + timedelta(days=5)).replace(hour=23, minute=59, second=0, microsecond=0)
    db.sync_source(c, "canvas", [
        {"key": "m1", "kind": "lecture", "course": "생화학 1", "title": "17강", "due": due.isoformat(), "earliest": None,
         "minutes": 50, "url": "https://x/1"},
        {"key": "a1", "kind": "assignment", "course": "생화학 1", "title": "보고서", "due": due.isoformat(), "earliest": None,
         "minutes": 240, "url": "https://x/courses/1/assignments/2"}])
    c.commit()
    BUSY.clear()
    return c


BUSY = []


def keys(p):
    return [t.key for t, s, e in p]


def at(hours, minutes=0):
    t = (now() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    return t + timedelta(hours=hours, minutes=minutes)


def test_whole_slot_replaces_auto_block_and_may_overlap_a_class(conn):
    BUSY.append((at(0), at(1, 15), "🏫 물리약학"))  # 수업과 겹치게 정해도 그대로
    k = server.move_block(conn, "m1", at(0, 30), at(1, 20))
    p, failed = plan.run(conn, service=object(), write=False)
    assert k.startswith("m1#고정") and k in keys(p)
    assert not [x for x in keys(p) if x == "m1"]  # 자동 블록은 없어짐
    blk = next((s, e) for t, s, e in p if t.key == k)
    assert blk == (at(0, 30), at(1, 20))


def test_moving_one_chunk_keeps_the_rest_automatic(conn):
    p, _ = plan.run(conn, service=object(), write=False)
    assert [x for x in keys(p) if x.startswith("a1#")] == ["a1#1", "a1#2", "a1#3"]
    k = server.move_block(conn, "a1#2", at(3), at(4, 30))  # 90분 조각 하나만
    p, _ = plan.run(conn, service=object(), write=False)
    a = [x for x in keys(p) if x.startswith("a1#")]
    assert k in a and len(a) == 3  # 정한 것 1 + 나머지 150분은 자동 2조각


def test_move_again_and_clear(conn):
    k = server.move_block(conn, "m1", at(2), at(3))
    assert server.move_block(conn, k, at(5), at(6)) == k  # 같은 블록을 다시 옮김
    assert db.slots(conn)[0]["start"] == at(5).isoformat()
    server.clear_block(conn, k)
    p, _ = plan.run(conn, service=object(), write=False)
    assert "m1" in keys(p) and not db.slots(conn)


def test_rejects_past_and_bad_ranges(conn):
    with pytest.raises(ValueError, match="지난 시간"):
        server.move_block(conn, "m1", now() - timedelta(hours=3), now() - timedelta(hours=2))
    with pytest.raises(ValueError, match="올바르지"):
        server.move_block(conn, "m1", at(3), at(2))


def test_past_slot_is_ignored(conn):
    conn.execute("INSERT INTO slots (key, start, end, part, created) VALUES ('m1', ?, ?, 0, ?)",
                 ((now() - timedelta(hours=3)).isoformat(), (now() - timedelta(hours=2)).isoformat(), now().isoformat()))
    p, _ = plan.run(conn, service=object(), write=False)
    assert "m1" in keys(p)  # 지난 정한 시간은 무시 → 다시 자동 배치


def test_inbox_task_slot_goes_to_inbox_line(conn):
    inbox.PATH.write_text("## 할 일\n- [ ] 발표 준비 @12-30 ~2h\n", encoding="utf-8")
    inbox.sync(conn)
    k = server.move_block(conn, "i:발표 준비", at(1), at(3))
    assert k == "i:발표 준비#고정"
    line = inbox.PATH.read_text(encoding="utf-8")
    assert f">{at(1):%m-%d} 11:00-13:00" in line and "@12-30" in line
    inbox.sync(conn)
    server.clear_block(conn, k)
    assert ">" not in inbox.PATH.read_text(encoding="utf-8").split("발표 준비")[1].split("\n")[0]


def test_move_and_unslot_through_http(conn, monkeypatch):
    """대시보드 요청 그대로 (do_POST 안의 이름 겹침 같은 실수를 잡는다)."""
    import http.client
    import json
    import threading
    from http.server import ThreadingHTTPServer
    monkeypatch.setattr(server.Handler, "on_change", None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def post(path, body):
        c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
        c.request("POST", path, json.dumps(body), {"Host": "localhost:8765", "X-PA": "1", "Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, json.loads(r.read())
    try:
        st, r = post("/api/move", {"key": "m1", "start": at(1).isoformat(), "end": at(2).isoformat()})
        assert st == 200 and r["key"].startswith("m1#고정")
        st, r = post("/api/unslot", {"key": r["key"]})
        assert st == 200 and not db.slots(db.connect())
        sid = post("/api/schedule/save", {"title": "공지", "start": at(3).isoformat(), "end": at(4).isoformat(), "every": "", "action": "notices", "args": {}})[1]["id"]
        st, r = post("/api/schedule/move", {"id": sid, "start": at(5).isoformat(), "end": at(6).isoformat(), "orig": at(3).isoformat()})
        assert st == 200 and r["ok"]
    finally:
        httpd.shutdown()


def test_change_during_planning_is_not_lost(conn, monkeypatch):
    """계획을 짜는 동안(캘린더 통신 중) 바뀐 입력은 다음에 다시 짠다 — 지문은 짜기 전에 찍는다."""
    k = server.move_block(conn, "m1", at(1), at(2))
    def slow_calendar(service, p, old, t_now, remind=0, force=False):  # 통신하는 사이에 사용자가 되돌리기
        server.clear_block(conn, k)
        conn.commit()
        return []
    monkeypatch.setattr(plan, "sync_calendar", slow_calendar)
    monkeypatch.setattr(plan, "reminders", lambda: {"plan": 0})
    plan.run(conn, service=object(), write=True)
    assert plan.needed(conn)  # 되돌린 것이 반영되도록 다시 짜야 함


def test_recurring_inbox_instance_goes_to_slots(conn):
    inbox.PATH.write_text("## 할 일\n- [ ] 텍스트 정리 ~1h 매주:수\n", encoding="utf-8")
    inbox.sync(conn)
    key = conn.execute("SELECT key FROM tasks WHERE key LIKE 'i:텍스트 정리@%' AND status = 'open' ORDER BY key LIMIT 1").fetchone()[0]
    k = server.move_block(conn, key, at(1), at(2))
    assert "#고정" in k and db.slots(conn, key=key) and ">" not in inbox.PATH.read_text(encoding="utf-8")
    server.clear_block(conn, k)
    assert not db.slots(conn)
