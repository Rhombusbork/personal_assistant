"""LearningX (학교 강의 플랫폼) 데이터 — 로그인 브라우저에서 얻은 토큰으로 읽기만 한다.

강의·자료 '페이지'는 열지 않는다 (열면 열람·출석 기록이 남을 수 있음).
대신 LearningX 의 데이터 API 로:
  - 강의: 실제 길이(분), 출석 마감, 수강 완료 여부
  - 배포 자료(PDF): 파일 이름과 위치 → study_system/materials/<과목>/ 로 내려받기

토큰은 data/browser-state.json (bin/pa browser login 으로 저장) 의 xn_api_token 쿠키.
만료되면 과목의 '주차별 강의콘텐츠' 탭(과목 단위 화면, 개별 강의 아님)을 한 번 열어 새로 받는다.
"""
import json
import math
import re
import urllib.error
import urllib.request

from pa import canvas, db, materials
from pa.browser import BASE, STATE
from pa.model import parse_dt

VIDEO_TYPES = {"everlec", "movie", "video", "mp4", "screenlecture"}


class NeedLogin(Exception):
    pass


def _token():
    if not STATE.exists():
        raise NeedLogin("브라우저 로그인 필요")
    for c in json.loads(STATE.read_text())["cookies"]:
        if c["name"] == "xn_api_token" and "jejunu" in c["domain"]:
            return c["value"]
    return None


def _get(url, token):
    """느린 응답(시간 초과)은 한 번 더 시도한다."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except (TimeoutError, urllib.error.URLError) as e:
            if attempt == 2 or isinstance(e, urllib.error.HTTPError):
                raise


def fetch_token_in(ctx, course_id):
    """로그인 창(사용자가 연 것) 안에서 과목의 LearningX 탭을 열어 토큰을 받는다. 개별 강의 페이지는 열지 않는다."""
    tab = next((t for t in canvas.get(f"/courses/{course_id}/tabs") if "강의콘텐츠" in t.get("label", "")), None)
    if not tab:
        return False
    page = ctx.new_page()
    page.goto(tab["full_url"], wait_until="networkidle", timeout=60000)
    page.close()
    return any(c["name"] == "xn_api_token" for c in ctx.cookies(BASE))


_mod_cache = {}  # course_id → (시각, 모듈)


def modules(course_id, token=None, max_age=300):
    """캐시: 같은 동기화에서 강의 정보·자료 다운로드가 함께 쓴다."""
    import time
    hit = _mod_cache.get(course_id)
    if hit and time.time() - hit[0] < max_age:
        return hit[1], token
    mods, token = _modules(course_id, token)
    _mod_cache[course_id] = (time.time(), mods)
    return mods, token


def _modules(course_id, token=None):
    """(모듈 목록, 쓴 토큰). 토큰이 없거나 만료되면 NeedLogin — 비서가 스스로 다시 로그인하지 않는다.

    (비서가 따로 로그인하면 학교가 평소 브라우저의 통합 로그인을 끊어, 평소 브라우저에서
     영상·자료가 안 열린 일이 있었다. 그래서 다시 로그인은 사용자가 버튼을 눌렀을 때만.)
    """
    url = f"{BASE}/learningx/api/v1/courses/{course_id}/modules?include_detail=true"
    token = token or _token()
    if not token:
        raise NeedLogin("LearningX 로그인 필요 (저장된 토큰 없음)")
    try:
        return _get(url, token), token
    except urllib.error.HTTPError as e:
        if e.code in (400, 401, 403):  # 토큰이 무효면 LearningX 는 400 'Invalid request' 를 준다
            raise NeedLogin(f"LearningX 로그인 만료 ({e.code})")
        raise


def items(mods):
    """모듈 → (module_item_id, 종류, 정보) 목록. 종류: 'lecture' | 'file'"""
    out = []
    for m in mods:
        for it in m.get("module_items", []):
            cd = it.get("content_data") or {}
            icd = cd.get("item_content_data") or {}
            ctype = icd.get("content_type")
            if it.get("content_type") != "attendance_item" or not (ctype or cd.get("item_content_type")):
                continue
            if cd.get("item_content_type") == "smart_attendance":
                out.append((it["module_item_id"], "lecture", {
                    "title": it["title"], "due": cd.get("due_at"), "late": cd.get("late_at"), "minutes": 5,
                    "done": bool(it.get("completed")) or it.get("attendance_status") == "attendance",
                }))
                continue
            if ctype in VIDEO_TYPES and cd.get("use_attendance"):
                out.append((it["module_item_id"], "lecture", {
                    "title": it["title"], "due": cd.get("due_at"), "late": cd.get("late_at"),
                    "minutes": math.ceil((icd.get("duration") or 0) / 60) or None,
                    "done": bool(it.get("completed")) or it.get("attendance_status") == "attendance",
                }))
            elif icd.get("file_name") or ctype == "pdf":
                out.append((it["module_item_id"], "file", {
                    "title": it["title"], "file_name": icd.get("file_name") or f"{it['title']}.pdf",
                    "content_id": icd.get("content_id"), "type": ctype, "view_url": icd.get("view_url"),
                }))
    return out


def lecture_info(course_id):
    """Canvas 항목 키(m<id>) → 강의면 실제 마감·길이·완료, 자료(파일)면 {'file': True}."""
    mods, _ = modules(course_id)
    return {f"m{mid}": (info if kind == "lecture" else {"file": True}) for mid, kind, info in items(mods)}


class Deleted(Exception):
    """교수자가 공용 뷰어에서 지운 자료 — 학생 화면에도 '삭제됨'으로 보이므로 받지 않는다."""


def _pdf_url(view_url, content_id):
    """파일 위치. 뷰어에서 삭제된 자료는 Deleted. (과목 강의 페이지가 아니라 공용 콘텐츠 정보만 읽는다)"""
    with urllib.request.urlopen(view_url, timeout=30) as r:
        if "deleted_content" in r.read().decode("utf-8", "replace"):
            raise Deleted(content_id)
    info = f"https://common.jejunu.ac.kr/viewer/ssplayer/uniplayer_support/content.php?content_id={content_id}"
    with urllib.request.urlopen(info, timeout=30) as r:
        m = re.search(r"<content_uri><!\[CDATA\[(.*?)\]\]>", r.read().decode("utf-8", "replace"))
    return m.group(1).rstrip("/") + "/original.pdf" if m else None


def _norm(name):
    """비교용 이름: 확장자·'(1)' 같은 복사본 표시·기호·공백을 무시."""
    stem = re.sub(r"\.\w+$", "", name.lower())
    stem = re.sub(r"\(\d+\)$", "", stem.strip())
    return re.sub(r"[^0-9a-z가-힣]", "", stem)


def download_files(conn, course, course_id):
    """그 과목의 배포 자료 중 아직 없는 PDF 를 materials 폴더로 받는다. 받은 파일 이름 목록 반환."""
    dirs = materials.course_dirs(course)
    if not dirs:
        return []
    mat = dirs[0]
    have = {_norm(f.name) for f in mat.rglob("*") if f.is_file()} if mat.exists() else set()
    mods, _ = modules(course_id)
    got, skipped = [], []
    for mid, kind, info in items(mods):
        if kind != "file" or info["type"] != "pdf" or not info["content_id"]:
            continue
        name = re.sub(r'[\\/:*?"<>|]', "_", info["file_name"])
        if _norm(name) in have:
            continue
        try:
            url = _pdf_url(info["view_url"], info["content_id"]) if info.get("view_url") else None
        except Deleted:
            skipped.append(name)
            continue
        if not url:
            continue
        with urllib.request.urlopen(url, timeout=120) as r:
            data = r.read()
        if not data.startswith(b"%PDF"):
            continue
        mat.mkdir(parents=True, exist_ok=True)
        (mat / name).write_bytes(data)
        db.log(conn, "material_downloaded", f"m{mid}", file=name, course=course)
        got.append(name)
    if skipped:
        deleted_files[course] = skipped
    return got


deleted_files = {}  # 과목 → 교수자가 뷰어에서 지운 자료 이름 (받지 않음)


def sync(conn, online_courses):
    """모든 온라인 과목의 새 배포 자료를 받는다. (받은 수, 오류 문장 또는 None)"""
    total, err = 0, None
    for c in online_courses:
        try:
            total += len(download_files(conn, c["name"], c["id"]))
        except NeedLogin as e:
            err = str(e)
            break
        except Exception as e:  # 한 과목이 실패해도 나머지는 계속
            err = f"{c['name']}: {e}"
    db.set_meta(conn, "learningx_error", err or "")
    if deleted_files:
        db.set_meta(conn, "deleted_materials", json.dumps(deleted_files, ensure_ascii=False))
    conn.commit()
    return total, err
