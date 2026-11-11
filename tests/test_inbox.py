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
