from datetime import date

import pytest

from pa.inbox import parse_line

TODAY = date(2026, 11, 11)


def test_full_line():
    it = parse_line("린스타트업 발표 @11-13 18:00 ~90m #창업", TODAY, 60)
    assert it["title"] == "린스타트업 발표"
    assert (it["due"].month, it["due"].day, it["due"].hour, it["due"].minute) == (11, 13, 18, 0)
    assert it["minutes"] == 90 and it["course"] == "창업"


def test_defaults_and_hours():
    it = parse_line("리바이어던 발표자료 제출 @11-20 ~2h", TODAY, 60)
    assert (it["due"].hour, it["due"].minute) == (23, 59) and it["minutes"] == 120


def test_no_due():
    it = parse_line("논문 읽기", TODAY, 60)
    assert it["due"] is None and it["minutes"] == 60


def test_every_korean_and_english():
    assert parse_line("생화학 공부 ~1h 매주:화,목", TODAY, 60)["every"] == [1, 3]
    assert parse_line("운동 every:mon,fri", TODAY, 60)["every"] == [0, 4]


def test_year_rollover():
    assert parse_line("신년 계획 @01-05", TODAY, 60)["due"].year == 2027


@pytest.mark.parametrize("line", ["잘못 @13-40", "요일 매주:화,X", "@11-20 ~1h"])
def test_errors(line):
    with pytest.raises(ValueError):
        parse_line(line, TODAY, 60)


def test_quick_line_words():
    from pa.inbox import quick_line
    # 2026-11-11 은 수요일
    assert quick_line("발표 @내일 18시 ~2h #창업", TODAY) == "- [ ] 발표 @11-12 18:00 ~120m #창업"
    assert quick_line("보고서 @금", TODAY) == "- [ ] 보고서 @11-13"
    assert quick_line("회의 @수 9:30", TODAY) == "- [ ] 회의 @11-11 09:30"
    assert quick_line("정리 @11-20 9시", TODAY) == "- [ ] 정리 @11-20 09:00"
    assert quick_line("논문 읽기", TODAY) == "- [ ] 논문 읽기"


def test_slot_and_due_are_separate():
    from datetime import date
    from pa import inbox
    today = date(2026, 11, 16)
    line = inbox.quick_line("PPT 만들기 >내일 15-18시 @수", today)
    assert line == "- [ ] PPT 만들기 >11-17 15:00-18:00 @11-18"
    it = inbox.parse_line(line[6:], today, 60)
    assert (it["earliest"].hour, it["slot_end"].hour, it["minutes"]) == (15, 18, 180)
    assert it["due"].day == 18
    only = inbox.parse_line("독서 >11-17 23:00-24:00", today, 60)
    assert only["due"] is None and only["slot_end"].day == 18 and only["minutes"] == 60


def test_folder_complete(tmp_path, monkeypatch):
    from pa import folders
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    for d in ("quiz_system_project/pharmacy", "quiz_system_project/pharmacy-work", "quiet", ".hidden"):
        (tmp_path / d).mkdir(parents=True)
    assert folders.complete("~/qui") == ["~/quiet", "~/quiz_system_project"]
    assert folders.complete("~/quiz_system_project/ph") == ["~/quiz_system_project/pharmacy", "~/quiz_system_project/pharmacy-work"]
    assert ".hidden" not in " ".join(folders.complete("~/")) and folders.complete("~/.h") == ["~/.hidden"]
