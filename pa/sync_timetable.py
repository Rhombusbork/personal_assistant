"""config/timetable.yaml 의 수업을 Google Calendar 의 매주 반복 일정으로 동기화.

여러 번 실행해도 중복 생성되지 않고, 기존 일정은 갱신된다.
사용법: python -m pa.sync_timetable [--dry-run]
"""
import argparse
from datetime import date, datetime, timedelta

from pa.config import load_timetable
from pa.gcal import get_or_create_calendar, get_service

TZ = "Asia/Seoul"
CALENDAR_NAME = "수업 시간표"
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
RRULE_DAYS = {"mon": "MO", "tue": "TU", "wed": "WE", "thu": "TH", "fri": "FR", "sat": "SA", "sun": "SU"}


def build_event(c, sem_start, sem_end):
    first = sem_start + timedelta(days=(DAYS[c["day"]] - sem_start.weekday()) % 7)
    # 종강일 23:59:59 KST = 14:59:59 UTC
    until = sem_end.strftime("%Y%m%dT145959Z")
    key = f"{c['name']}|{c['day']}|{c['start']}"
    return key, {
        "summary": c["name"],
        "start": {"dateTime": f"{first.isoformat()}T{c['start']}:00", "timeZone": TZ},
        "end": {"dateTime": f"{first.isoformat()}T{c['end']}:00", "timeZone": TZ},
        "recurrence": [f"RRULE:FREQ=WEEKLY;BYDAY={RRULE_DAYS[c['day']]};UNTIL={until}"],
        "extendedProperties": {"private": {"pa_source": "timetable", "pa_key": key}},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Google 에 쓰지 않고 출력만")
    args = parser.parse_args()

    cfg = load_timetable()
    sem_start = date.fromisoformat(cfg["semester_start"])
    sem_end = date.fromisoformat(cfg["semester_end"])
    events = [build_event(c, sem_start, sem_end) for c in cfg["classes"]]

    if args.dry_run:
        for key, ev in events:
            print(key, ev["start"]["dateTime"], ev["recurrence"][0])
        return

    service = get_service()
    cal_id = get_or_create_calendar(service, CALENDAR_NAME, TZ)
    for key, ev in events:
        found = service.events().list(
            calendarId=cal_id, privateExtendedProperty=f"pa_key={key}", singleEvents=False
        ).execute().get("items", [])
        if found:
            service.events().update(calendarId=cal_id, eventId=found[0]["id"], body=ev).execute()
            print("갱신:", key)
        else:
            service.events().insert(calendarId=cal_id, body=ev).execute()
            print("생성:", key)


if __name__ == "__main__":
    main()
