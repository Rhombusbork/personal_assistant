"""🎓 새 점수 · 🗓 이번 주 돌아보기 · 기록 정리."""
from datetime import timedelta

import pytest

from pa import collect_canvas, db, render
from pa.model import now


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    return db.connect()


def g(key, at):
    return {"key": key, "course": "생화학 676209", "title": "퀴즈 " + key, "score": 8, "points": 10, "graded_at": at, "url": ""}


def test_first_sync_does_not_flood_old_grades(conn):
    old = (now() - timedelta(days=3)).isoformat()
    collect_canvas.save_grades(conn, [g("a1", old)])
    assert render.new_grades(conn) == []  # 처음엔 기록만
    assert not conn.execute("SELECT 1 FROM events WHERE type = 'grade_posted'").fetchone()
    new = (now() + timedelta(minutes=1)).isoformat()
    collect_canvas.save_grades(conn, [g("a1", old), g("a2", new)])
    assert [x["key"] for x in render.new_grades(conn)] == ["a2"]
    assert render.new_grades(conn)[0]["course"] == "생화학"
    assert conn.execute("SELECT COUNT(*) FROM events WHERE type = 'grade_posted'").fetchone()[0] == 1
    collect_canvas.save_grades(conn, [g("a1", old), g("a2", new)])  # 같은 점수는 다시 기록하지 않음
    assert conn.execute("SELECT COUNT(*) FROM events WHERE type = 'grade_posted'").fetchone()[0] == 1


def test_week_review_counts(conn):
    t = now()
    due_past = (t - timedelta(minutes=5)).isoformat() if t.weekday() or t.hour else t.isoformat()
    db.sync_source(conn, "canvas", [
        {"key": "a1", "kind": "assignment", "course": "", "title": "과제", "due": (t + timedelta(days=1)).isoformat(),
         "earliest": None, "minutes": 60, "url": ""},
        {"key": "m1", "kind": "lecture", "course": "", "title": "놓친 강의", "due": due_past, "earliest": None, "minutes": 50, "url": ""},
        {"key": "a2", "kind": "assignment", "course": "", "title": "다음 주 기말고사 준비",
         "due": (t + timedelta(days=7 - t.weekday() + 2)).isoformat(), "earliest": None, "minutes": 90, "url": ""}])
    db.set_status(conn, "a1", "done", "user")
    w = render.week_review(conn, t)
    assert w["done"] == {"assignment": 1} and w["nextCount"] == 1 and w["nextMinutes"] == 90
    assert w["nextExams"] == ["다음 주 기말고사 준비"]
    if t.weekday() or t.hour:  # 월요일 0시 직후가 아니면 '놓친 것'
        assert [m["title"] for m in w["missed"]] == ["놓친 강의"]


def test_prune_events(conn):
    conn.execute("INSERT INTO events (ts, type) VALUES (?, 'x')", ((now() - timedelta(days=400)).isoformat(),))
    db.log(conn, "y")
    assert db.prune_events(conn) == 1
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
