"""자료 연결 (📄): 할 일마다 '연결된 자료' — 추천 · 실시간 찾기 · 경로 Tab · 📁 둘러보기의 엔진 쪽.

- 범위·규칙: config/materials.yaml (읽기만. 바꾸는 건 대화로)
- 저장: data/pa.db 의 links 표 (key, path, origin)
    origin: user(직접 고름) | pair(강의 플랫폼에서 같은 주차의 강의 ↔ 자료 짝) | removed(짝을 사용자가 뺌 — 다시 넣지 않음)
- 가볍게: 파일 '이름·날짜·크기'만 모아 1분 보관. 찾기는 화면(브라우저)이 그 목록으로 한다.
  다운로드 폴더는 엔진의 30초 감시가 기억한 목록(RECENT_DOWNLOADS)만 쓴다 — 이 모듈이 Windows 폴더를 직접 열지 않는다.
- 파일 내용은 읽지 않는다 (내용정리·보고서를 누를 때만 그 파일).
"""
import json
import os
import re
import time
from pathlib import Path

import yaml

from pa import db, materials
from pa.config import ROOT
from pa.model import now

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
  key TEXT NOT NULL,
  path TEXT NOT NULL,
  origin TEXT NOT NULL DEFAULT 'user',   -- user | pair | removed
  created_at TEXT NOT NULL,
  PRIMARY KEY (key, path)
);
"""
RECENT_DOWNLOADS = {"at": 0.0, "files": []}  # 엔진의 다운로드 감시가 채운다 (materials.scan_downloads)
_index = {"at": 0.0, "files": None}


def cfg():
    c = yaml.safe_load((ROOT / "config" / "materials.yaml").read_text())
    for r in c["roots"]:
        r["path"] = Path(os.path.expanduser(r["path"])).resolve()
        r["ext"] = {"." + e.lower().lstrip(".") for e in r["ext"]}
    c["downloads"]["ext"] = {"." + e.lower().lstrip(".") for e in c["downloads"]["ext"]}
    return c


def _skip(name, c):
    return name.startswith(".") or any(s in name for s in c.get("skip", []))


def root_of(path, c=None):
    """경로가 어느 찾기 범위 안인지 → (이름, 상대 경로) 또는 None."""
    c = c or cfg()
    p = Path(path).resolve()
    for r in c["roots"]:
        try:
            return r["name"], str(p.relative_to(r["path"]))
        except ValueError:
            continue
    return None


# ---- 파일 목록 -----------------------------------------------------------------

def index(max_age=60):
    """찾기 범위의 모든 파일 [{p, r, rel, m, s}] — 1분 보관 (study_system·report 는 Ubuntu 쪽이라 빠름)."""
    if _index["files"] is not None and time.time() - _index["at"] < max_age:
        return _index["files"]
    c, out = cfg(), []
    for r in c["roots"]:
        if not r["path"].exists():
            continue
        for dirpath, dirnames, filenames in os.walk(r["path"]):
            dirnames[:] = [d for d in dirnames if not _skip(d, c)]
            for f in filenames:
                if _skip(f, c) or Path(f).suffix.lower() not in r["ext"]:
                    continue
                full = Path(dirpath) / f
                try:
                    st = full.stat()
                except OSError:
                    continue
                out.append({"p": str(full), "r": r["name"], "rel": str(full.relative_to(r["path"])),
                            "m": int(st.st_mtime), "s": st.st_size})
    _index.update(at=time.time(), files=out)
    return out


def recent_downloads():
    """엔진이 30초마다 본 다운로드 폴더 맨 위의 최근 문서 (Windows 쪽을 다시 열지 않음)."""
    return RECENT_DOWNLOADS["files"]


def update_recent_downloads(entries):
    """materials.scan_downloads 가 한 번 읽은 목록으로 갱신 [(Path, stat)]."""
    c = cfg()["downloads"]
    cutoff = time.time() - c["recent_days"] * 86400
    files = [{"p": str(f), "r": "다운로드", "rel": f.name, "m": int(st.st_mtime), "s": st.st_size}
             for f, st in entries if f.suffix.lower() in c["ext"] and st.st_mtime >= cutoff
             and not f.name.endswith((".crdownload", ".part", ".tmp"))]
    RECENT_DOWNLOADS.update(at=time.time(), files=sorted(files, key=lambda x: -x["m"]))


def ls(root_name, rel=""):
    """📁 둘러보기: 폴더 하나의 바로 아래 (폴더·파일). 범위 밖은 거부."""
    c = cfg()
    if root_name == "다운로드":
        return {"root": root_name, "path": "", "dirs": [], "files": recent_downloads()}
    r = next((x for x in c["roots"] if x["name"] == root_name), None)
    if not r:
        raise ValueError("찾기 범위가 아님")
    folder = (r["path"] / rel).resolve()
    if folder != r["path"] and r["path"] not in folder.parents:
        raise ValueError("찾기 범위 밖")
    dirs, files = [], []
    for e in sorted(folder.iterdir()) if folder.is_dir() else []:
        if _skip(e.name, c):
            continue
        if e.is_dir():  # 개수는 1분 보관하는 목록에서 센다 (폴더를 다시 훑지 않음)
            prefix = str(e) + os.sep
            dirs.append({"name": e.name, "count": sum(1 for x in index() if x["p"].startswith(prefix))})
        elif e.suffix.lower() in r["ext"]:
            st = e.stat()
            files.append({"name": e.name, "p": str(e), "r": root_name, "rel": str(e.relative_to(r["path"])),
                          "m": int(st.st_mtime), "s": st.st_size})
    return {"root": root_name, "path": "" if folder == r["path"] else str(folder.relative_to(r["path"])),
            "dirs": dirs, "files": files}


# ---- 연결 ----------------------------------------------------------------------

def _ensure(conn):
    conn.executescript(SCHEMA)


def get(conn, key):
    """연결된 자료 (직접 고른 것 먼저). 파일이 사라졌으면 exists=False."""
    _ensure(conn)
    c, out = cfg(), []
    for r in conn.execute("SELECT path, origin FROM links WHERE key = ? AND origin != 'removed' "
                          "ORDER BY origin = 'pair', created_at", (key,)):
        loc = root_of(r["path"], c)
        out.append({"p": r["path"], "name": Path(r["path"]).name, "r": loc[0] if loc else "", "rel": loc[1] if loc else r["path"],
                    "origin": r["origin"], "exists": Path(r["path"]).exists()})
    return out


def paths(conn, key):
    """보고서·내용정리용: 존재하는 연결 파일 경로."""
    return [Path(x["p"]) for x in get(conn, key) if x["exists"]]


def add(conn, key, path, origin="user"):
    _ensure(conn)
    p = Path(path).resolve()
    if not p.is_file():
        raise ValueError("파일이 없습니다")
    if not root_of(p):
        raise ValueError("찾기 범위 밖의 파일입니다 — 범위를 넓히려면 채팅에서 요청하세요")
    limit = cfg()["max_links"]
    have = conn.execute("SELECT COUNT(*) FROM links WHERE key = ? AND origin != 'removed' AND path != ?",
                        (key, str(p))).fetchone()[0]
    if have >= limit:
        raise ValueError(f"자료는 할 일 하나에 최대 {limit}개입니다 — 더 넣으려면 채팅에서 늘려 달라고 하세요")
    conn.execute("INSERT INTO links (key, path, origin, created_at) VALUES (?, ?, ?, ?) "
                 "ON CONFLICT(key, path) DO UPDATE SET origin = excluded.origin",
                 (key, str(p), origin, now().isoformat()))
    db.log(conn, "link_added", key, path=p.name, origin=origin)
    conn.commit()


def remove(conn, key, path):
    """연결 빼기. 짝(pair)은 '뺐음'으로 남겨 다음 동기화에서 다시 넣지 않는다."""
    _ensure(conn)
    row = conn.execute("SELECT origin FROM links WHERE key = ? AND path = ?", (key, path)).fetchone()
    if not row:
        return
    if row["origin"] == "pair":
        conn.execute("UPDATE links SET origin = 'removed' WHERE key = ? AND path = ?", (key, path))
    else:
        conn.execute("DELETE FROM links WHERE key = ? AND path = ?", (key, path))
    db.log(conn, "link_removed", key, path=Path(path).name)
    conn.commit()


def add_download(conn, key, path, course=None):
    """다운로드 폴더의 파일: 그 할 일의 과목 자료 폴더로 옮긴 뒤 연결 (config downloads.on_link: move)."""
    src = Path(path)
    if src.parent != materials.downloads_dir() or not src.is_file():
        raise ValueError("다운로드 폴더의 파일이 아닙니다")
    row = conn.execute("SELECT course FROM tasks WHERE key = ?", (key,)).fetchone()
    dirs = materials.course_dirs(course or (row["course"] if row else ""))
    if not dirs:
        return {"needCourse": True, "courses": [c["match"][0] for c in materials._cfg()["courses"]]}
    dst = materials.move_download(conn, str(src), course or row["course"])
    _index["files"] = None  # 목록 새로
    RECENT_DOWNLOADS["files"] = [f for f in RECENT_DOWNLOADS["files"] if f["p"] != str(src)]  # 다음 감시를 기다리지 않게
    add(conn, key, dst)
    return {"ok": True, "message": f"과목 폴더로 옮겨 연결: {dst.name}"}


# ---- 짝 (강의 ↔ 자료) ------------------------------------------------------------

MATERIAL_TITLE = re.compile(r"배포용|handout|\[강의자료\]", re.I)
_PREFIX = re.compile(r"^\s*\[[^\]]*\]\s*")
_LECTURE_WORDS = re.compile(r"lecture|leture|강의영상|\d\)", re.I)


def norm_title(s):
    """이름 비교용: 글자·숫자만 (공백·기호·대소문자 무시)."""
    return re.sub(r"[^0-9a-z가-힣]", "", s.lower())


_norm = norm_title


def _core(title):
    """짝 비교용 핵심 제목: [머리말]·배포용·handout·Lecture 1) 같은 말 빼기."""
    t = _PREFIX.sub("", title)
    t = re.sub(r"_?(배포용|handout)", "", t, flags=re.I)
    t = _LECTURE_WORDS.sub("", t)
    return _norm(t)


def find_pairs(module_items, local_files, candidates=None):
    """한 주차(모듈)의 항목들 → [(강의 키, 자료 경로)].
    자료 = 과목 폴더에 같은 이름의 파일이 있는 항목. 강의 하나에 자료 후보가 하나로 정해질 때만 짝.
    정하지 못하면 candidates[강의 키] = [후보 경로…] 에 남긴다 (📄 추천으로만 — 연결은 사용자가)."""
    by_norm = {}
    for f in local_files:
        by_norm.setdefault(_norm(Path(f).stem), f)
    mats, lectures = [], []
    for it in module_items:
        if it.get("type") != "ExternalTool":
            continue
        f = by_norm.get(_norm(it["title"]))
        if f:
            mats.append((it, f))
        elif not MATERIAL_TITLE.search(it["title"]) and "[출결]" not in it["title"]:  # 출석 확인은 공부할 강의가 아님
            lectures.append(it)
    pairs = []
    for lec in lectures:
        cands = mats
        if len(cands) > 1:
            lc, lclues = _core(lec["title"]), materials.clues(lec["title"])
            cands = [(m, f) for m, f in mats
                     if (_core(m["title"]) and (_core(m["title"]) in lc or lc in _core(m["title"])))
                     or (lclues and lclues & materials.clues(m["title"]))]
        if len(cands) == 1:
            pairs.append((f"m{lec['id']}", cands[0][1]))
        elif mats and candidates is not None:
            candidates[f"m{lec['id']}"] = [f for _, f in (cands or mats)]
    return pairs


def save_pairs(conn, pairs):
    """짝 저장 — 이미 있는 연결(직접 고름·뺐음)은 건드리지 않는다."""
    _ensure(conn)
    n = 0
    for key, path in pairs:
        n += conn.execute("INSERT OR IGNORE INTO links (key, path, origin, created_at) VALUES (?, ?, 'pair', ?)",
                          (key, str(path), now().isoformat())).rowcount
    conn.commit()
    return n


# ---- 추천 ----------------------------------------------------------------------

def suggest(conn, key, limit=8):
    """아무것도 안 쳤을 때 보여 줄 추천: 번호가 맞는 자료·노트 → 그 과목 폴더의 최근 파일. (연결된 건 뺌)"""
    row = conn.execute("SELECT course, title FROM tasks WHERE key = ?", (key,)).fetchone()
    if not row:
        return []
    have = {x["p"] for x in get(conn, key)}
    removed = {r["path"] for r in conn.execute("SELECT path FROM links WHERE key = ? AND origin = 'removed'", (key,))}
    out, seen = [], have | removed
    for f in json.loads(db.get_meta(conn, "pair_candidates") or "{}").get(key, []):  # 같은 주차 자료가 여럿이라 짝을 못 정한 것
        if f not in seen and Path(f).exists():
            seen.add(f)
            out.append({"p": f, "name": Path(f).name, "why": "같은 주차 자료 (강의 플랫폼)"})
    dirs = materials.course_dirs(row["course"])
    if dirs:
        for label, folder in (("번호가 맞는 자료", dirs[0]), ("번호가 맞는 내 노트", dirs[1])):
            for sc, f in materials.scan(folder, row["title"]):
                if sc >= 10 and str(f) not in seen and root_of(f):
                    seen.add(str(f))
                    out.append({"p": str(f), "name": f.name, "why": label})
        recent = sorted((x for x in index() if x["p"].startswith(str(dirs[0])) and x["p"] not in seen),
                        key=lambda x: -x["m"])[:3]
        out += [{"p": x["p"], "name": Path(x["p"]).name, "why": "이 과목 최근 파일"} for x in recent]
    return out[:limit]


def summary_map(conn, keys):
    """대시보드·휴대폰 표시용: {키: [파일 이름…]} (연결이 있는 것만)."""
    _ensure(conn)
    out = {}
    for r in conn.execute("SELECT key, path FROM links WHERE origin != 'removed'"):
        if r["key"] in keys:
            out.setdefault(r["key"], []).append(Path(r["path"]).name)
    return out
