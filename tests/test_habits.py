"""습관 블록 · 하루 마무리 · 짧은 이름 · 메모 · 덜 들은 강의 (진짜 Google 은 쓰지 않음)."""
from datetime import timedelta

import pytest

from pa import db, habits, inbox, names, plan
from pa.model import now


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "pa.db")
    monkeypatch.setattr(inbox, "PATH", tmp_path / "inbox.md")
    monkeypatch.setattr(plan, "fetch_busy", lambda service, s, e: BUSY)
    inbox.PATH.write_text("## 할 일\n\n## 습관\n- 복습 ~1h 매일 저녁\n- 운동 ~40m 주2회\n- 이상한 줄\n", encoding="utf-8")
    BUSY.clear()
    return db.connect()


BUSY = []


def test_parse():
    h = habits.parse("영어 단어 ~20m 매주:월,수 아침")
    assert (h["title"], h["minutes"], h["every"], h["days"], h["window"]) == ("영어 단어", 20, "days", [0, 2], (360, 720))
    h = habits.parse("독서 ~30m 매일 21-23시")
    assert h["window"] == (21 * 60, 23 * 60) and h["every"] == "daily"
    assert habits.parse("운동 ~1h 주3회")["per_week"] == 3
    with pytest.raises(ValueError):
        habits.parse("길이 없는 습관 매일")


def test_habits_placed_in_window_and_review_added(conn):
    hs, warns = habits.load()
    assert {h["title"] for h in hs} == {"복습", "운동", habits.REVIEW} and warns  # 잘못된 줄은 경고
    p, _ = plan.run(conn, service=object(), write=False)
    hb = [(t.key, s, e) for t, s, e in p if t.key.startswith("h:")]
    review = [x for x in hb if x[0].startswith(f"h:{habits.REVIEW}@")]
    assert review and all(21 <= s.hour < 23 for _, s, _ in review)
    assert all(s.hour >= 18 for k, s, e in hb if k.startswith("h:복습@"))
    weeks = {}
    for k, s, e in hb:
        if k.startswith("h:운동@"):
            wk = s.date() - timedelta(days=s.weekday())
            weeks[wk] = weeks.get(wk, 0) + 1
    assert weeks and all(n <= 2 for n in weeks.values())  # 주2회


def test_busy_day_skips_habit_and_done_removes_it(conn):
    d = now().date() + timedelta(days=1)
    from datetime import datetime, time
    from pa.model import KST
    BUSY.append((datetime.combine(d, time(17, 0), KST), datetime.combine(d, time(23, 59), KST), "🏫 종일"))
    p, _ = plan.run(conn, service=object(), write=False)
    keys = [t.key for t, s, e in p]
    assert f"h:{habits.REVIEW}@{d.isoformat()}" not in keys  # 바쁘면 건너뜀
    later = (d + timedelta(days=1)).isoformat()
    assert f"h:{habits.REVIEW}@{later}" in keys
    habits.mark_done(conn, f"h:{habits.REVIEW}@{later}")
    p, _ = plan.run(conn, service=object(), write=False)
    assert f"h:{habits.REVIEW}@{later}" not in [t.key for t, s, e in p]


def test_short_names():
    assert names.short_name("[암브록솔의 합성] 연습문제 풀이제출") == "암브록솔의 합성"
    assert names.short_name("[강의영상] 생명의 가치와 윤리") == "생명의 가치와 윤리"
    assert names.short_name("조별학습활동 보고서 제출 게시판") == "조별학습활동 보고서"
    assert names.short_name("Ch22_배움노트작성_1장으로 정리") == "Ch22"
    assert names.short_name("제출") == "제출"  # 다 지워지면 원래 제목


def test_notes(conn):
    db.set_note(conn, "a1", memo="교수님이 그림 넣으라 함")
    db.set_note(conn, "a1", short="실습 12주")
    assert db.notes(conn)["a1"] == {"short": "실습 12주", "memo": "교수님이 그림 넣으라 함"}
    db.set_note(conn, "a1", memo="")
    assert db.notes(conn)["a1"]["memo"] is None


def test_add_habit_line(conn):
    inbox.add_habit("독서 ~30m 매일 21-23시")
    assert "- 독서 ~30m 매일 21-23시" in inbox.PATH.read_text(encoding="utf-8").split("## 습관")[1]
    with pytest.raises(ValueError):
        inbox.add_habit("길이 없음 매일")
