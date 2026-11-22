"""자동 제출: 시간을 정했거나 켠 과제만 · 늦어도 마감 6시간 전 · 초안이 없으면 AI 초안을 먼저 맡김 · 빈칸이 남으면 안 냄 ·
낸 뒤 '확인 필요' → ✅ 완성. 진짜 Canvas·Google·AI 는 쓰지 않는다."""
import os
from datetime import timedelta

import pytest

from pa import autosubmit, canvas, db, jobs
from pa.model import now

URL = "https://canvas.example/courses/7/assignments/9"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    c = db.connect()
    due = now() + timedelta(days=2)
    db.sync_source(c, "canvas", [{"key": "a9", "kind": "assignment", "course": "약학실습Ⅱ 1", "title": "13주차 결과보고서",
                                  "due": due.isoformat(), "earliest": None, "minutes": 60, "url": URL}])
    c.commit()
    md = tmp_path / "r.md"
    monkeypatch.setattr(jobs, "report_path", lambda t, conn=None: md)
    st = {"uploads": [], "sub": {"workflow_state": "unsubmitted", "attempt": 0, "attachments": []}}

    def get(path, **k):
        if path.endswith("/submissions/self"):
            return st["sub"]
        return {"name": "13주차 결과보고서", "submission_types": ["online_upload"], "allowed_attempts": -1,
                "due_at": due.isoformat(), "lock_at": None, "locked_for_user": False}

    def upload_file(path, file):
        st["uploads"].append(file)
        return {"id": 1}

    def post(path, data):
        f = st["uploads"][-1]
        st["sub"] = {"workflow_state": "submitted", "attempt": st["sub"]["attempt"] + 1,
                     "attachments": [{"display_name": os.path.basename(f), "size": os.path.getsize(f)}]}
        return st["sub"]

    monkeypatch.setattr(canvas, "get", get)
    monkeypatch.setattr(canvas, "upload_file", upload_file)
    monkeypatch.setattr(canvas, "post", post)

    def fake_pdf(p):
        out = p.with_suffix(".pdf")
        out.write_bytes(b"%PDF /Type /Page " + p.read_bytes())
        return out, 1
    from pa import pdf
    monkeypatch.setattr(pdf, "make", fake_pdf)
    return c, md, due, st


def test_only_reserved_or_turned_on(env):
    c, md, due, st = env
    assert autosubmit.candidates(c) == []                 # 시간을 안 정했고 켜지도 않음
    db.add_slot(c, "a9", now() + timedelta(hours=1), now() + timedelta(hours=2))
    assert [t.key for t in autosubmit.candidates(c)] == ["a9"]
    autosubmit.set_flag(c, "a9", False)                   # 끄면 시간을 정했어도 안 냄
    assert autosubmit.candidates(c) == []
    autosubmit.set_flag(c, "a9", True)
    c.execute("DELETE FROM slots")
    assert [t.key for t in autosubmit.candidates(c)] == ["a9"]  # 켜기만 해도


def test_submit_time_is_slot_end_but_at_latest_6h_before_due(env):
    c, md, due, st = env
    t = lambda: autosubmit.candidates(c)[0]
    autosubmit.set_flag(c, "a9", True)
    assert autosubmit.submit_at(c, t()) == due - timedelta(hours=6)
    end = now() + timedelta(hours=3)
    db.add_slot(c, "a9", end - timedelta(hours=1), end)
    assert autosubmit.submit_at(c, t()) == end


def test_drafts_first_then_submits_then_needs_review(env, monkeypatch):
    c, md, due, st = env
    end = now() + timedelta(hours=1)
    db.add_slot(c, "a9", end - timedelta(hours=1), end)
    assert autosubmit.tick(c, now() - timedelta(hours=1)) == [] and not c.execute("SELECT 1 FROM jobs").fetchone()  # 아직 이름
    assert autosubmit.tick(c, now()) == []                 # 90분 안 → 초안을 맡김
    job = c.execute("SELECT kind, key FROM jobs").fetchone()
    assert tuple(job) == ("report-submit", "a9") and autosubmit.state(c, "a9")["state"] == "drafting"
    md.write_text("# 13주차 결과보고서\n본문\n", encoding="utf-8")  # 초안이 생김
    assert autosubmit.tick(c, now()) == []                 # 아직 제출 시각 전
    assert autosubmit.tick(c, end + timedelta(minutes=1)) == ["a9"]
    assert st["uploads"][0].suffix == ".pdf"               # .md 는 안 보냄
    rv = autosubmit.reviews(c)
    assert [r["key"] for r in rv] == ["a9"] and rv[0]["attempt"] == 1
    assert autosubmit.tick(c, end + timedelta(minutes=2)) == []  # 한 번만
    ev = autosubmit.wanted_events(c, now())
    assert {k.split("|")[1] for k in ev} == {"now", "later", "due"}
    autosubmit.confirm(c, "a9")
    assert autosubmit.reviews(c) == [] and autosubmit.wanted_events(c, now()) == {}


def test_blank_placeholder_stops_auto_submit(env):
    c, md, due, st = env
    autosubmit.set_flag(c, "a9", True)
    md.write_text("# 보고서\n[✍ 내 생각: 여기에 느낀 점]\n", encoding="utf-8")
    assert autosubmit.tick(c, due - timedelta(hours=5)) == []
    s = autosubmit.state(c, "a9")
    assert s["state"] == "failed" and "빈칸" in s["why"] and st["uploads"] == []


def test_draft_job_failure_is_reported(env):
    c, md, due, st = env
    autosubmit.set_flag(c, "a9", True)
    autosubmit.tick(c, due - timedelta(hours=7))
    c.execute("UPDATE jobs SET status = 'failed', error = 'AI 없음'")
    autosubmit.tick(c, due - timedelta(hours=7))
    s = autosubmit.state(c, "a9")
    assert s["state"] == "failed" and "AI 초안 실패" in s["why"]
    up = autosubmit.upcoming(c)
    assert up[0]["state"] == "failed" and not up[0]["draft"]
