import json
import os
import time
from datetime import datetime, timedelta

import pytest

from pa import db, quiz
from pa.model import KST


def at(days_ago):
    return datetime.now(KST) - timedelta(days=days_ago)


def test_next_review_intervals():
    d0 = at(0)
    assert quiz.next_review([(d0, False)]) == (d0 + timedelta(days=1)).date()           # 틀림 → 다음 날
    assert quiz.next_review([(d0, True)]) == (d0 + timedelta(days=1)).date()            # 1번 맞음 → 1일
    assert quiz.next_review([(d0, True)] * 3) == (d0 + timedelta(days=7)).date()        # 3연속 → 7일
    assert quiz.next_review([(d0, True)] * 9) == (d0 + timedelta(days=30)).date()       # 최대 30일
    assert quiz.next_review([(d0, True), (d0, False), (d0, True)]) == (d0 + timedelta(days=1)).date()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    backup = tmp_path / "quizapp-backup-test.json"
    monkeypatch.setattr(quiz, "latest_backup", lambda: backup)
    monkeypatch.setattr(quiz, "decks", lambda: {"biochem-01": {"subject": "생화학", "title": "아미노산"}})
    return db.connect(), backup


def write_backup(path, log, age_days=0):
    path.write_text(json.dumps({"questionStats": {}, "sessions": [], "bookmarks": [], "answerLog": log}))
    t = time.time() - age_days * 86400
    os.utime(path, (t, t))


def test_review_task_for_wrong_answers_and_done_after_reexport(env):
    conn, backup = env
    log = [{"qid": "biochem-01/1", "correct": False, "at": at(1).isoformat()},
           {"qid": "biochem-01/2", "correct": False, "at": at(1).isoformat()},
           {"qid": "old-deck/1", "correct": False, "at": at(1).isoformat()}]  # 지금 앱에 없는 덱
    write_backup(backup, log)
    assert quiz.sync(conn) == 3
    rows = conn.execute("SELECT key, title, status FROM tasks WHERE source='quiz'").fetchall()
    assert len(rows) == 1 and "아미노산" in rows[0]["title"] and "틀린 2" in rows[0]["title"]
    key = rows[0]["key"]
    # 다시 풀어 맞히고 내보내기 → 복습 할 일은 자동 완료
    log += [{"qid": "biochem-01/1", "correct": True, "at": at(0).isoformat()},
            {"qid": "biochem-01/2", "correct": True, "at": at(0).isoformat()}]
    time.sleep(0.01)
    write_backup(backup, log)
    os.utime(backup, None)
    quiz.sync(conn)
    assert conn.execute("SELECT status FROM tasks WHERE key=?", (key,)).fetchone()[0] == "done"


def test_stale_backup_makes_no_tasks(env):
    conn, backup = env
    write_backup(backup, [{"qid": "biochem-01/1", "correct": False, "at": at(30).isoformat()}], age_days=30)
    quiz.sync(conn)
    assert conn.execute("SELECT COUNT(*) FROM tasks WHERE source='quiz' AND status='open'").fetchone()[0] == 0
    assert quiz.status(conn)["stale"] is True
