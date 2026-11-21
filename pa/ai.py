"""AI 호출 — API 키 대신 내 구독의 CLI 를 화면 없이 한 번 부른다.

  Claude Code: `claude -p`        (Read 만 허용)
  Codex:       `codex exec`       (읽기 전용 샌드박스 — 기본값)

어느 쪽을 쓸지는 .env 의 PA_AI=claude|codex. 비워 두면 설치된 것 (둘 다 있으면 claude).
사용 예:
  from pa.ai import ask
  ask("다음 강의 자료를 1장으로 요약해줘", files=["data/courses/.../17강.pdf"])
"""
import glob
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from pa.config import ROOT, load_env

NAMES = {"claude": "Claude", "codex": "Codex"}


def _vscode_bin(pattern, exe):
    """VSCode 확장에 들어 있는 CLI (가장 최신 버전). WSL 은 ~/.vscode-server, 그 밖은 ~/.vscode."""
    found = []
    for base in (".vscode-server", ".vscode"):
        found += glob.glob(str(Path.home() / base / "extensions" / pattern / exe))
    return max(found, key=lambda p: [int(n) for n in re.findall(r"\d+", Path(p).relative_to(Path.home()).parts[2])],
               default=None)


def _find(kind):
    env = os.environ.get(f"{kind.upper()}_BIN")
    if env:
        return env
    if kind == "claude":
        return shutil.which("claude") or _vscode_bin("anthropic.claude-code-*", "resources/native-binary/claude*")
    return shutil.which("codex")


def backend():
    """'claude' 또는 'codex'. 쓸 수 있는 것이 없으면 SystemExit."""
    load_env()
    want = os.environ.get("PA_AI", "").strip().lower()
    if want and want not in NAMES:
        raise SystemExit(f"PA_AI={want} 는 모릅니다 — claude 또는 codex")
    for kind in [want] if want else ["claude", "codex"]:
        if _find(kind):
            return kind
    raise SystemExit(f"{want or 'claude·codex'} CLI 를 찾지 못했습니다. 설치하거나 .env 에 CLAUDE_BIN / CODEX_BIN 으로 경로를 적으세요.")


_name = {"at": 0.0, "value": "AI"}


def name():
    """화면에 보여 줄 이름 (Claude / Codex). 아무것도 없으면 'AI'. 대시보드가 자주 부르므로 1분 보관."""
    if time.time() - _name["at"] > 60:
        try:
            _name["value"] = NAMES[backend()]
        except SystemExit:
            _name["value"] = "AI"
        _name["at"] = time.time()
    return _name["value"]


def claude_bin():
    found = _find("claude")
    if not found:
        raise SystemExit("claude CLI 를 찾지 못했습니다. CLAUDE_BIN 환경변수로 경로를 지정하세요.")
    return found


def _run(cmd, cwd, timeout, stdin=None):
    result = subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-500:] or f"{Path(cmd[0]).name} 호출 실패")
    return result.stdout.strip()


def ask(prompt, files=(), timeout=600, cwd=ROOT, add_dirs=(), images=()):
    """프롬프트를 보내고 텍스트 응답을 반환. 읽기만 허용한다 (파일은 엔진이 쓴다).

    cwd: 그 폴더의 규칙 파일(CLAUDE.md)이 적용된다. add_dirs: 추가로 읽을 수 있는 폴더.
    files: AI 가 읽을 수 있게 경로를 알려준다. images: 보여 줄 사진 (Claude 는 Read 로 보고, Codex 는 -i 로 붙인다).
    """
    if files:
        prompt += "\n\n참고 파일:\n" + "\n".join(f"- {Path(f).resolve()}" for f in files)
    if backend() == "codex":
        return _ask_codex(prompt, timeout, Path(cwd), add_dirs, images)
    if images:
        prompt += "\n\n사진 (Read 로 본다):\n" + "\n".join(f"- {Path(f).resolve()}" for f in images)
        add_dirs = [*add_dirs, *{str(Path(f).resolve().parent) for f in images}]
    cmd = [claude_bin(), "-p", prompt, "--output-format", "text", "--allowedTools", "Read"]
    for d in add_dirs:
        cmd += ["--add-dir", str(d)]
    return _run(cmd, cwd, timeout)


def _ask_codex(prompt, timeout, cwd, add_dirs, images=()):
    # Codex 는 CLAUDE.md 가 아니라 AGENTS.md 를 읽는다 → AGENTS.md 가 없는 폴더면 CLAUDE.md 를 규칙으로 읽으라고 알려 준다.
    # --add-dir 은 쓰기 권한을 주는 옵션이라 쓰지 않고, 읽을 폴더는 프롬프트로 알려 준다.
    head = []
    if (cwd / "CLAUDE.md").exists() and not (cwd / "AGENTS.md").exists():
        head.append(f"먼저 {cwd / 'CLAUDE.md'} 를 읽고 그 규칙을 모두 따른다 (아래에서 'CLAUDE.md' 는 이 파일이다).")
    if add_dirs:
        head.append("읽어도 되는 폴더: " + ", ".join(str(Path(d).resolve()) for d in add_dirs))
    head.append("파일을 고치거나 명령으로 무언가를 바꾸지 않는다. 결과는 답으로만 낸다.")
    cmd = [_find("codex"), "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral",
           "--cd", str(cwd)]
    for f in images:
        cmd += ["-i", str(Path(f).resolve())]
    cmd.append("-")  # 프롬프트는 표준 입력으로 (Windows 명령 줄 길이 제한을 피함). 최종 답만 stdout 으로 나온다
    return _run(cmd, cwd, timeout, stdin="\n".join(head) + "\n\n" + prompt)


if __name__ == "__main__":
    import sys
    print(f"[{name()}]", ask(" ".join(sys.argv[1:]) or "한 문장으로 인사해줘"))
