"""Claude 호출 — API 키 대신 Claude Code CLI(헤드리스 `claude -p`)로 내 구독을 사용한다.

사용 예:
  from pa.ai import ask
  ask("다음 강의 자료를 1장으로 요약해줘", files=["data/courses/.../17강.pdf"])
"""
import glob
import os
import shutil
import subprocess
from pathlib import Path

from pa.config import ROOT


def claude_bin():
    found = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if found:
        return found
    # VSCode 확장에 포함된 CLI (가장 최신 버전)
    cands = sorted(glob.glob(str(Path.home() / ".vscode-server/extensions/anthropic.claude-code-*/resources/native-binary/claude")))
    if not cands:
        raise SystemExit("claude CLI 를 찾지 못했습니다. CLAUDE_BIN 환경변수로 경로를 지정하세요.")
    return cands[-1]


def ask(prompt, files=(), timeout=600):
    """프롬프트를 보내고 텍스트 응답을 반환. files 는 Claude 가 Read 도구로 읽을 수 있게 경로를 알려준다."""
    if files:
        prompt += "\n\n참고 파일:\n" + "\n".join(f"- {Path(f).resolve()}" for f in files)
    result = subprocess.run(
        [claude_bin(), "-p", prompt, "--output-format", "text", "--allowedTools", "Read"],
        cwd=ROOT, capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "claude 호출 실패")
    return result.stdout.strip()


if __name__ == "__main__":
    import sys
    print(ask(" ".join(sys.argv[1:]) or "한 문장으로 인사해줘"))
