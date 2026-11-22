"""두 PC 같이 쓰기: 임시 git 저장소 하나에 PC 두 대(A·B 폴더)를 붙여 시험한다."""
import json
import sqlite3
import subprocess

import pytest

from pa import db, peer


def _pc(tmp_path, name, remote, priority, calls):
    root = tmp_path / name
    (root / "data").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "config" / "timetable.yaml").write_text("planner: {}\n", encoding="utf-8")
    (root / "inbox.md").write_text("# inbox\n\n## 할 일\n\n## 완료\n", encoding="utf-8")
    conn = sqlite3.connect(root / "data" / "pa.db")
    conn.executescript(db.SCHEMA)
    conn.commit()
    conn.close()

    def replay(action, body):
        calls.append((name, action, body))

    return peer.Peer(root=root, remote=str(remote), host=name, priority=priority, replay=replay)


@pytest.fixture
def two(tmp_path):
    remote = tmp_path / "state.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    calls = []
    a = _pc(tmp_path, "A", remote, 1, calls)
    b = _pc(tmp_path, "B", remote, 2, calls)
    return a, b, calls


def _add_task(p, key, title):
    conn = sqlite3.connect(p.data / "pa.db")
    conn.execute("INSERT INTO tasks (key, source, kind, title, status, minutes, first_seen, updated_at) VALUES (?, 'inbox', 'todo', ?, 'open', 30, 'x', 'x')",
                 (key, title))
    conn.commit()
    conn.close()


def _titles(p):
    conn = sqlite3.connect(p.data / "pa.db")
    try:
        return sorted(r[0] for r in conn.execute("SELECT title FROM tasks"))
    finally:
        conn.close()


def test_off_without_repo(tmp_path):
    p = peer.Peer(root=tmp_path, remote="")
    assert not p.enabled() and p.is_leader() and p.tick() == {}


def test_first_pc_leads_and_higher_priority_takes_over(two):
    a, b, calls = two
    _add_task(a, "i:1", "A 에서 만든 일")
    assert a.tick()["became"] == "leader" and a.is_leader()
    # B 가 켜짐: A 가 일하는 중 → 먼저 대기, A 가 넘겨주고, B 가 A 기록을 받아 일함
    assert b.tick()["became"] == "standby" and not b.is_leader()
    assert a.tick()["became"] == "standby" and not a.is_leader()
    assert b.tick()["became"] == "leader" and b.is_leader()
    assert _titles(b) == ["A 에서 만든 일"]
    # A 는 대기: 다시 맞춰도 계속 대기
    a.tick()
    assert not a.is_leader()


def test_standby_input_goes_to_leader_then_comes_back(two):
    a, b, calls = two
    a.tick(); b.tick(); a.tick(); b.tick()  # B 가 일하는 PC
    a.queue("/api/done", {"key": "i:1"})
    a.tick()  # 입력 올림
    b.tick()  # B 가 실행하고 acks
    assert calls == [("B", "/api/done", {"key": "i:1"})]
    _add_task(b, "i:2", "B 가 반영한 결과")
    b.tick()  # B 기록 올림
    a.tick()  # A: 다 받았음 확인 → 입력 비움 → B 기록으로 맞춤
    assert a.local()["outbox"] == []
    assert "B 가 반영한 결과" in _titles(a)
    b.tick()
    assert calls == [("B", "/api/done", {"key": "i:1"})]  # 두 번 실행하지 않음


def test_standby_inbox_edit_is_merged(two):
    a, b, calls = two
    a.tick(); b.tick(); a.tick(); b.tick()
    a.tick()  # A 가 B 기록(inbox 포함)으로 맞춤
    text = (a.root / "inbox.md").read_text(encoding="utf-8")
    (a.root / "inbox.md").write_text(text.replace("## 할 일\n", "## 할 일\n- A 에서 적은 일\n"), encoding="utf-8")
    assert a.inbox_changed()
    btext = (b.root / "inbox.md").read_text(encoding="utf-8")
    (b.root / "inbox.md").write_text(btext.replace("## 완료\n", "## 완료\n- B 에서 끝낸 일\n"), encoding="utf-8")
    a.tick(); b.tick()
    merged = (b.root / "inbox.md").read_text(encoding="utf-8")
    assert "- A 에서 적은 일" in merged and "- B 에서 끝낸 일" in merged


def test_config_change_travels(two):
    a, b, calls = two
    a.tick(); b.tick()
    (a.root / "config" / "timetable.yaml").write_text("planner: {max: 3}\n", encoding="utf-8")
    a.tick(); b.tick()
    assert (b.root / "config" / "timetable.yaml").read_text(encoding="utf-8") == "planner: {max: 3}\n"
    (b.root / "config" / "courses.yaml").write_text("courses: []\n", encoding="utf-8")
    b.tick(); a.tick()
    assert (a.root / "config" / "courses.yaml").exists()


def test_stale_leader_is_replaced(two, monkeypatch):
    a, b, calls = two
    a.tick(); b.tick(); a.tick(); b.tick()  # B 일함
    assert b.is_leader()
    # B 가 꺼짐 (노트북 덮음): 10분 넘게 소식 없음 → A 가 이어받음
    t = peer.time.time() + peer.STALE + 5
    monkeypatch.setattr(peer.time, "time", lambda: t)
    assert not b.is_leader()  # 잠에서 깬 B 는 맞추기 전까지 일하지 않는다
    assert a.tick()["became"] == "leader"
    # B 가 깨어남: A 신호가 새것이고 B 가 우선 → 다시 넘겨받는 흐름
    assert b.tick()["became"] == "standby"
    a.tick()
    assert b.tick()["became"] == "leader"


def test_copied_local_file_is_not_trusted(two):
    a, b, calls = two
    a.tick()
    (b.data / "peer.json").write_text((a.data / "peer.json").read_text(encoding="utf-8"), encoding="utf-8")
    assert not b.is_leader()  # A 에서 복사해 온 '일하는 PC' 표시를 믿지 않음


def test_local_meta_and_jobs_stay(two):
    a, b, calls = two
    conn = sqlite3.connect(a.data / "pa.db")
    conn.execute("INSERT INTO meta (k, v) VALUES ('autoopen:x', '1'), ('report_file:x', 'r.md')")
    conn.commit()
    conn.close()
    a.tick()
    rows = (a.dir / "db" / "meta.jsonl").read_text(encoding="utf-8")
    assert "report_file:x" in rows and "autoopen:x" not in rows
    assert not (a.dir / "db" / "jobs.jsonl").exists()
    assert json.loads(rows.splitlines()[0]) == ["k", "v"]


def test_engine_on_standby_only_draws(monkeypatch):
    from pa import pipeline
    drawn = []
    monkeypatch.setattr(peer, "is_leader", lambda: False)
    monkeypatch.setattr(peer, "get", lambda: type("P", (), {"inbox_changed": lambda self: False})())
    monkeypatch.setattr(pipeline, "_render_only", lambda: drawn.append(1))
    monkeypatch.setattr(pipeline, "_run", lambda *a, **k: pytest.fail("대기 PC 가 계획·캘린더를 씀"))
    pipeline.run(full=True)
    assert drawn == [1]


def test_takeover_replays_own_inputs_once(two, monkeypatch):
    """대기 때 한 입력이 아직 일하는 PC 에 안 갔는데 일하는 PC 가 사라짐 → 이어받은 PC 가 스스로 한 번만 실행."""
    a, b, calls = two
    a.tick(); b.tick(); a.tick(); b.tick()  # B 일함, A 대기
    a.tick()

    def like_server(action, body):  # 실제 서버처럼: 대기 PC 라고 생각하면 보낼 목록에 또 넣는다
        calls.append(("A", action, body))
        if not a.is_leader():
            a.queue(action, body)
    a.replay = like_server
    a.queue("/api/done", {"key": "i:9"})  # B 가 받기 전에 B 가 꺼짐
    t = peer.time.time() + peer.STALE + 5
    monkeypatch.setattr(peer.time, "time", lambda: t)
    assert a.tick()["became"] == "leader"
    assert calls == [("A", "/api/done", {"key": "i:9"})]
    assert a.local()["outbox"] == []
