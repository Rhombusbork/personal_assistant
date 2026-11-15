"""AI 고르기 (PA_AI) 와 Codex·Claude 명령 줄 — CLI 를 실제로 부르지 않는다."""
import pytest

from pa import ai


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """설치된 CLI 와 실행을 가짜로: installed 에 넣은 것만 있다고 보고, 실행은 기록만."""
    installed, calls = set(), []
    monkeypatch.setattr(ai, "load_env", lambda: None)
    monkeypatch.delenv("PA_AI", raising=False)
    monkeypatch.setattr(ai, "_find", lambda kind: f"/bin/{kind}" if kind in installed else None)
    monkeypatch.setattr(ai, "_run", lambda cmd, cwd, timeout, stdin=None: calls.append((cmd, cwd, stdin)) or "답")
    return installed, calls


def test_default_prefers_claude_then_codex(fake, monkeypatch):
    installed, _ = fake
    with pytest.raises(SystemExit):
        ai.backend()
    installed.add("codex")
    assert ai.backend() == "codex"
    installed.add("claude")
    assert ai.backend() == "claude"
    monkeypatch.setenv("PA_AI", "codex")
    assert ai.backend() == "codex"


def test_unknown_or_missing_choice_is_explained(fake, monkeypatch):
    installed, _ = fake
    installed.add("claude")
    monkeypatch.setenv("PA_AI", "gemini")
    with pytest.raises(SystemExit, match="claude 또는 codex"):
        ai.backend()
    monkeypatch.setenv("PA_AI", "codex")  # 골랐는데 없으면 다른 걸로 몰래 바꾸지 않는다
    with pytest.raises(SystemExit, match="codex"):
        ai.backend()


def test_codex_is_read_only_and_gets_rules_from_claude_md(fake, monkeypatch, tmp_path):
    installed, calls = fake
    installed.add("codex")
    (tmp_path / "CLAUDE.md").write_text("규칙", encoding="utf-8")
    assert ai.ask("초안 써줘", cwd=tmp_path, add_dirs=[tmp_path / "mat"]) == "답"
    cmd, cwd, stdin = calls[0]
    assert cmd[:2] == ["/bin/codex", "exec"] and cmd[-1] == "-"
    assert cmd[cmd.index("--sandbox") + 1] == "read-only" and "--add-dir" not in cmd  # --add-dir 은 쓰기 권한
    assert cmd[cmd.index("--cd") + 1] == str(tmp_path) and cwd == tmp_path
    assert str(tmp_path / "CLAUDE.md") in stdin and str((tmp_path / "mat").resolve()) in stdin
    assert stdin.rstrip().endswith("초안 써줘")


def test_codex_uses_agents_md_when_present(fake, tmp_path):
    installed, calls = fake
    installed.add("codex")
    (tmp_path / "CLAUDE.md").write_text("규칙", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("규칙", encoding="utf-8")
    ai.ask("x", cwd=tmp_path)
    assert "CLAUDE.md" not in calls[0][2]


def test_claude_command_unchanged(fake, tmp_path):
    installed, calls = fake
    installed.add("claude")
    ai.ask("요약", cwd=tmp_path, add_dirs=[tmp_path])
    cmd = calls[0][0]
    assert cmd[:3] == ["/bin/claude", "-p", "요약"] and cmd[cmd.index("--allowedTools") + 1] == "Read"
    assert cmd[cmd.index("--add-dir") + 1] == str(tmp_path)
