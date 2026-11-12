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


def test_notices_job_parses_suggestions(conn, monkeypatch):
    db.sync_source(conn, "canvas", [{"key": "a9", "kind": "assignment", "course": "생약학Ⅰ 676205", "title": "조별 보고서",
                                     "due": "2099-01-01T23:59:00+09:00", "earliest": None, "minutes": 60, "url": ""}])
    conn.execute("INSERT INTO notices (id, course, title, text, posted_at) VALUES ('n1', '생약학Ⅰ 676205', '공지', '조장만 제출', '2026-11-12')")
    monkeypatch.setattr(jobs.ai, "ask", lambda *a, **k: '{"summaries":[{"id":"n1","summary":"조장만 낸다"}],'
                                                        '"exclude":[{"key":"a9","reason":"조장만 제출"},{"key":"zzz","reason":"x"}]}')
    jobs.enqueue(conn, "notices", "notices", "새 공지 정리")
    jobs.run_next(conn)
    assert jobs.recent(conn)[0]["status"] == "done"
    assert conn.execute("SELECT summary FROM notices WHERE id='n1'").fetchone()[0] == "조장만 낸다"
    sugg = __import__("json").loads(db.get_meta(conn, "notice_suggestions"))
    assert [x["key"] for x in sugg] == ["a9"]  # 없는 키는 버림


def test_summary_job_writes_beside_material(conn, monkeypatch, tmp_path):
    from pa import materials
    root = tmp_path / "study"
    pdf = root / "materials" / "ethics" / "강의.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(materials, "_cfg", lambda: {"root": root, "courses": []})
    monkeypatch.setattr(materials, "open_file", lambda p: None)
    monkeypatch.setattr(jobs.ai, "ask", lambda *a, **k: "```markdown\n# 강의 요약\n내용\n```")
    jobs.enqueue(conn, "summary", str(pdf), "요약")
    jobs.run_next(conn)
    out = root / "materials" / "ethics" / "요약" / "강의_요약.md"
    assert out.read_text().startswith("# 강의 요약") and jobs.recent(conn)[0]["status"] == "done"
    outside = tmp_path / "x.pdf"; outside.write_bytes(b"%PDF")
    jobs.enqueue(conn, "summary", str(outside), "요약2")
    jobs.run_next(conn)
    assert jobs.recent(conn)[0]["status"] == "failed"  # materials 밖은 거절
