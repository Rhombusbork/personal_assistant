"""포털 시간표: 대면 과목만, 휴강 빼기, 교시 합치기, 주 1회, 캘린더 맞추기 (진짜 학교·Google 은 부르지 않음)."""
import json
from datetime import date

import pytest

from pa import db, portal


def row(d, name, s, e, cancel="N"):
    return {"lsnYmd": d, "sbjctNm": name, "bgngHr": s, "endHr": e, "cclctYn": cancel, "lctrmNm": "약학대학1호관102"}


ROWS = [row("20261119", "약학실습Ⅱ", "15:00", "15:50"), row("20261119", "약학실습Ⅱ", "16:00", "16:50"),
        row("20261119", "약학실습Ⅱ", "17:00", "17:50"), row("20261116", "생약학Ⅰ", "12:00", "12:50"),
        row("20261124", "물리약학Ⅱ", "13:30", "14:45", cancel="Y"), row("20261116", "물리약학Ⅱ", "13:30", "14:45"),
        None, row("20261117", "새과목", "09:00", "09:50")]


def test_blocks_offline_merge_and_cancel():
    got, names = portal.blocks(ROWS, {"약학실습Ⅱ", "물리약학Ⅱ"})
    assert [(str(d), f"{s:%H:%M}", f"{e:%H:%M}", n) for d, s, e, n, _ in got] == [
        ("2026-11-16", "13:30", "14:45", "물리약학Ⅱ"), ("2026-11-19", "15:00", "17:50", "약학실습Ⅱ")]
    assert "새과목" in names and "생약학Ⅰ" in names


def test_week_range_covers_plan_horizon():
    assert portal.week_range(date(2026, 11, 18), 14) == (date(2026, 11, 16), date(2026, 12, 6))


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    monkeypatch.setattr(portal, "cfg", lambda: {"enabled": True, "offline": ["물리약학Ⅱ"], "online": ["생약학Ⅰ"]})
    monkeypatch.setattr(portal, "load_timetable", lambda: {"planner": {"horizon_days": 14}})
    c = db.connect()
    yield c
    c.close()


def test_weekly_once_per_week_and_unknown(conn, monkeypatch):
    calls = []
    monkeypatch.setattr(portal, "fetch", lambda s, e: calls.append((s, e)) or ROWS)
    n, unknown = portal.weekly(conn)
    assert n == 1 and unknown == ["새과목", "약학실습Ⅱ"]
    assert portal.weekly(conn) is None and len(calls) == 1  # 같은 주에는 다시 안 읽음
    assert json.loads(db.get_meta(conn, "portal_classes"))["blocks"][0][3] == "물리약학Ⅱ"


def test_weekly_failure_waits(conn, monkeypatch):
    def boom(s, e):
        raise RuntimeError("로그인 실패")
    monkeypatch.setattr(portal, "fetch", boom)
    with pytest.raises(RuntimeError):
        portal.weekly(conn)
    assert "로그인 실패" in db.get_meta(conn, "portal_error")
    assert portal.weekly(conn) is None  # 6시간 안에는 다시 시도하지 않음 (계정 잠김 방지)


class FakeCal:
    """Google Calendar 흉내: events().list/insert/delete 만"""
    def __init__(self, events):
        self.items, self.ops = events, []

    def calendarList(self):
        return self

    def events(self):
        return self

    def list(self, **kw):
        if "calendarId" not in kw:  # calendarList().list()
            return _Exec({"items": [{"summary": "수업 시간표", "id": "cal"}]})
        src = kw["privateExtendedProperty"].split("=")[1]
        return _Exec({"items": [e for e in self.items if e["extendedProperties"]["private"]["pa_source"] == src]})

    def insert(self, calendarId, body):
        self.ops.append(("+", body["extendedProperties"]["private"]["pa_key"]))
        return _Exec({})

    def delete(self, calendarId, eventId):
        self.ops.append(("-", eventId))
        return _Exec({})


class _Exec:
    def __init__(self, r):
        self.r = r

    def execute(self):
        return self.r


def test_sync_calendar_replaces_weekly_series_and_diffs(conn):
    db.set_meta(conn, "portal_classes", json.dumps({"start": "2026-11-16", "end": "2026-12-06", "blocks": [
        ["2026-11-16", "13:30", "14:45", "물리약학Ⅱ", ""], ["2026-11-18", "13:30", "14:45", "물리약학Ⅱ", ""]]}))
    ev = lambda i, src, key: {"id": i, "extendedProperties": {"private": {"pa_source": src, "pa_key": key}}}
    cal = FakeCal([ev("old", "timetable", "물리약학|mon|13:30"), ev("keep", "portal", "물리약학Ⅱ|2026-11-16|13:30"),
                   ev("gone", "portal", "물리약학Ⅱ|2026-11-23|13:30")])
    assert portal.sync_calendar(conn, cal) == (1, 2)
    assert sorted(cal.ops) == [("+", "물리약학Ⅱ|2026-11-18|13:30"), ("-", "gone"), ("-", "old")]
    assert portal.sync_calendar(conn, cal) is None  # 바뀐 게 없으면 Google 에 묻지 않음


def test_no_real_portal_in_tests():
    with pytest.raises(RuntimeError):
        portal.fetch(date(2026, 11, 16), date(2026, 11, 22))
