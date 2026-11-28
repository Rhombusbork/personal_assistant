from datetime import datetime, timedelta

import pytest

from pa import autoopen, db, jobs
from pa.model import KST

T0 = datetime(2026, 11, 23, 14, 0, tzinfo=KST)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    monkeypatch.setattr(autoopen, "load_timetable", lambda: {"auto_open": {"late_limit_minutes": 15, "draft_hours_before": 3}})
    monkeypatch.setattr(jobs, "REPORT_DIR", tmp_path / "report")
    monkeypatch.setattr(jobs, "student", lambda: ("2024", "나"))
    c = db.connect()
    db.sync_source(c, "canvas", [
        {"key": "l1", "kind": "lecture", "course": "생약학Ⅰ", "title": "10주차 강의", "due": "2099-01-01T23:59:00+09:00",
         "earliest": None, "minutes": 50, "url": "https://canvas/lecture"},
        {"key": "a1", "kind": "assignment", "course": "생약학Ⅰ", "title": "조별 보고서", "due": "2099-01-01T23:59:00+09:00",
         "earliest": None, "minutes": 60, "url": "https://canvas/assign"},
    ])
    c.executemany("INSERT INTO plan VALUES (?, ?, ?, ?, ?)", [
        ("l1", T0.isoformat(), (T0 + timedelta(minutes=50)).isoformat(), "[강의]", None),
        ("a1#1", (T0 + timedelta(hours=5)).isoformat(), (T0 + timedelta(hours=6)).isoformat(), "[과제]", None),
    ])
    c.commit()
    return c


def _opened(conn, t):
    got = []
    autoopen.check(conn, t, opener=lambda c, task: got.append(task["key"]) or [])
    return got


def test_opens_once_when_block_starts(conn):
    assert _opened(conn, T0 - timedelta(minutes=1)) == []
    assert _opened(conn, T0 + timedelta(minutes=2)) == ["l1"]
    assert _opened(conn, T0 + timedelta(minutes=3)) == []  # 한 번만


def test_late_wake_does_not_open(conn):
    assert _opened(conn, T0 + timedelta(minutes=30)) == []
    assert conn.execute("SELECT COUNT(*) FROM events WHERE type = 'autoopen_missed'").fetchone()[0] == 1


def test_done_task_is_not_opened(conn):
    conn.execute("UPDATE tasks SET status = 'done' WHERE key = 'l1'")
    assert _opened(conn, T0 + timedelta(minutes=1)) == []


def test_off_without_config(conn, monkeypatch):
    monkeypatch.setattr(autoopen, "load_timetable", lambda: {})
    assert _opened(conn, T0 + timedelta(minutes=1)) == []


def test_assignment_draft_queued_before_block(conn):
    _opened(conn, T0 + timedelta(hours=1))  # 과제 블록 4시간 전 → 아직
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    _opened(conn, T0 + timedelta(hours=2, minutes=30))  # 2시간 30분 전 → 초안 맡김 (열지 않는 종류)
    _opened(conn, T0 + timedelta(hours=3))
    rows = conn.execute("SELECT kind, key FROM jobs").fetchall()
    assert [tuple(r) for r in rows] == [("report-auto", "a1")]


def test_assignment_opens_draft_folder_and_submit_page(conn, monkeypatch, tmp_path):
    from pa import materials
    calls = []
    monkeypatch.setattr(materials, "open_file", lambda p: calls.append(("file", p.name)))
    monkeypatch.setattr(materials, "reveal", lambda p: calls.append(("reveal", p.name)))
    monkeypatch.setattr(autoopen.osutil, "open_url", lambda u: calls.append(("url", u)))
    task = dict(conn.execute("SELECT * FROM tasks WHERE key = 'a1'").fetchone())
    path = jobs.report_path(task, conn)
    path.parent.mkdir(parents=True)
    path.write_text("# 초안\n", encoding="utf-8")
    db.set_meta(conn, "report_file:a1", str(path))  # 초안 작업이 기억해 두는 파일
    assert autoopen.open_task(conn, task) == ["초안", "탐색기", "제출 페이지"]
    assert calls == [("file", path.name), ("reveal", path.name), ("url", "https://canvas/assign")]


def test_plan_reminder_at_start():
    from pa.config import popup
    assert [o["minutes"] for o in popup([10, 0])["overrides"]] == [10, 0]
    assert popup(0)["overrides"] == []


def test_lecture_page_then_play_button(conn, monkeypatch):
    calls = []
    monkeypatch.setattr(autoopen.osutil, "open_url", lambda u: calls.append(u))
    monkeypatch.setattr(autoopen, "_play", lambda title, *a: calls.append("play:" + title))
    task = dict(conn.execute("SELECT * FROM tasks WHERE key = 'l1'").fetchone())
    assert autoopen.open_task(conn, task) == ["페이지", "재생"]
    import time
    time.sleep(0.1)  # 재생은 뒤에서 (페이지가 뜰 때까지 기다리므로)
    assert calls == ["https://canvas/lecture", "play:10주차 강의"]


def test_dashboard_closed_does_not_open(conn):
    got = []
    autoopen.check(conn, T0 + timedelta(minutes=2), opener=lambda c, task: got.append(task["key"]) or [], viewing=False)
    assert got == []
    assert _opened(conn, T0 + timedelta(minutes=5)) == ["l1"]  # 늦게라도 대시보드를 열면 그때 연다
