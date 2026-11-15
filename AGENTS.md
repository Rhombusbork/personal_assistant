# 개인 비서 — Codex 용 안내

이 저장소의 규칙 원본은 **CLAUDE.md** 다 (Claude Code 와 함께 쓰는 규칙). Codex 도 같은 규칙을 따른다.

1. 작업을 시작하기 전에 `CLAUDE.md` 를 읽고 그대로 따른다. 거기 적힌 `@config/profile.md` 는
   "`config/profile.md` 를 읽어라"는 뜻이다 (없으면 `config/profile.example.md`).
2. CLAUDE.md 가 말하는 연결된 프로젝트(`~/study_system`, `~/report`, 퀴즈)에서 일할 때는
   그 폴더의 `AGENTS.md` 를, 없으면 `CLAUDE.md` 를 먼저 읽는다.
3. 스킬(today·study·assignment·quiz·rules)은 `.agents/skills/` 에 있고, 본문은 `.claude/skills/<이름>/SKILL.md` 다.
4. Windows 에서는 명령의 `bin/pa` 를 `bin\pa.cmd` 로 쓴다.

규칙은 CLAUDE.md 와 `.claude/skills/` 에서만 고친다. `.agents/skills/` 는 `python scripts/sync_agents.py` 가 만든다.
