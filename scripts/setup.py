"""처음 설치 (리눅스·WSL: bin/setup, Windows: bin\\setup.cmd). 여러 번 실행해도 안전 — 이미 있는 것은 건드리지 않는다.

시스템 Python 으로 실행되므로 표준 라이브러리만 쓴다.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIN = os.name == "nt"
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if WIN else "bin/python")
PA = r"bin\pa.cmd" if WIN else "bin/pa"
HOME = Path.home()


def read(p):
    return p.read_text(encoding="utf-8") if p.exists() else ""


def main():
    if sys.version_info < (3, 10):
        sys.exit(f"Python 3.10 이상이 필요합니다 (지금 {sys.version.split()[0]})")
    os.chdir(ROOT)

    print("== 1. 파이썬 환경 (.venv)")
    if not VENV_PY.exists():
        subprocess.run([sys.executable, "-m", "venv", ".venv"], check=True)
    subprocess.run([str(VENV_PY), "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=True)
    r = subprocess.run([str(VENV_PY), "-m", "playwright", "install", "chromium"], capture_output=True)
    print("   PDF·브라우저용 Chromium 준비됨" if r.returncode == 0 else
          f"   ⚠️ Chromium 설치 실패 — 나중에: {VENV_PY} -m playwright install --with-deps chromium")

    print("== 2. 개인 파일")
    if not Path(".env").exists():
        shutil.copy(".env.example", ".env")
        print("   .env 만듦 (CANVAS_TOKEN 을 채우세요)")
    for f in sorted(Path("config").glob("*.example.*")):
        real = f.with_name(f.name.replace(".example", ""))
        if not real.exists():
            shutil.copy(f, real)
            print(f"   {real} 만듦 (견본 — 내 것으로 고치기)")
    Path("data").mkdir(exist_ok=True)

    print("== 3. 연결 폴더")
    for d in (HOME / "study_system" / "materials", HOME / "study_system" / "notes", HOME / "report"):
        if not d.is_dir():
            d.mkdir(parents=True)
            print(f"   {d} 만듦")
    report_rules = HOME / "report" / "CLAUDE.md"
    if not report_rules.exists():
        shutil.copy(ROOT / "templates" / "report-CLAUDE.md", report_rules)
        print(f"   {report_rules} 만듦 (보고서 글쓰기 규칙 견본)")
    for folder in (HOME / "report", HOME / "study_system"):  # Codex 는 CLAUDE.md 대신 AGENTS.md 를 읽는다 → 원본을 가리키는 안내만
        if (folder / "CLAUDE.md").exists() and not (folder / "AGENTS.md").exists():
            (folder / "AGENTS.md").write_text("이 폴더의 규칙 원본은 CLAUDE.md 다. 작업 전에 CLAUDE.md 를 읽고 그대로 따른다.\n",
                                              encoding="utf-8")
            print(f"   {folder / 'AGENTS.md'} 만듦 (Codex 용 안내 — 규칙은 CLAUDE.md)")

    print("== 4. 아직 남은 것")
    todo = []
    if not any(l.startswith("CANVAS_TOKEN=") and l.strip() != "CANVAS_TOKEN=" for l in read(Path(".env")).splitlines()):
        todo.append(".env 에 CANVAS_TOKEN")
    if not Path("credentials.json").exists():
        todo.append("credentials.json (docs/google-calendar-setup.md)")
    if any("예시과목" in read(Path("config") / n) for n in ("timetable.yaml", "courses.yaml", "profile.md")):
        todo.append("config/timetable.yaml·courses.yaml·profile.md 의 '예시과목'을 내 시간표·과목으로")
    if "<학번>" in read(report_rules):
        todo.append(f"{report_rules} 의 <학번>·<이름> (보고서 파일 이름·머리말에 씀)")
    for t in todo:
        print(f"   [ ] {t}")
    print(f"== {'위를 채운 뒤' if todo else '준비 끝'}: {PA} run --full")


if __name__ == "__main__":
    main()
