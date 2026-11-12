"""다시 계획·마감 캘린더가 필요한지 (불필요한 Google 요청 줄이기)."""
from datetime import timedelta

import pytest

from pa import db, deadlines, plan
from pa.deadlines import _remind_minutes
from pa.model import now


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    c = db.connect()
    db.sync_source(c, "canvas", [{"key": "a1", "kind": "assignment", "course": "", "title": "과제",
                                  "due": (now() + timedelta(days=2)).isoformat(), "earliest": None, "minutes": 60, "url": ""}])
    return c


def test_plan_needed_only_when_something_changes(conn):
    assert plan.needed(conn)  # 처음
    db.set_meta(conn, "plan_sig", plan.signature(conn))
    db.set_meta(conn, "planned_at", now().isoformat())
    assert not plan.needed(conn)  # 그대로면 필요 없음
    conn.execute("UPDATE tasks SET minutes = 90 WHERE key = 'a1'")
    assert plan.needed(conn)  # 예상 시간이 바뀜
    db.set_meta(conn, "plan_sig", plan.signature(conn))
    db.set_meta(conn, "planned_at", (now() - timedelta(minutes=61)).isoformat())
    assert plan.needed(conn)  # 한 시간 지남 (새 약속 반영)


def test_plan_needed_when_block_passed(conn):
    db.set_meta(conn, "plan_sig", plan.signature(conn))
    db.set_meta(conn, "planned_at", (now() - timedelta(minutes=30)).isoformat())
    conn.execute("INSERT INTO plan VALUES ('a1', ?, ?, 's', 'e')",
                 ((now() - timedelta(minutes=20)).isoformat(), (now() - timedelta(minutes=5)).isoformat()))
    assert plan.needed(conn)  # 계획 블록이 지나감 → 놓친 일 옮기기


def test_deadlines_needed(conn):
    assert deadlines.needed(conn)
    db.set_meta(conn, "deadlines_sig", deadlines.signature(conn))
    db.set_meta(conn, "deadlines_synced_at", now().isoformat())
    assert not deadlines.needed(conn)
    db.set_status(conn, "a1", "done", "auto")
    assert deadlines.needed(conn)


def test_reminder_order_does_not_matter():
    a = {"useDefault": False, "overrides": [{"method": "popup", "minutes": 150}, {"method": "popup", "minutes": 30}]}
    b = {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}, {"method": "popup", "minutes": 150}]}
    assert _remind_minutes(a) == _remind_minutes(b)
