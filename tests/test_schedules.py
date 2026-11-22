"""고급 예약: 저장 검사 · 반복 회차 · 때가 되면 한 번만 실행 · 늦으면 건너뜀 · 반복 예약 옮기기 · AI 지시는 답을 파일로 ·
예약 전 깨우기 시각 (진짜 AI·작업 스케줄러는 쓰지 않음)."""
from datetime import timedelta

import pytest

from pa import db, power, schedules
from pa.model import now


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    monkeypatch.setattr(schedules, "RESULTS", tmp_path / "ai-results")
    monkeypatch.setattr(schedules, "folders", lambda: {"공부": tmp_path})
    c = db.connect()
    db.sync_source(c, "canvas", [{"key": "m1", "kind": "lecture", "course": "생화학 1", "title": "17강",
                                  "due": (now() + timedelta(days=3)).isoformat(), "earliest": None, "minutes": 50, "url": "https://x"}])
    return c


def sched(c, start, every="", action="notices", **args):
    return schedules.save(c, {"title": "시험", "start": start.isoformat(), "end": (start + timedelta(minutes=30)).isoformat(),
                              "every": every, "action": action, "args": args})


def test_validation(conn):
    with pytest.raises(ValueError, match="할 말"):
        sched(conn, now(), action="prompt", folder="공부")
    with pytest.raises(ValueError, match="폴더"):
        sched(conn, now(), action="prompt", prompt="요약해줘", folder="없는 곳")
    with pytest.raises(ValueError, match="할 일"):
        sched(conn, now(), action="open_task")
    with pytest.raises(ValueError, match="골라"):
        sched(conn, now(), action="모름")


def test_weekly_occurrences_and_move_series(conn):
    first = now().replace(hour=9) + timedelta(days=1)
    sid = sched(conn, first, every="weekly")
    r = schedules.get(conn, sid)
    occ = schedules.occurrences(r, first - timedelta(days=1), first + timedelta(days=15))
    assert [s for s, e in occ] == [first, first + timedelta(days=7), first + timedelta(days=14)]
    second = first + timedelta(days=7)  # 둘째 회차를 1시간 늦게 끌면 → 모든 회차가 1시간 늦게
    schedules.move(conn, sid, second + timedelta(hours=1), second + timedelta(hours=1, minutes=30), orig=second)
    assert schedules.get(conn, sid)["start"] == (first + timedelta(hours=1)).isoformat()


def test_tick_runs_once_and_skips_late(conn):
    ran = []
    runner = lambda c, r, occ: ran.append((r["id"], occ)) or "ok"
    t0 = now() + timedelta(hours=1)
    sid = sched(conn, t0)
    assert schedules.tick(conn, t0 - timedelta(minutes=1), runner) == []
    assert [x[0] for x in schedules.tick(conn, t0 + timedelta(minutes=2), runner)] == [sid]
    assert schedules.tick(conn, t0 + timedelta(minutes=3), runner) == []  # 한 번만
    late = sched(conn, t0 + timedelta(hours=2))
    assert schedules.tick(conn, t0 + timedelta(hours=3), runner) == []   # 15분 넘게 늦음 → 건너뜀
    assert conn.execute("SELECT 1 FROM events WHERE type = 'schedule_missed' AND key = ?", (f"s{late}",)).fetchone()
    daily = sched(conn, t0 - timedelta(days=3), every="daily")           # 매일: 오늘 회차만
    got = schedules.tick(conn, (t0 - timedelta(days=3)) + timedelta(days=3, minutes=1), runner)
    assert [x[0] for x in got] == [daily]


def test_prompt_job_saves_answer(conn, monkeypatch):
    from pa import ai, jobs
    monkeypatch.setattr(ai, "ask", lambda prompt, **k: "1. 문제\n2. 문제")
    sid = sched(conn, now() + timedelta(minutes=5), action="prompt", prompt="이번 주 노트로 퀴즈 2문제", folder="공부")
    r = schedules.get(conn, sid)
    assert schedules.run_action(conn, r, now()).startswith("AI 작업")
    assert jobs.run_next(conn)
    job = conn.execute("SELECT status, result FROM jobs").fetchone()
    assert job["status"] == "done"
    text = open(job["result"], encoding="utf-8").read()
    assert "퀴즈 2문제" in text and "1. 문제" in text


def test_wake_times_only_for_things_i_set(conn):
    t = now() + timedelta(hours=3)
    sched(conn, t)
    db.add_slot(conn, "m1", t + timedelta(hours=1), t + timedelta(hours=2))
    got = power.wake_times(conn)
    assert got == [t - timedelta(minutes=5), t + timedelta(minutes=55)]
