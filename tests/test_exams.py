from datetime import date

from pa.exams import find_in_text

TODAY = date(2026, 11, 20)


def test_finds_final_exam_dates_and_times():
    text = "기말고사는 12월 15일(화) 10:00 - 12:00 입니다.\n과제 안내\n중간고사 결과는 10/20 공지"
    got = find_in_text(text, TODAY)
    assert got[0][:3] == ("기말고사", date(2026, 12, 15), "10:00")
    assert len(got) == 1  # 지난 중간고사(10/20)는 제외


def test_korean_time_and_slash_date():
    got = find_in_text("기말 시험: 12/18 오후 2시 30분, 강의실 301", TODAY)
    assert got[0][1] == date(2026, 12, 18) and got[0][2] == "14:30"


def test_no_exam_word_no_suggestion():
    assert find_in_text("12월 15일 과제 제출", TODAY) == []


def test_exam_item_itself_not_scheduled_but_reviews_are():
    from pa.model import Task
    from pa.plan import is_exam
    assert is_exam(Task("i:생화학 기말고사", "todo", "생화학", "생화학 기말고사", None, 60, source="inbox"))
    assert not is_exam(Task("i:생화학 기말고사@복습1", "todo", "생화학", "생화학 기말고사 복습 1/3", None, 60, source="inbox"))
    assert not is_exam(Task("a1", "assignment", "", "임상시험에서의 연구윤리", None, 60))
