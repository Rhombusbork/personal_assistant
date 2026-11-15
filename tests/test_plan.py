from datetime import datetime, timedelta

from pa import calibrate
from pa.model import KST, Task
from pa.plan import make_plan

CFG = {"day_start": "09:00", "day_end": "23:00", "break_minutes": 10, "max_minutes_per_day": 240,
       "main_days": ["mon", "wed", "fri", "sat"], "fallback_days": ["sun"], "split_over": 120, "chunk_minutes": 90}
NOW = datetime(2026, 11, 16, 9, 0, tzinfo=KST)  # 월요일


def task(key, minutes, due_days, kind="todo", course=""):
    return Task(key, kind, course, key, NOW + timedelta(days=due_days), minutes)


def test_edf_and_main_days():
    plan, failed, why = make_plan([task("b", 60, 5), task("a", 60, 2)], [], CFG, NOW, {})
    assert [t.key for t, s, e in plan][0] == "a" and not failed
    assert all(s.strftime("%a") in ("Mon", "Wed", "Fri", "Sat") for t, s, e in plan)
    assert "월·수·금·토" in why["a"]


def test_big_task_split_across_days():
    plan, failed, why = make_plan([task("report", 240, 6)], [], CFG, NOW, {})
    keys = [t.key for t, s, e in plan]
    assert keys == ["report#1", "report#2", "report#3"] and not failed
    assert len({s.date() for t, s, e in plan}) == 3  # 서로 다른 날
    assert all(e - s <= timedelta(minutes=90) for t, s, e in plan)
    assert plan[0][0].title.endswith("(1/3)") and "3번으로 나눔" in why["report#1"]


def test_lecture_never_split():
    plan, _, _ = make_plan([task("lec", 150, 6, kind="lecture")], [], CFG, NOW, {})
    assert [t.key for t, s, e in plan] == ["lec"]


def test_any_day_fallback_when_due_on_tuesday():
    now = NOW.replace(hour=22, minute=30)
    t = Task("t", "todo", "", "t", (NOW + timedelta(days=1)).replace(hour=23, minute=59), 60)  # 화요일 마감
    plan, failed, why = make_plan([t], [], CFG, now, {})
    assert not failed and plan[0][1].strftime("%a") == "Tue" and "다른 요일" in why["t"]


def test_pinned_block_not_duplicated():
    t = task("r", 120, 3)
    pinned = {"r": (NOW - timedelta(minutes=30), NOW + timedelta(minutes=30))}
    plan, _, _ = make_plan([t], [], CFG, NOW, pinned)
    assert [p[0].key for p in plan] == ["r#2"]  # 남은 60분은 새 키로


def test_calibration_median_and_minimum(monkeypatch):
    monkeypatch.setattr(calibrate, "samples", lambda c: [("lecture", "유기약화학", r) for r in (1.2, 1.4, 1.6)] + [("todo", "", 2.0)])
    fs = calibrate.factors(None)
    assert round(calibrate.factor_for(fs, "lecture", "유기약화학Ⅱ 676208"), 2) == 1.4
    assert calibrate.factor_for(fs, "todo", "") == 1.0  # 1번뿐이면 쓰지 않음


def test_lecture_before_quiz_on_same_deadline():
    q = task("quiz", 20, 2, kind="quiz", course="분석")
    q.due -= timedelta(seconds=59)  # 실제 데이터처럼 퀴즈 마감이 몇십 초 빠름
    lec = task("lec", 30, 2, kind="lecture", course="분석")
    plan, _, _ = make_plan([q, lec], [], CFG, NOW, {})
    assert [t.key for t, s, e in plan] == ["lec", "quiz"] and plan[1][1] >= plan[0][2]


def test_popup_reminders():
    from pa.config import popup
    assert popup([1410, 150, 30])["overrides"] == [{"method": "popup", "minutes": m} for m in (1410, 150, 30)]
    assert popup(0)["overrides"] == [] and popup(10)["overrides"][0]["minutes"] == 10


def test_overdue_task_planned_on_redo_day():
    from datetime import datetime, timedelta

    from pa.model import KST, Task
    from pa.plan import _apply_redo
    t_now = datetime(2026, 11, 16, 10, 0, tzinfo=KST)
    late = Task(key="a1", kind="assignment", course="", title="리포트", due=t_now - timedelta(days=2), minutes=60)
    other = Task(key="a2", kind="assignment", course="", title="다른", due=t_now + timedelta(days=1), minutes=60)
    out = {t.key: t for t in _apply_redo([late, other], {"a1": "2026-11-18", "a2": "2026-11-20"}, t_now)}
    assert out["a1"].due == datetime(2026, 11, 18, 23, 59, tzinfo=KST) and out["a1"].earliest == datetime(2026, 11, 18, tzinfo=KST)
    assert out["a2"].due == other.due  # 마감이 안 지난 일은 그대로
    today = {t.key: t for t in _apply_redo([late], {"a1": "2026-11-16"}, t_now)}
    assert today["a1"].due.date().isoformat() == "2026-11-16" and today["a1"].earliest is None
    assert _apply_redo([late], {"a1": "2026-11-15"}, t_now)[0].due == late.due  # 하기로 한 날이 지나면 다시 '지남'
