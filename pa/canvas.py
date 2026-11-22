"""Canvas(canvas.jejunu.ac.kr) REST API 클라이언트. .env 의 CANVAS_TOKEN 사용.

읽기는 get. 쓰기(post · upload_file)는 과제 제출(pa/submit.py)에서만 쓴다.
"""
import json
import mimetypes
import os
import uuid
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from pa.config import load_env

BASE = "https://canvas.jejunu.ac.kr/api/v1"


class CanvasAuthError(RuntimeError):
    pass


AUTH_HELP = ("Canvas 토큰이 만료됐거나 무효입니다 — Canvas → 계정 → 설정 → '새 액세스 토큰' 으로 발급해 "
             ".env 의 CANVAS_TOKEN 을 바꿔 주세요 (채팅에서 도와드려요)")


def _token():
    load_env()
    token = os.environ.get("CANVAS_TOKEN")
    if not token:
        raise SystemExit(".env 에 CANVAS_TOKEN 이 없습니다.")
    return token


def _send(req):
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise CanvasAuthError(AUTH_HELP) from None
        raise


def get(path, **params):
    """GET 요청. Link 헤더를 따라가며 모든 페이지를 합쳐 반환."""
    token = _token()
    query = urllib.parse.urlencode({"per_page": 100, **params}, doseq=True)  # 목록 값은 같은 이름으로 여러 번
    url, results = f"{BASE}{path}?{query}", []
    while url:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                links = resp.headers.get("Link", "")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise CanvasAuthError(AUTH_HELP) from None
            raise
        if not isinstance(data, list):
            return data
        results.extend(data)
        url = next((p.split(";")[0].strip("<> ") for p in links.split(",") if 'rel="next"' in p), None)
    return results


_courses = {"at": 0.0, "data": None}


def active_courses(max_age=600):
    """수강 과목 목록 — 한 동기화 안에서 여러 번 쓰이므로 10분 보관."""
    import time
    if _courses["data"] is None or time.time() - _courses["at"] > max_age:
        _courses["data"], _courses["at"] = get("/courses", enrollment_state="active"), time.time()
    return _courses["data"]


def post(path, data):
    """POST (폼). data 의 목록 값은 같은 이름으로 여러 번 (예: submission[file_ids][])."""
    body = urllib.parse.urlencode(data, doseq=True).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {_token()}"})
    return _send(req)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # 올린 곳이 돌려보내는 주소는 토큰을 붙여 따로 연다
        return None


def upload_file(path, file):
    """Canvas 파일 올리기 3단계: 자리 받기(path 에 POST) → 받은 곳에 파일 → (돌려보내면) 확인. 반환: 파일 정보(id 포함)."""
    file = Path(file)
    ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    slot = post(path, {"name": file.name, "size": file.stat().st_size, "content_type": ctype})
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
             for k, v in slot["upload_params"].items()]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file.name}"\r\n'
                 f"Content-Type: {ctype}\r\n\r\n".encode() + file.read_bytes() + f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(slot["upload_url"], data=b"".join(parts), method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:  # 올리는 곳은 Canvas 밖일 수 있어 토큰을 보내지 않는다
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=300) as resp:
            info = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303):
            raise
        info = {"location": e.headers["Location"]}
    if "id" not in info and info.get("location"):
        info = _send(urllib.request.Request(info["location"], headers={"Authorization": f"Bearer {_token()}"}))
    return info
