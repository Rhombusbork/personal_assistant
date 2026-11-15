"""마감 캘린더를 가짜 Google Calendar 로 시험."""
from datetime import timedelta

import pytest

from pa import db, deadlines
from pa.model import now


class Call:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class FakeCal:
    def __init__(self):
        self.cals = {"과제": "cal1"}
        self.events_by_id = {}
        self.n = 0

    def calendarList(self):
        return type("L", (), {"list": lambda _s: Call(lambda: {"items": [{"summary": k, "id": v} for k, v in self.cals.items()]})})()

    def calendars(self):
        def patch(calendarId, body):
            name = next(k for k, v in self.cals.items() if v == calendarId)
            return Call(lambda: self.cals.update({body["summary"]: self.cals.pop(name)}))
        def insert(body):
            return Call(lambda: self.cals.setdefault(body["summary"], f"cal{len(self.cals) + 1}") and {"id": self.cals[body["summary"]]})
        return type("C", (), {"patch": lambda _s, calendarId, body: patch(calendarId, body),
                              "insert": lambda _s, body: insert(body)})()

    def events(self):
        fake = self

        class E:
            def list(self, calendarId, privateExtendedProperty, pageToken=None, maxResults=0):
                src = privateExtendedProperty.split("=", 1)[1]
                return Call(lambda: {"items": [e for e in fake.events_by_id.values()
                                               if e["extendedProperties"]["private"]["pa_source"] == src]})

            def insert(self, calendarId, body):
                fake.n += 1
                ev = dict(body, id=f"e{fake.n}")
                return Call(lambda: fake.events_by_id.setdefault(ev["id"], ev))

            def update(self, calendarId, eventId, body):
                return Call(lambda: fake.events_by_id.update({eventId: dict(body, id=eventId)}))

            def delete(self, calendarId, eventId):
                return Call(lambda: fake.events_by_id.pop(eventId))
        return E()


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    return db.connect()


def add(conn, key, kind, days, source="canvas"):
    due = (now() + timedelta(days=days)).replace(hour=23, minute=59).isoformat()
    db.sync_source(conn, source, [{"key": key, "kind": kind, "course": "유기약화학Ⅱ 676208", "title": key,
                                   "due": due, "earliest": None, "minutes": 30, "url": ""}])


def test_all_kinds_get_reminders_and_done_items_removed(conn):
    cal = FakeCal()
    old = {"id": "old1", "summary": "📚 피드", "start": {"date": "2026-11-15"}, "end": {"date": "2026-11-16"},
           "extendedProperties": {"private": {"pa_source": "canvas", "pa_key": "event-assignment-1"}}}
    cal.events_by_id["old1"] = old
    for key, kind in (("a1", "assignment"), ("a2", "quiz"), ("m1", "lecture")):
        add(conn, key, kind, 2)
    add(conn, "i:발표", "todo", 3, source="inbox")
    c, u, r = deadlines.sync(conn, cal)
    assert "마감" in cal.cals and "과제" not in cal.cals           # 이름만 바뀜 (같은 캘린더)
    assert "마감 알림" in cal.cals
    assert (c, u, r) == (4 + 12, 0, 1)                             # 마감 4 + 알림 4×3, 예전 피드 일정 1개 정리
    evs = list(cal.events_by_id.values())
    dl = [e for e in evs if e["extendedProperties"]["private"]["pa_source"] == "deadline"]
    rm = [e for e in evs if e["extendedProperties"]["private"]["pa_source"] == "remind"]
    assert {e["summary"][0] for e in dl} == {"📚", "❓", "🎬", "✅"} and all(not e["reminders"]["overrides"] for e in dl)
    assert sorted({e["summary"].split(" · ")[0] for e in rm}) == ["⏰ 1시간 전", "⏰ 3시간 전", "⏰ 하루 전"]
    assert all(e["reminders"]["overrides"] == [{"method": "popup", "minutes": 0}] for e in rm)  # 그 시각에 알림
    assert deadlines.sync(conn, cal) == (0, 0, 0)                  # 바뀐 게 없으면 아무것도 안 함
    db.set_status(conn, "a1", "done", "auto")
    assert deadlines.sync(conn, cal) == (0, 0, 1 + 3)              # 끝낸 과제는 마감·알림 모두 지움


def test_ahead_label():
    assert [deadlines.ahead_label(m) for m in (1440, 4320, 180, 60, 30)] == ["하루 전", "3일 전", "3시간 전", "1시간 전", "30분 전"]
