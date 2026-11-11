"""inbox.md 섹션 동작: 체크, ## 완료, ## 제외, 줄 삭제."""
import pytest

from pa import db, inbox


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    monkeypatch.setattr(inbox, "PATH", tmp_path / "inbox.md")
    c = db.connect()
    db.sync_source(c, "canvas", [{"key": "a1", "kind": "assignment", "course": "생약학Ⅰ 676205",
                                  "title": "조별학습활동 보고서 제출 게시판", "due": "2099-01-01T23:59:00+09:00",
                                  "earliest": None, "minutes": 60, "url": ""}])
    return c


def write(body):
    inbox.PATH.write_text(body)


def status(c, key):
    return c.execute("SELECT status FROM tasks WHERE key = ?", (key,)).fetchone()["status"]


def test_checkbox_done_and_reopen(conn):
    write("## 할 일\n- [x] 보고서 @12-01\n")
    inbox.sync(conn)
    assert status(conn, "i:보고서") == "done"
    write("## 할 일\n- [ ] 보고서 @12-01\n")
    inbox.sync(conn)
    assert status(conn, "i:보고서") == "open"


def test_ignore_section_is_declarative(conn):
    write("## 할 일\n## 제외\n- 생약학 조별학습활동\n")
    assert inbox.sync(conn) == []
    assert status(conn, "a1") == "ignored"
    write("## 할 일\n## 제외\n")
    inbox.sync(conn)
    assert status(conn, "a1") == "open"


def test_done_section_is_sticky(conn):
    write("## 완료\n- a1\n")
    inbox.sync(conn)
    assert status(conn, "a1") == "done"
    write("## 완료\n")
    inbox.sync(conn)
    assert status(conn, "a1") == "done"


def test_removed_line_is_gone(conn):
    write("## 할 일\n- [ ] 논문 읽기\n")
    inbox.sync(conn)
    write("## 할 일\n")
    inbox.sync(conn)
    assert status(conn, "i:논문 읽기") == "gone"


def test_comments_ignored_and_warnings(conn):
    write("<!--\n- [ ] 예시 @11-20\n-->\n## 할 일\n- [ ] 잘못 @13-40\n## 완료\n- 없는항목\n")
    warns = inbox.sync(conn)
    assert len(warns) == 2
    assert conn.execute("SELECT COUNT(*) FROM tasks WHERE key = 'i:예시'").fetchone()[0] == 0


def test_every_creates_dated_instances(conn):
    write("## 할 일\n- [ ] 생화학 공부 ~1h 매주:월,화,수,목,금,토,일\n")
    inbox.sync(conn)
    n = conn.execute("SELECT COUNT(*) FROM tasks WHERE key LIKE 'i:생화학 공부@%'").fetchone()[0]
    assert n >= 14
