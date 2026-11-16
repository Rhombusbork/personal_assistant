"""켤 때 내 git 저장소 내려받기: config/repos.yaml 의 pull_on_start

엔진이 켜질 때 한 번 (코드가 바뀌어 스스로 다시 시작할 때는 건너뜀), 각 폴더의 지금 브랜치를
원격(추적 브랜치)과 대조해 새 커밋이 있으면 fast-forward 로만 받는다. 휴대폰·클라우드 세션에서
바꾼 공부 기록·보고서·퀴즈가 PC 에도 들어오게 하려는 것.

- 내 쪽에 올리지 않은 커밋이 있어 갈라졌거나, 저장 안 한 변경과 겹치면 건드리지 않고 ⚠️ 로 알린다.
- 올리지(push) 않는다. 문제는 meta 'repo_warnings' 에 남겨 TODAY.md·대시보드의 '확인 필요'에 보인다.
"""
import os
import subprocess
from pathlib import Path

from pa import db
from pa.config import ROOT, load_yaml

# 로그인이 끊겨도 창·입력 대기로 멈추지 않게 (Git Credential Manager 포함)
GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "LC_ALL": "C"}


def paths():
    out = []
    for p in load_yaml("repos").get("pull_on_start") or []:
        p = Path(os.path.expanduser(str(p)))
        out.append(p if p.is_absolute() else (ROOT / p).resolve())
    return out


def _git(repo, *args, timeout=60):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, env={**os.environ, **GIT_ENV})


def _last_line(r):
    lines = (r.stderr or r.stdout or "").strip().splitlines()
    return lines[-1] if lines else f"git 종료 코드 {r.returncode}"


def pull(repo):
    """폴더 하나 → (상태, 설명). 상태: 'pulled' | 'ok' | 'ahead' | 'skip' | 'warn'"""
    name = repo.name
    if not (repo / ".git").exists():
        return "warn", f"{name}: git 저장소가 아니에요 ({repo}) — config/repos.yaml 확인"
    try:
        if _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode:
            return "skip", f"{name}: 지금 브랜치에 연결된 원격 브랜치가 없어 건너뜀"
        r = _git(repo, "fetch", "--quiet", timeout=120)
        if r.returncode:
            return "warn", f"{name}: GitHub 에서 확인 못 함 (인터넷·로그인?) — {_last_line(r)}"
        r = _git(repo, "rev-list", "--left-right", "--count", "HEAD...@{u}")
        if r.returncode:
            return "warn", f"{name}: 비교 실패 — {_last_line(r)}"
        ahead, behind = (int(x) for x in r.stdout.split())
        if not behind:
            return ("ahead", f"{name}: 올리지 않은 커밋 {ahead}개") if ahead else ("ok", f"{name}: 최신")
        if ahead:
            return "warn", (f"{name}: PC 와 GitHub 양쪽에 새 커밋이 있어 자동으로 받지 않았어요 "
                            f"(PC {ahead}개 · GitHub {behind}개) — 채팅에서 합쳐 달라고 해 주세요")
        r = _git(repo, "merge", "--ff-only", "--quiet", "@{u}")
        if r.returncode:
            return "warn", (f"{name}: GitHub 의 새 커밋 {behind}개를 받지 못했어요 — 저장 안 한 변경과 겹침. "
                            "채팅에서 정리해 달라고 해 주세요")
        return "pulled", f"{name}: GitHub 에서 새 커밋 {behind}개 받음"
    except (OSError, subprocess.TimeoutExpired) as e:
        return "warn", f"{name}: git 실행 실패 — {e}"


def pull_all(log=print):
    """설정된 저장소를 모두 대조·내려받기. 결과 목록을 돌려주고 경고는 meta 에 남긴다."""
    results = [(p, *pull(p)) for p in paths()]
    for _, state, msg in results:
        if state != "ok":
            log(("⚠️ " if state == "warn" else "") + "저장소 " + msg)
    conn = db.connect()
    try:
        db.set_meta(conn, "repo_warnings", "\n".join(msg for _, state, msg in results if state == "warn"))
        for p, state, msg in results:
            if state == "pulled":
                db.log(conn, "repo_pulled", str(p), msg=msg)
        conn.commit()
    finally:
        conn.close()
    return results
