import os
import time
from datetime import timedelta

import pytest

from pa import ai, db, jobs, materials, quizhelp
from pa.model import now


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    shots = tmp_path / "Screenshots"
    shots.mkdir()
    monkeypatch.setattr(quizhelp, "load_timetable", lambda: {"quiz_help": {"minutes": 120, "screenshots_dir": str(shots)}})
    root = tmp_path / "study"
    (root / "materials" / "pharmacognosy").mkdir(parents=True)
    monkeypatch.setattr(materials, "_cfg", lambda: {"root": root, "courses": [
        {"match": ["생약학"], "materials": "pharmacognosy", "notes": "생약학"}]})
    monkeypatch.setattr(materials, "open_file", lambda p: None)
    conn = db.connect()
    task = {"key": "q1", "kind": "quiz", "title": "11주차 퀴즈", "course": "생약학Ⅰ 676205"}
    return conn, shots, root, task


def _shot(shots, name, age=0):
    f = shots / name
    f.write_bytes(b"\x89PNG")
    t = time.time() - age
    os.utime(f, (t, t))
    return f


def test_only_screenshots_taken_while_on_are_sent(env):
    conn, shots, root, task = env
    _shot(shots, "old.png", age=3600)
    assert quizhelp.scan(conn) == 0  # 꺼져 있음
    quizhelp.start(conn, task, now() - timedelta(minutes=1))
    _shot(shots, "new.png")
    assert quizhelp.scan(conn) == 1
    assert quizhelp.scan(conn) == 0  # 같은 사진은 한 번만
    pics = list((root / "materials" / "pharmacognosy" / "퀴즈풀이").glob("*/문제_01.png"))
    assert len(pics) == 1
    assert [r["kind"] for r in conn.execute("SELECT kind FROM jobs")] == ["quizhelp"]


def test_expired_help_sends_nothing(env):
    conn, shots, _, task = env
    quizhelp.start(conn, task, now() - timedelta(hours=3))
    _shot(shots, "late.png")
    assert quizhelp.scan(conn) == 0


def test_job_appends_answer_and_runs_beside_reports(env, monkeypatch):
    conn, shots, root, task = env
    quizhelp.start(conn, task, now() - timedelta(minutes=1))
    _shot(shots, "a.png")
    quizhelp.scan(conn)
    seen = {}
    monkeypatch.setattr(ai, "ask", lambda prompt, **k: seen.update(k) or "1. **답**: ③")
    jobs.enqueue(conn, "report", "a1", "보고서")  # 보고서 초안이 기다리고 있어도
    assert jobs.run_next(conn, quick=True)  # 퀴즈 풀이는 따로 처리
    assert conn.execute("SELECT status FROM jobs WHERE kind = 'report'").fetchone()[0] == "queued"
    out = next((root / "materials" / "pharmacognosy" / "퀴즈풀이").glob("*/풀이.md"))
    text = out.read_text(encoding="utf-8")
    assert "![문제_01](문제_01.png)" in text and "③" in text
    assert seen["images"][0].name == "문제_01.png"


def test_quiz_runner_does_not_take_other_jobs(env):
    conn, *_ = env
    jobs.enqueue(conn, "notices", "notices", "공지")
    assert not jobs.run_next(conn, quick=True)
