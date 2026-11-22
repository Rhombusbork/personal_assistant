"""Canvas 제출: 진짜 Canvas 에 절대 보내지 않는다 (canvas.get/post/upload_file 을 가짜로)."""
import os
import time

import pytest

from pa import canvas, db, pdf, submit

URL = "https://canvas.example/courses/7/assignments/9"


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    c = db.connect()
    db.sync_source(c, "canvas", [{"key": "a9", "kind": "assignment", "course": "약학실습Ⅱ 1", "title": "12주차 결과보고서",
                                  "due": "2099-01-01T11:00:00+09:00", "earliest": None, "minutes": 60, "url": URL}])
    c.commit()
    return c


@pytest.fixture
def fake(monkeypatch):
    st = {"a": {"name": "12주차 결과보고서", "submission_types": ["online_upload"], "allowed_attempts": -1,
                "due_at": "2099-01-01T02:00:00Z", "lock_at": None, "locked_for_user": False},
          "sub": {"workflow_state": "submitted", "attempt": 1, "attachments": [{"display_name": "old.md", "size": 5}]},
          "uploads": [], "posts": []}

    def get(path, **k):
        return st["sub"] if path.endswith("/submissions/self") else st["a"]

    def upload_file(path, file):
        st["uploads"].append(file)
        return {"id": 42}

    def post(path, data):
        st["posts"].append(data)
        size = os.path.getsize(st["uploads"][-1])
        st["sub"] = {"workflow_state": "submitted", "attempt": st["sub"]["attempt"] + 1,
                     "attachments": [{"display_name": os.path.basename(st["uploads"][-1]), "size": size}]}
        return st["sub"]

    monkeypatch.setattr(canvas, "get", get)
    monkeypatch.setattr(canvas, "upload_file", upload_file)
    monkeypatch.setattr(canvas, "post", post)
    return st


def test_md_is_never_sent_pdf_is(conn, fake, tmp_path):
    md, out = tmp_path / "r.md", tmp_path / "r.pdf"
    out.write_bytes(b"%PDF-1.4 /Type /Page x %%EOF")
    time.sleep(0.01)
    md.write_text("# 보고서", encoding="utf-8")
    os.utime(out, (time.time() + 5, time.time() + 5))  # PDF 가 더 새것
    r = submit.submit(conn, "a9", str(md), reveal=False)
    assert fake["uploads"] == [out] and r["pages"] == 1 and r["attempt"] == 2
    assert fake["posts"][0]["submission[file_ids][]"] == [42]
    assert conn.execute("SELECT status FROM tasks WHERE key='a9'").fetchone()[0] == "done"
    assert submit.recent(conn)[0]["name"] == "r.pdf"


def test_newer_md_remakes_pdf(conn, fake, tmp_path, monkeypatch):
    md, out = tmp_path / "r.md", tmp_path / "r.pdf"
    out.write_bytes(b"%PDF old")
    os.utime(out, (time.time() - 60, time.time() - 60))
    md.write_text("# 새 원고", encoding="utf-8")
    made = []

    def make(p):
        made.append(p)
        out.write_bytes(b"%PDF new /Type /Page")
        return out, 1
    monkeypatch.setattr(pdf, "make", make)
    c = submit.check(conn, "a9", str(md))
    assert c["remake"] and not c["problems"]
    submit.submit(conn, "a9", str(md), reveal=False)
    assert made == [md] and fake["uploads"] == [out]


@pytest.mark.parametrize("change, word", [
    ({"locked_for_user": True}, "잠겨"),
    ({"allowed_attempts": 1}, "횟수"),
    ({"submission_types": ["online_text_entry"]}, "파일 올리기"),
    ({"allowed_extensions": ["docx"]}, "확장자"),
])
def test_refuses_and_sends_nothing(conn, fake, tmp_path, change, word):
    f = tmp_path / "r.pdf"
    f.write_bytes(b"%PDF x")
    fake["a"].update(change)
    with pytest.raises(submit.SubmitError, match=word):
        submit.submit(conn, "a9", str(f), reveal=False)
    assert fake["uploads"] == [] and fake["posts"] == []


def test_same_file_twice_is_refused(conn, fake, tmp_path):
    f = tmp_path / "r.pdf"
    f.write_bytes(b"%PDF x")
    submit.submit(conn, "a9", str(f), reveal=False)
    with pytest.raises(submit.SubmitError, match="이미 같은 파일"):
        submit.submit(conn, "a9", str(f), reveal=False)
    assert len(fake["uploads"]) == 1


def test_unverified_is_not_marked_done(conn, fake, tmp_path, monkeypatch):
    f = tmp_path / "r.pdf"
    f.write_bytes(b"%PDF x")
    monkeypatch.setattr(canvas, "post", lambda path, data: {})  # Canvas 가 제출을 안 받음
    with pytest.raises(submit.SubmitError, match="확인되지 않음"):
        submit.submit(conn, "a9", str(f), reveal=False)
    assert conn.execute("SELECT status FROM tasks WHERE key='a9'").fetchone()[0] == "open"
    assert submit.recent(conn) == []


def test_server_check_then_submit_and_phone_queue(conn, fake, tmp_path, monkeypatch):
    """대시보드 📤: 확인(아무것도 안 보냄) → 제출. 휴대폰 대기열로도 같은 요청이 된다. 막히면 글로 된 오류."""
    from pa import jobs, server
    f = tmp_path / "r.pdf"
    f.write_bytes(b"%PDF /Type /Page x")
    monkeypatch.setattr(jobs, "report_path", lambda t, c=None: f)
    c = server.side_action("/api/submit-check", {"key": "a9"}, remote=True)
    assert c["file"] == "r.pdf" and c["pages"] == 1 and c["problems"] == [] and fake["uploads"] == []
    assert "/api/submit" in server.PHONE_ACTIONS
    r = server.side_action("/api/submit", {"key": "a9"}, remote=True)  # remote: 탐색기 안 띄움
    assert r["ok"] and r["attempt"] == 2 and "제출됨" in r["message"]
    with pytest.raises(ValueError, match="이미 같은 파일"):
        server.side_action("/api/submit", {"key": "a9"}, remote=True)
