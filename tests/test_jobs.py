import pytest

from pa import db, jobs


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    return db.connect()


def test_queue_runs_once_and_records(conn, monkeypatch):
    calls = []
    monkeypatch.setitem(jobs.report_job.__globals__, "report_job", lambda c, j: calls.append(j["key"]) or "/tmp/x.md")
    a = jobs.enqueue(conn, "report", "a1", "과제1")
    assert jobs.enqueue(conn, "report", "a1", "과제1") == a  # 같은 작업은 한 번만
    assert jobs.run_next(conn) and not jobs.run_next(conn)
    j = jobs.recent(conn)[0]
    assert calls == ["a1"] and j["status"] == "done" and j["result"] == "/tmp/x.md"


def test_failure_is_recorded(conn, monkeypatch):
    def boom(c, j):
        raise ValueError("자료 없음")
    monkeypatch.setitem(jobs.report_job.__globals__, "report_job", boom)
    jobs.enqueue(conn, "report", "a2", "과제2")
    jobs.run_next(conn)
    j = jobs.recent(conn)[0]
    assert j["status"] == "failed" and "자료 없음" in j["error"]


def test_doc_kind():
    assert jobs.doc_kind("Ch22_배움노트작성_1장으로 정리") == "배움노트"
    assert jobs.doc_kind("리바이어던 발표자료 제출") == "발표자료"
    assert jobs.doc_kind("10주차 결과보고서") == "결과보고서"
