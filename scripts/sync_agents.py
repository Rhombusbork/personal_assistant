"""Codex 용 스킬(.agents/skills/) 을 Claude 스킬(.claude/skills/) 에서 만든다: python scripts/sync_agents.py

원본은 .claude/skills/<이름>/SKILL.md 하나. Codex 용은 같은 name·description 에 "원본을 읽어라"만 적는다
(본문을 두 벌 두면 한쪽만 고치는 일이 생긴다). tests/test_agents_sync.py 가 어긋나면 알려 준다.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, DST = ROOT / ".claude" / "skills", ROOT / ".agents" / "skills"


def frontmatter(text):
    _, head, _ = text.split("---", 2)
    return head.strip()


def expected():
    """{스킬 이름: Codex 용 SKILL.md 내용}"""
    out = {}
    for f in sorted(SRC.glob("*/SKILL.md")):
        name = f.parent.name
        out[name] = (f"---\n{frontmatter(f.read_text(encoding='utf-8'))}\n---\n\n"
                     f"이 스킬의 본문은 `.claude/skills/{name}/SKILL.md` 다 (Claude Code 와 함께 쓰는 원본).\n"
                     f"그 파일을 읽고 단계를 그대로 따른다. Windows 에서는 `bin/pa` 를 `bin\\pa.cmd` 로 쓴다.\n")
    return out


def main():
    want = expected()
    for d in DST.glob("*") if DST.exists() else []:
        if d.name not in want:
            shutil.rmtree(d)
    for name, text in want.items():
        (DST / name).mkdir(parents=True, exist_ok=True)
        (DST / name / "SKILL.md").write_text(text, encoding="utf-8")
    print(f"{DST.relative_to(ROOT)}: {', '.join(want)}")


if __name__ == "__main__":
    main()
