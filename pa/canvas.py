"""Canvas(canvas.jejunu.ac.kr) REST API 클라이언트. .env 의 CANVAS_TOKEN 사용."""
import json
import os
import urllib.request

from pa.config import load_env

BASE = "https://canvas.jejunu.ac.kr/api/v1"


def get(path, **params):
    """GET 요청. Link 헤더를 따라가며 모든 페이지를 합쳐 반환."""
    load_env()
    token = os.environ.get("CANVAS_TOKEN")
    if not token:
        raise SystemExit(".env 에 CANVAS_TOKEN 이 없습니다.")
    query = "&".join(f"{k}={v}" for k, v in {"per_page": 100, **params}.items())
    url, results = f"{BASE}{path}?{query}", []
    while url:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            links = resp.headers.get("Link", "")
        if not isinstance(data, list):
            return data
        results.extend(data)
        url = next((p.split(";")[0].strip("<> ") for p in links.split(",") if 'rel="next"' in p), None)
    return results


def active_courses():
    return get("/courses", enrollment_state="active")
