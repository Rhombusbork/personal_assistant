"""Canvas(canvas.jejunu.ac.kr) REST API 클라이언트. .env 의 CANVAS_TOKEN 사용."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from pa.config import load_env

BASE = "https://canvas.jejunu.ac.kr/api/v1"


class CanvasAuthError(RuntimeError):
    pass


AUTH_HELP = ("Canvas 토큰이 만료됐거나 무효입니다 — Canvas → 계정 → 설정 → '새 액세스 토큰' 으로 발급해 "
             ".env 의 CANVAS_TOKEN 을 바꿔 주세요 (채팅에서 도와드려요)")


def get(path, **params):
    """GET 요청. Link 헤더를 따라가며 모든 페이지를 합쳐 반환."""
    load_env()
    token = os.environ.get("CANVAS_TOKEN")
    if not token:
        raise SystemExit(".env 에 CANVAS_TOKEN 이 없습니다.")
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
