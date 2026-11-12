"""R2 자료: 강의·과제에 맞는 자료 찾기·열기, 다운로드 폴더의 새 자료를 과목 폴더로 정리.

- 과목 → 폴더: config/courses.yaml
- 맞추기: 제목의 '17강', 'Ch24', '11주차' 같은 강한 단서 + 제목 단어 겹침
- 열기: VSCode 안이면 `code <파일>` (같은 창의 편집기 탭), 아니면 Windows 기본 프로그램
"""
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import yaml

from pa import db
from pa.config import ROOT

SKIP = re.compile(r"^스크린샷|^Screenshot|\.(png|jpg|jpeg|gif)$", re.I)
DOC_EXT = {".pdf", ".ppt", ".pptx", ".doc", ".docx", ".hwp", ".hwpx", ".xlsx", ".md", ".txt", ".zip"}


def _cfg():
    c = yaml.safe_load((ROOT / "config" / "courses.yaml").read_text())
    c["root"] = Path(os.path.expanduser(c["root"]))
    return c


def course_dirs(course_name):
    """과목명 → (materials 폴더, notes 폴더) 또는 None."""
    cfg = _cfg()
    for c in cfg["courses"]:
        if any(m in (course_name or "") for m in c["match"]):
            return cfg["root"] / "materials" / c["materials"], cfg["root"] / "notes" / c["notes"]
    return None


def allowed_roots():
    cfg = _cfg()
    return [cfg["root"].resolve(), (Path.home() / "report").resolve()]


def clues(title):
    """제목에서 강한 단서: ('강', '17'), ('ch', '24'), ('주', '11')."""
    out = set()
    for n in re.findall(r"(\d+)\s*강", title):
        out.add(("강", str(int(n))))
    for n in re.findall(r"ch\.?\s*(\d+)", title, re.I):
        out.add(("ch", str(int(n))))
    for n in re.findall(r"(\d+)\s*주", title):
        out.add(("주", str(int(n))))
    return out


def words(text):
    return {w for w in re.split(r"[\s_\-\[\]\(\)·,.&]+", text.lower()) if len(w) >= 2 and not w.isdigit()}


def find(course_name, title):
    """후보 파일 [(점수, 경로)] — 점수 높은 순. 강한 단서가 맞으면 10점 이상."""
    dirs = course_dirs(course_name)
    if not dirs or not dirs[0].exists():
        return None, []
    return dirs[0], scan(dirs[0], title)


def scan(folder, title):
    """folder 안에서 title 에 맞는 파일 [(점수, 경로)]."""
    if not folder.exists():
        return []
    mat = folder
    want_clues, want_words = clues(title), words(title)
    scored = []
    for f in mat.rglob("*"):
        if not f.is_file() or SKIP.search(f.name) or f.suffix.lower() not in DOC_EXT:
            continue
        rel = str(f.relative_to(mat))
        fc = clues(rel)
        score = 10 * len(want_clues & fc)
        if want_clues and fc and not (want_clues & fc):
            continue  # 다른 강·챕터의 자료
        score += len(want_words & words(rel))
        if score:
            scored.append((score, f))
    scored.sort(key=lambda x: (-x[0], str(x[1])))
    return scored


def _vscode_open(path):
    """VSCode 편집기 탭으로 연다. 엔진이 켜진 뒤 VSCode 창을 다시 열었으면 연결 통로(소켓)가 바뀌므로,
    환경 변수의 것 → 가장 최근 것 순서로 시도한다. 실패하면 False."""
    import glob
    code = shutil.which("code") or next(iter(sorted(glob.glob(
        str(Path.home() / ".vscode-server/bin/*/bin/remote-cli/code")), key=os.path.getmtime, reverse=True)), None)
    if not code:
        return False
    socks = sorted(glob.glob(f"/run/user/{os.getuid()}/vscode-ipc-*.sock"), key=os.path.getmtime, reverse=True)
    for sock in dict.fromkeys([os.environ.get("VSCODE_IPC_HOOK_CLI")] + socks):
        if not sock or not os.path.exists(sock):
            continue
        try:
            r = subprocess.run([code, "--reuse-window", str(path)], env={**os.environ, "VSCODE_IPC_HOOK_CLI": sock},
                               capture_output=True, timeout=8)
        except (subprocess.TimeoutExpired, OSError):
            continue
        if r.returncode == 0:
            return True
    return False


def open_file(path):
    path = Path(path).resolve()
    if not any(str(path).startswith(str(r)) for r in allowed_roots()):
        raise ValueError("열 수 없는 위치")
    if not path.exists():
        raise ValueError("파일 없음")
    if _vscode_open(path):
        return "vscode"
    win = subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True).stdout.strip()
    subprocess.Popen(["explorer.exe", win])
    return "windows"


# ---- 다운로드 폴더 정리 --------------------------------------------------------

def downloads_dir():
    users = Path("/mnt/c/Users")
    for u in sorted(users.iterdir()) if users.exists() else []:
        d = u / "Downloads"
        if d.is_dir() and u.name not in ("Public", "Default", "Default User", "All Users"):
            return d
    return None


def guess_course(filename):
    cfg = _cfg()
    for c in cfg["courses"]:
        if any(m in filename for m in c["match"]):
            return c["match"][0]
    return None


def scan_downloads(conn):
    """다운로드 폴더 맨 위를 한 번 읽어서: ① 자료 연결 창용 '최근 받은 파일' 목록을 기억하고
    ② 엔진 시작 이후(처음엔 지금부터) 새로 받은 자료를 '새 다운로드' 목록에 올린다."""
    d = downloads_dir()
    if not d:
        return
    entries = []
    with os.scandir(d) as it:  # Windows 쪽 폴더라 한 번만 읽는다
        for e in it:
            try:
                if e.is_file():
                    entries.append((Path(e.path), e.stat()))
            except OSError:
                continue
    from pa import links
    links.update_recent_downloads(entries)
    since = float(db.get_meta(conn, "downloads_since") or 0)
    if not since:
        db.set_meta(conn, "downloads_since", str(time.time()))
        conn.commit()
        return
    pending = json.loads(db.get_meta(conn, "downloads_pending") or "[]")
    known = {p["path"] for p in pending}
    changed = False
    for f, st in entries:
        if (f.suffix.lower() in DOC_EXT and st.st_mtime > since
                and str(f) not in known and not f.name.endswith((".crdownload", ".part", ".tmp"))):
            pending.append({"path": str(f), "name": f.name, "course": guess_course(f.name)})
            changed = True
    if changed:
        db.set_meta(conn, "downloads_pending", json.dumps(pending, ensure_ascii=False))
        conn.commit()


def pending_downloads(conn):
    return [p for p in json.loads(db.get_meta(conn, "downloads_pending") or "[]") if Path(p["path"]).exists()]


def _drop_pending(conn, path):
    pending = [p for p in json.loads(db.get_meta(conn, "downloads_pending") or "[]") if p["path"] != path]
    db.set_meta(conn, "downloads_pending", json.dumps(pending, ensure_ascii=False))
    conn.commit()


def move_download(conn, path, course):
    src = Path(path)
    dirs = course_dirs(course)
    if not dirs or not src.exists():
        raise ValueError("옮길 수 없음")
    dst = dirs[0] / src.name
    if dst.exists():
        dst = dirs[0] / f"{src.stem}_{int(time.time())}{src.suffix}"
    dirs[0].mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    db.log(conn, "material_moved", None, src=src.name, dst=str(dst))
    _drop_pending(conn, path)
    return dst


def dismiss_download(conn, path):
    _drop_pending(conn, path)
