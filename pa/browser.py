"""로그인된 브라우저로 Canvas/LearningX 다루기 (R7 시험).

학교 강의 자료는 LearningX(Canvas 안의 외부 도구)에 있어 API 토큰으로는 막혀 있다.
그래서 사용자가 한 번 직접 로그인한 브라우저 프로필(data/browser-profile, git 제외)을
저장해 두고, 그 프로필로 페이지를 열어 자료를 찾는다.

  bin/pa browser login            창이 열리면 직접 로그인 → 로그인 확인되면 자동으로 닫힘
  bin/pa browser probe <과목> <제목 일부>   그 강의 항목을 열어 받을 수 있는 파일이 있는지 조사
"""
import json
import os
import re
import sys
import time

from pa import canvas
from pa.config import ROOT

PROFILE = ROOT / "data" / "browser-profile"
STATE = ROOT / "data" / "browser-state.json"  # 세션 쿠키까지 (창을 닫으면 브라우저가 버리는 학교 로그인 쿠키)
PROBE_DIR = ROOT / "data" / "probe"
BASE = "https://canvas.jejunu.ac.kr"
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(os.path.expanduser("~/quiz_system_project/.tools/pw")))


def _context(p, headless):
    PROFILE.mkdir(parents=True, exist_ok=True)
    ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=headless, accept_downloads=True,
                                               viewport={"width": 1280, "height": 900}, locale="ko-KR")
    if STATE.exists():
        ctx.add_cookies(json.loads(STATE.read_text())["cookies"])
    return ctx


def save_state(ctx):
    ctx.storage_state(path=str(STATE))
    STATE.chmod(0o600)


def logged_in(ctx):
    r = ctx.request.get(f"{BASE}/api/v1/users/self")
    return r.status == 200


def login(timeout_min=10):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _context(p, headless=False)
        if logged_in(ctx):
            _finish(ctx)
            print("이미 로그인되어 있습니다.")
            ctx.close()
            return True
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(f"{BASE}/login")
        print("열린 브라우저 창에서 제주대 Canvas 에 로그인해 주세요. (최대 10분 기다림)", flush=True)
        end = time.time() + timeout_min * 60
        while time.time() < end:
            time.sleep(3)
            try:
                if logged_in(ctx):
                    _finish(ctx)
                    print("✅ 로그인 확인 — 저장됨", flush=True)
                    ctx.close()
                    return True
            except Exception:
                pass
        print("시간 초과 — 로그인이 확인되지 않았습니다.")
        ctx.close()
        return False


def _finish(ctx):
    """로그인 직후 (사용자가 연 창 안에서) LearningX 토큰까지 받아 저장한다."""
    from pa import collect_canvas, learningx
    for c in collect_canvas.online_courses()[:1]:
        try:
            learningx.fetch_token_in(ctx, c["id"])
        except Exception as e:
            print("LearningX 토큰 받기 실패:", e)
    save_state(ctx)


def find_item(course_word, title_word):
    for c in canvas.active_courses():
        if course_word not in c["name"]:
            continue
        for m in canvas.get(f"/courses/{c['id']}/modules", **{"include[]": "items"}):
            for i in m.get("items", []):
                if title_word in i["title"]:
                    return c, m, i
    return None


def probe(course_word, title_word):
    """항목 페이지를 열고, 안쪽 프레임·링크·네트워크에서 파일(PDF 등)을 찾는다."""
    from playwright.sync_api import sync_playwright
    found = find_item(course_word, title_word)
    if not found:
        print("항목을 찾지 못했습니다.")
        return
    c, m, item = found
    print(f"항목: {c['name']} / {m['name']} / {item['title']}\n주소: {item['html_url']}")
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    with sync_playwright() as p:
        ctx = _context(p, headless=True)
        if not logged_in(ctx):
            print("로그인이 필요합니다: bin/pa browser login")
            ctx.close()
            return
        page = ctx.new_page()

        def on_response(r):
            ct = r.headers.get("content-type", "")
            if any(x in ct for x in ("pdf", "octet-stream", "presentation", "msword", "officedocument")):
                files.append((ct, r.url))
        page.on("response", on_response)
        page.goto(item["html_url"], wait_until="networkidle", timeout=60000)
        time.sleep(5)
        page.screenshot(path=str(PROBE_DIR / "item.png"), full_page=True)
        print("\n[프레임]")
        for f in page.frames:
            print("  ", f.url[:150])
        print("\n[다운로드처럼 보이는 링크·버튼]")
        for f in page.frames:
            try:
                for a in f.query_selector_all("a, button"):
                    txt = (a.inner_text() or "").strip().replace("\n", " ")[:40]
                    href = a.get_attribute("href") or ""
                    if re.search(r"다운|download|pdf|첨부|파일", txt + href, re.I):
                        print(f"   [{txt}] {href[:120]}")
            except Exception as e:
                print("   (프레임 읽기 실패)", e)
        print("\n[네트워크로 받은 파일]")
        for ct, url in files:
            print(f"   {ct}  {url[:150]}")
        ctx.close()
    print(f"\n화면: {PROBE_DIR / 'item.png'}")


def main(argv):
    if argv[:1] == ["login"]:
        login()
    elif argv[:1] == ["probe"] and len(argv) >= 3:
        probe(argv[1], " ".join(argv[2:]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
