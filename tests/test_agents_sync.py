"""Codex 용 스킬(.agents/skills/)이 Claude 스킬과 맞는지 — 어긋나면 python scripts/sync_agents.py"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("sync_agents", ROOT / "scripts" / "sync_agents.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def test_codex_skills_match_claude_skills():
    have = {d.name: (d / "SKILL.md").read_text(encoding="utf-8") for d in sync.DST.iterdir() if (d / "SKILL.md").exists()}
    assert have == sync.expected(), "python scripts/sync_agents.py 를 실행하세요"
