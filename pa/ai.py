"""Claude 호출 — API 키 대신 Claude Code CLI(헤드리스 `claude -p`)로 내 구독을 사용한다.

사용 예:
  from pa.ai import ask
  ask("다음 강의 자료를 1장으로 요약해줘", files=["data/courses/.../17강.pdf"])
"""
import glob
import os
import re
import shutil
import subprocess
from pathlib import Path

from pa.config import ROOT


def claude_bin():
    found = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if found:
        return found
    # VSCode 확장에 포함된 CLI (가장 최신 버전)
    cands = sorted(glob.glob(str(Path.home() / ".vscode-server/extensions/anthropic.claude-code-*/resources/native-binary/claude")),
                   key=lambda p: [int(n) for n in re.findall(r"\d+", p.split("claude-code-")[1].split("/")[0])])
    if not cands:
        raise SystemExit("claude CLI 를 찾지 못했습니다. CLAUDE_BIN 환경변수로 경로를 지정하세요.")
    return cands[-1]


def ask(prompt, files=(), timeout=600, cwd=ROOT, add_dirs=()):
    """프롬프트를 보내고 텍스트 응답을 반환. Read(읽기)만 허용한다.

    cwd: 그 폴더의 CLAUDE.md 가 규칙으로 적용된다. add_dirs: 추가로 읽을 수 있는 폴더.
    files: Claude 가 Read 로 읽을 수 있게 경로를 알려준다.
    """
    if files:
        prompt += "\n\n참고 파일:\n" + "\n".join(f"- {Path(f).resolve()}" for f in files)
    cmd = [claude_bin(), "-p", prompt, "--output-format", "text", "--allowedTools", "Read"]
    for d in add_dirs:
        cmd += ["--add-dir", str(d)]
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "claude 호출 실패")
    return result.stdout.strip()


if __name__ == "__main__":
    import sys
    print(ask(" ".join(sys.argv[1:]) or "한 문장으로 인사해줘"))
