"""자동 조작 (출석·시험을 '돕는' 것까지): 확인창은 자리에 있을 때만 누르고 없으면 알림 · 끝난 블록에서 출석·제출 안 잡힘 알림 ·
시험·퀴즈 30분 전 점검. 진짜 브라우저·Windows 는 쓰지 않는다."""
from datetime import timedelta

import pytest

from pa import autoopen, autoplay, db, pipeline, power
from pa.model import now


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    c = db.connect()
    due = (now() + timedelta(hours=5)).isoformat()
    db.sync_source(c, "canvas", [
        {"key": "m1", "kind": "lecture", "course": "생화학 1", "title": "17강", "due": due, "earliest": None, "minutes": 50, "url": "https://x/1"},
        {"key": "a2", "kind": "quiz", "course": "생화학 1", "title": "17강 퀴즈", "due": due, "earliest": None, "minutes": 20, "url": "https://x/2"}])
    c.commit()
    return c


def test_continue_button_only_when_user_is_there(monkeypatch):
    pressed, alerts, clock = [], [], {"t": now()}
    monkeypatch.setattr(autoplay, "tab_open", lambda t: True)
    monkeypatch.setattr(autoplay.time, "sleep", lambda s: clock.update(t=clock["t"] + timedelta(seconds=s)))
    monkeypatch.setattr("pa.model.now", lambda: clock["t"])
    monkeypatch.setattr(autoplay, "press", lambda title, names, dry=False: "found" if dry else pressed.append(names[0]) or "invoked")
    monkeypatch.setattr(autoplay, "idle_seconds", lambda: 30)          # 자리에 있음 → 누름
    autoplay.watch("17강", clock["t"] + timedelta(minutes=2), alert=alerts.append)
    assert pressed and pressed[0] in autoplay.CONTINUE and not alerts
    pressed.clear()
    monkeypatch.setattr(autoplay, "idle_seconds", lambda: 900)         # 자리에 없음 → 안 누르고 한 번만 알림
    autoplay.watch("17강", clock["t"] + timedelta(minutes=3), alert=alerts.append)
    assert not [p for p in pressed if p in autoplay.CONTINUE] and len(alerts) == 1


def test_block_end_alerts_when_attendance_or_submission_missing(conn, monkeypatch):
    monkeypatch.setattr(pipeline.collect_canvas, "quick_done", lambda c: 0)
    pipeline._quick_check(["m1", "a2"])  # 엔진처럼 따로 연결 (같은 DB 파일)
    types = [r[0] for r in db.connect().execute("SELECT type FROM events WHERE type IN ('attendance_missing','submit_missing')")]
    assert sorted(types) == ["attendance_missing", "submit_missing"]


def test_exam_precheck_30_minutes_before(conn, monkeypatch):
    start = now() + timedelta(minutes=30)
    conn.execute("INSERT INTO plan VALUES ('a2', ?, ?, '퀴즈', NULL)", (start.isoformat(), (start + timedelta(minutes=20)).isoformat()))
    monkeypatch.setattr(autoopen, "cfg", lambda: dict(autoopen.DEFAULTS))
    monkeypatch.setattr(power, "battery", lambda: (40, False))
    monkeypatch.setattr(power, "keep_awake", lambda m: True)
    from pa import canvas
    monkeypatch.setattr(canvas, "get", lambda *a, **k: {})
    got = autoopen.precheck(conn, now())
    assert got and "배터리 40%" in got[0][1][0]
    assert autoopen.precheck(conn, now()) == []  # 한 번만
