"""학교 포털(하영드리미) 내 수업시간표 → Google '수업 시간표' 캘린더 (대면 수업만, 날짜별)

사용자가 정한 것 (2026-11-16): 매주 시작할 때(그 주의 첫 전체 확인) 포털에서 내 시간표를 읽어 온다.
포털은 온라인 과목에도 강의실을 적어 두어 스스로 구분하지 못하므로, config/timetable.yaml 의
portal.offline 에 적은 과목만 대면으로 넣는다. 처음 보는 과목은 '확인 필요'로 묻는다.

- 읽는 것: portal.jejunu.ac.kr/classwork/management/timetable.htm?act=table&_out=json (읽기만)
- 로그인: .env 의 PA_SCHOOL_ID·PA_SCHOOL_PW 로 안 보이는 브라우저 (data/portal-state.json 에 저장, 주 1회 정도)
- 휴강(cclctYn=Y)은 빼고 보강은 그 날짜에. 이어지는 교시는 한 일정으로 합친다
- 캘린더에는 오늘이 속한 주 월요일부터 계획 기간(horizon_days)까지를 날짜별 일정으로 맞춘다
  (예전 '매주 반복' 일정(pa_source=timetable)은 포털 일정이 처음 들어갈 때 지운다)
"""
import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta

from pa import db
from pa.config import ROOT, load_env, load_timetable
from pa.model import KST, now

BASE = "https://portal.jejunu.ac.kr"
LOGIN = BASE + "/login.htm?returnURL=%2Findex.htm"
API = BASE + "/classwork/management/timetable.htm"
STATE = ROOT / "data" / "portal-state.json"
CALENDAR = "수업 시간표"
TERMS = ("10", "11", "20", "21")  # 1학기·하기계절·2학기·동기계절
RETRY = 6 * 3600                  # 실패하면 6시간 뒤에 다시 (계정 잠김 방지)


def cfg():
    c = load_timetable().get("portal") or {}
    return {"enabled": bool(c.get("enabled")), "offline": list(c.get("offline") or []),
            "online": list(c.get("online") or []) + list(load_timetable().get("online_classes") or [])}


def week_range(today, horizon_days):
    start = today - timedelta(days=today.weekday())
    end = today + timedelta(days=horizon_days)
    return start, end + timedelta(days=6 - end.weekday())


# ---- 읽기 -----------------------------------------------------------------------

def _hm(s):
    return datetime.strptime(s, "%H:%M").time()


def blocks(rows, offline):
    """포털 행들 → 대면 수업 일정 [(날짜, 시작, 끝, 과목, 강의실)], 처음 보는 과목 집합은 따로 돌려준다.
    이어지는 교시(사이 15분 이하)는 합친다."""
    rows = [r for r in rows if r and r.get("cclctYn") != "Y"]
    names = {r["sbjctNm"] for r in rows}
    keep = sorted((r for r in rows if r["sbjctNm"] in offline),
                  key=lambda r: (r["lsnYmd"], r["sbjctNm"], r["bgngHr"]))
    out = []
    for r in keep:
        d = datetime.strptime(r["lsnYmd"], "%Y%m%d").date()
        s, e = _hm(r["bgngHr"]), _hm(r["endHr"])
        if out and out[-1][0] == d and out[-1][3] == r["sbjctNm"] and \
                datetime.combine(d, s) - datetime.combine(d, out[-1][2]) <= timedelta(minutes=15):
            out[-1] = (d, out[-1][1], max(e, out[-1][2]), r["sbjctNm"], out[-1][4])
        else:
            out.append((d, s, e, r["sbjctNm"], r.get("lctrmNm") or ""))
    return sorted(out, key=lambda b: (b[0], b[1])), names


def _login(ctx):
    load_env()
    uid, pw = os.environ.get("PA_SCHOOL_ID"), os.environ.get("PA_SCHOOL_PW")
    if not uid or not pw:
        raise RuntimeError(".env 에 PA_SCHOOL_ID·PA_SCHOOL_PW 가 없어 포털에 로그인할 수 없습니다")
    page = ctx.new_page()
    page.goto(LOGIN, wait_until="networkidle", timeout=60000)
    page.fill("#userId", uid)
    page.fill("#userPswd", pw)
    page.click("button[type=submit]")
    for _ in range(40):
        page.wait_for_timeout(1000)
        if "login.htm" not in page.url:
            break
    if "login.htm" in page.url:
        raise RuntimeError("포털 로그인 실패 (아이디·비밀번호 확인)")
    page.close()


def fetch(start, end):
    """[start, end] 의 내 수업 행들 (포털 JSON). 저장된 로그인이 끊겼으면 한 번 로그인한다."""
    if "PYTEST_CURRENT_TEST" in os.environ:  # 테스트 중에는 절대 진짜 학교에 접속하지 않음
        raise RuntimeError("테스트 중 포털 접속 금지")
    from pa import browser  # noqa: F401 — Playwright 브라우저 위치(PLAYWRIGHT_BROWSERS_PATH)를 맞춘다
    from playwright.sync_api import sync_playwright
    years = sorted({start.year, end.year, start.year - 1})
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            ctx = b.new_context(locale="ko-KR", storage_state=str(STATE) if STATE.exists() else None)

            def get(y, t):
                r = ctx.request.get(API, params={"act": "table", "_out": "json", "estblScyr": str(y), "estblSctm": t,
                                                 "sttLsnYmd": f"{start:%Y%m%d}", "endLsnYmd": f"{end:%Y%m%d}"})
                if "json" not in (r.headers.get("content-type") or ""):
                    return None  # 로그인 화면으로 돌려보냄
                return r.json().get("classTables") or []

            if get(start.year, "20") is None:
                _login(ctx)
            rows = []
            for y in years:
                for t in TERMS:
                    got = get(y, t)
                    if got is None:
                        raise RuntimeError("포털이 시간표 대신 로그인 화면을 보냈습니다")
                    rows += [r for r in got if r and f"{start:%Y%m%d}" <= r["lsnYmd"] <= f"{end:%Y%m%d}"]
            ctx.storage_state(path=str(STATE))
            STATE.chmod(0o600)
            return rows
        finally:
            b.close()


def weekly(conn, force=False):
    """그 주에 아직 안 읽었으면 포털에서 읽어 meta 'portal_classes' 에 둔다. 읽었으면 (일정 수, 새 과목) 반환."""
    c = cfg()
    if not c["enabled"]:
        return None
    t_now = now()
    week = f"{t_now:%G-W%V}"
    if not force:
        if db.get_meta(conn, "portal_week") == week:
            return None
        failed = float(db.get_meta(conn, "portal_failed_at") or 0)
        if time.time() - failed < RETRY:
            return None
    start, end = week_range(t_now.date(), load_timetable()["planner"]["horizon_days"])
    try:
        rows = fetch(start, end)
    except Exception as e:
        db.set_meta(conn, "portal_failed_at", str(time.time()))
        db.set_meta(conn, "portal_error", f"{t_now:%m/%d %H:%M} {str(e)[:120]}")
        conn.commit()
        raise
    got, names = blocks(rows, set(c["offline"]))
    unknown = sorted(names - set(c["offline"]) - set(c["online"]))
    db.set_meta(conn, "portal_classes", json.dumps({"start": start.isoformat(), "end": end.isoformat(), "blocks": [
        [d.isoformat(), f"{s:%H:%M}", f"{e:%H:%M}", n, room] for d, s, e, n, room in got]}, ensure_ascii=False))
    db.set_meta(conn, "portal_unknown", "\n".join(unknown))
    db.set_meta(conn, "portal_week", week)
    db.set_meta(conn, "portal_error", "")
    db.set_meta(conn, "portal_failed_at", "")
    db.log(conn, "portal_timetable", None, blocks=len(got), unknown=unknown)
    conn.commit()
    return len(got), unknown


# ---- 캘린더 ---------------------------------------------------------------------

def digest(conn):
    return hashlib.sha256((db.get_meta(conn, "portal_classes") or "").encode()).hexdigest()


def _key(b):
    return f"{b[3]}|{b[0]}|{b[1]}"


def sync_calendar(conn, service):
    """meta 의 포털 일정을 '수업 시간표' 캘린더에 맞춘다 (그 기간만). 바뀐 게 없으면 None, 있으면 (+, -)."""
    raw = db.get_meta(conn, "portal_classes")
    if not raw or not cfg()["enabled"]:
        return None
    want = json.loads(raw)
    h = digest(conn)
    if db.get_meta(conn, "portal_calendar_hash") == h:
        return None
    from pa.gcal import get_or_create_calendar
    cal = get_or_create_calendar(service, CALENDAR, "Asia/Seoul")
    added = removed = 0
    # 예전 '매주 반복' 일정 → 날짜별 포털 일정으로 바뀌므로 지운다 (비서가 만든 것만)
    old = service.events().list(calendarId=cal, privateExtendedProperty="pa_source=timetable").execute().get("items", [])
    for ev in old:
        service.events().delete(calendarId=cal, eventId=ev["id"]).execute()
        removed += 1
    t0 = datetime.combine(date.fromisoformat(want["start"]), datetime.min.time(), KST)
    t1 = datetime.combine(date.fromisoformat(want["end"]) + timedelta(days=1), datetime.min.time(), KST)
    have = {}
    req = {"calendarId": cal, "privateExtendedProperty": "pa_source=portal", "timeMin": t0.isoformat(),
           "timeMax": t1.isoformat(), "singleEvents": True, "maxResults": 2500}
    for ev in service.events().list(**req).execute().get("items", []):
        have[ev.get("extendedProperties", {}).get("private", {}).get("pa_key")] = ev["id"]
    wanted = {_key(b): b for b in want["blocks"]}
    for k, ev_id in have.items():
        if k not in wanted:
            service.events().delete(calendarId=cal, eventId=ev_id).execute()
            removed += 1
    for k, (d, s, e, name, room) in wanted.items():
        if k in have:
            continue
        service.events().insert(calendarId=cal, body={
            "summary": name, "location": room,
            "start": {"dateTime": f"{d}T{s}:00", "timeZone": "Asia/Seoul"},
            "end": {"dateTime": f"{d}T{e}:00", "timeZone": "Asia/Seoul"},
            "extendedProperties": {"private": {"pa_source": "portal", "pa_key": k}},
        }).execute()
        added += 1
    db.set_meta(conn, "portal_calendar_hash", h)
    conn.commit()
    return added, removed


def main(argv):
    """bin/pa timetable [--force] [--dry-run]: 포털 시간표를 지금 읽어 보여 주고 (dry-run 이 아니면) 캘린더에 반영."""
    conn = db.connect()
    try:
        if not cfg()["enabled"]:
            print("config/timetable.yaml 의 portal.enabled 가 꺼져 있습니다")
            return
        res = weekly(conn, force=True)
        want = json.loads(db.get_meta(conn, "portal_classes"))
        print(f"포털 시간표 {want['start']} ~ {want['end']}: 대면 수업 {res[0]}건")
        for d, s, e, name, room in want["blocks"]:
            print(f"  {d} {s}-{e} {name} ({room})")
        if res[1]:
            print("처음 보는 과목 (대면인지 알려 주세요):", ", ".join(res[1]))
        if "--dry-run" in argv:
            return
        from pa.gcal import get_service
        db.set_meta(conn, "portal_calendar_hash", "")
        print("캘린더:", sync_calendar(conn, get_service()))
    finally:
        conn.close()
