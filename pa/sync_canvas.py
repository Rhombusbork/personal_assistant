"""Canvas(canvas.jejunu.ac.kr) 캘린더 피드의 과제 마감을 Google Calendar 로 동기화.

.env 의 CANVAS_ICS_URL 을 사용. 여러 번 실행해도 중복 생성되지 않는다.
사용법: python -m pa.sync_canvas [--dry-run]
"""
import argparse
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone

from pa.gcal import ROOT, get_or_create_calendar, get_service

TZ = "Asia/Seoul"
CALENDAR_NAME = "과제"


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def unescape(s):
    return s.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def parse_ics(text):
    """Canvas 피드용 최소 ICS 파서. 줄 접힘(folding)을 풀고 VEVENT 들을 dict 로 반환."""
    lines = []
    for raw in text.splitlines():
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    events, cur = [], None
    for line in lines:
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, value = line.split(":", 1)
            name, *params = key.split(";")
            cur[name] = (value, params)
    return events


def to_gcal_times(value, params):
    """Canvas 는 종일 마감을 'VALUE=DATE:20261014T000000', 시각 마감을 UTC 로 준다."""
    if "VALUE=DATE" in params:
        d = date(int(value[:4]), int(value[4:6]), int(value[6:8]))
        return {"date": d.isoformat()}, {"date": (d + timedelta(days=1)).isoformat()}
    due = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    start = due - timedelta(minutes=30)
    return {"dateTime": start.isoformat(), "timeZone": TZ}, {"dateTime": due.isoformat(), "timeZone": TZ}


def build_event(ev):
    uid = ev["UID"][0]
    start, end = to_gcal_times(*ev["DTSTART"])
    url = ev.get("URL", ("", []))[0]
    desc = unescape(ev.get("DESCRIPTION", ("", []))[0])
    return uid, {
        "summary": "📚 " + unescape(ev["SUMMARY"][0]).strip(),
        "start": start,
        "end": end,
        "description": f"{url}\n\n{desc}".strip(),
        "transparency": "transparent",  # 마감 표시일 뿐이므로 '바쁨'으로 잡지 않음
        "extendedProperties": {"private": {"pa_source": "canvas", "pa_key": uid}},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Google 에 쓰지 않고 출력만")
    args = parser.parse_args()

    load_env()
    url = os.environ.get("CANVAS_ICS_URL")
    if not url:
        raise SystemExit(".env 에 CANVAS_ICS_URL 이 없습니다.")
    with urllib.request.urlopen(url) as resp:
        events = [build_event(e) for e in parse_ics(resp.read().decode("utf-8"))]

    if args.dry_run:
        for uid, ev in sorted(events, key=lambda x: str(x[1]["start"])):
            print(ev["start"].get("date") or ev["start"]["dateTime"], ev["summary"])
        print(f"총 {len(events)}건")
        return

    service = get_service()
    cal_id = get_or_create_calendar(service, CALENDAR_NAME, TZ)
    existing, token = {}, None
    while True:
        page = service.events().list(
            calendarId=cal_id, privateExtendedProperty="pa_source=canvas", pageToken=token, maxResults=2500
        ).execute()
        for item in page.get("items", []):
            existing[item["extendedProperties"]["private"]["pa_key"]] = item["id"]
        token = page.get("nextPageToken")
        if not token:
            break

    created = updated = 0
    for uid, ev in events:
        if uid in existing:
            service.events().update(calendarId=cal_id, eventId=existing[uid], body=ev).execute()
            updated += 1
        else:
            service.events().insert(calendarId=cal_id, body=ev).execute()
            created += 1
    print(f"Canvas 동기화 완료: 생성 {created}, 갱신 {updated}")


if __name__ == "__main__":
    main()
