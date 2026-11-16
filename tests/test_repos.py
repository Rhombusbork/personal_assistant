import subprocess

import pytest

from pa import db, repos


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def commit(repo, name, text):
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", name)


@pytest.fixture
def pair(tmp_path, monkeypatch):
    """원격(bare) + PC 쪽 복제(pc) + 휴대폰·클라우드 쪽 복제(cloud)"""
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    pc, cloud = tmp_path / "pc", tmp_path / "cloud"
    subprocess.run(["git", "clone", "-q", str(remote), str(cloud)], check=True, capture_output=True)
    git(cloud, "checkout", "-q", "-b", "main")
    commit(cloud, "a.md", "1")
    git(cloud, "push", "-q", "-u", "origin", "main")
    subprocess.run(["git", "clone", "-q", str(remote), str(pc)], check=True)
    monkeypatch.setattr(repos, "paths", lambda: [pc])
    return pc, cloud


def test_up_to_date(pair):
    pc, _ = pair
    assert repos.pull(pc)[0] == "ok"


def test_fast_forward(pair):
    pc, cloud = pair
    commit(cloud, "b.md", "from phone")
    git(cloud, "push", "-q")
    state, msg = repos.pull(pc)
    assert state == "pulled" and "1개" in msg
    assert (pc / "b.md").read_text(encoding="utf-8") == "from phone"


def test_diverged_left_alone(pair):
    pc, cloud = pair
    commit(cloud, "b.md", "cloud")
    git(cloud, "push", "-q")
    commit(pc, "c.md", "pc")
    head = subprocess.run(["git", "-C", str(pc), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    state, msg = repos.pull(pc)
    assert state == "warn" and "양쪽" in msg
    assert subprocess.run(["git", "-C", str(pc), "rev-parse", "HEAD"], capture_output=True, text=True).stdout == head


def test_dirty_overlap_left_alone(pair):
    pc, cloud = pair
    commit(cloud, "a.md", "cloud edit")
    git(cloud, "push", "-q")
    (pc / "a.md").write_text("unsaved pc edit", encoding="utf-8")
    state, _ = repos.pull(pc)
    assert state == "warn"
    assert (pc / "a.md").read_text(encoding="utf-8") == "unsaved pc edit"


def test_ahead_and_no_upstream(pair, tmp_path):
    pc, _ = pair
    commit(pc, "c.md", "pc only")
    assert repos.pull(pc)[0] == "ahead"
    git(pc, "checkout", "-q", "-b", "local-only")
    assert repos.pull(pc)[0] == "skip"
    assert repos.pull(tmp_path / "nope")[0] == "warn"


def test_warnings_saved_and_cleared(pair):
    pc, cloud = pair
    commit(cloud, "a.md", "cloud edit")
    git(cloud, "push", "-q")
    (pc / "a.md").write_text("unsaved", encoding="utf-8")
    repos.pull_all(log=lambda m: None)
    conn = db.connect()
    assert "pc:" in db.get_meta(conn, "repo_warnings")
    conn.close()
    (pc / "a.md").write_text("1", encoding="utf-8")  # 되돌리면 다음 확인에서 받고 경고가 사라짐
    repos.pull_all(log=lambda m: None)
    conn = db.connect()
    assert db.get_meta(conn, "repo_warnings") == ""
    assert conn.execute("SELECT COUNT(*) FROM events WHERE type = 'repo_pulled'").fetchone()[0] == 1
    conn.close()


def test_example_config_is_empty():
    from pa.config import ROOT
    import yaml
    cfg = yaml.safe_load((ROOT / "config" / "repos.example.yaml").read_text(encoding="utf-8"))
    assert cfg["pull_on_start"] == []
