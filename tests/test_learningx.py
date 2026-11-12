from pa.learningx import _norm, items


def mod(*its):
    return [{"module_items": list(its)}]


def test_items_kinds():
    video = {"module_item_id": 1, "title": "17강", "content_type": "attendance_item", "completed": False,
             "attendance_status": "none",
             "content_data": {"use_attendance": True, "due_at": "2026-11-17T14:59:59Z", "late_at": None,
                              "item_content_data": {"content_type": "everlec", "duration": 1585.87}}}
    pdf = {"module_item_id": 2, "title": "17강 배포용", "content_type": "attendance_item",
           "content_data": {"use_attendance": False,
                            "item_content_data": {"content_type": "pdf", "content_id": "abc", "file_name": "17강.pdf",
                                                  "view_url": "https://x/em/abc"}}}
    check = {"module_item_id": 3, "title": "[출결]", "content_type": "attendance_item", "completed": True,
             "content_data": {"use_attendance": True, "item_content_type": "smart_attendance", "due_at": "2026-11-17T08:08:40Z"}}
    quiz = {"module_item_id": 4, "title": "퀴즈", "content_type": "quiz", "content_data": {}}
    got = {mid: (kind, info) for mid, kind, info in items(mod(video, pdf, check, quiz))}
    assert got[1][0] == "lecture" and got[1][1]["minutes"] == 27 and got[1][1]["done"] is False
    assert got[2][0] == "file" and got[2][1]["file_name"] == "17강.pdf"
    assert got[3][0] == "lecture" and got[3][1]["minutes"] == 5 and got[3][1]["done"] is True
    assert 4 not in got


def test_norm_ignores_copies_and_symbols():
    assert _norm("Ch20_ Intro(1).pdf") == _norm("Ch20_ Intro.pdf")
    assert _norm("[강의자료] 윤리이론: 공리주의.pdf") == _norm("[강의자료] 윤리이론 공리주의.pdf")
