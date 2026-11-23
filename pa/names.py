"""시간표 블록에 보일 짧은 이름 (규칙만 — AI 안 씀). 작은 창에서 직접 고친 이름(task_notes.short)이 있으면 그것.

  [암브록솔의 합성] 연습문제 풀이제출   → 암브록솔의 합성
  [강의영상] 생명의 가치와 윤리          → 생명의 가치와 윤리
  Ch22_배움노트작성_1장으로 정리         → Ch22
  조별학습활동 보고서 제출 게시판        → 조별학습활동 보고서
"""
import re

TAGS = re.compile(r"\[(학습활동|강의영상|강의|과제|퀴즈|공지|토론|자료|필수|선택)\]\s*")
NOISE = re.compile(r"\s*(제출\s*게시판|게시판|풀이\s*제출|제출하기|제출|배움노트\s*작성|작성하기|작성|1장으로\s*정리|정리)\s*")


def short_name(title, course=""):
    t = TAGS.sub("", title or "").strip()
    if course:  # 과목 이름은 빼기 ('생약학Ⅰ' 이면 '생약학' 도)
        for part in re.split(r"\s+", course):
            for p in {part, re.sub(r"[ⅠⅡⅢⅣⅤ\d]+$", "", part)}:
                if len(p) >= 2:
                    t = t.replace(p, " ")
    m = re.match(r"\s*\[([^\]]+)\]", t)  # [핵심] 나머지 → 핵심
    if m and m.group(1).strip():
        t = m.group(1)
    t = re.sub(r"[_·]+", " ", t)
    t = NOISE.sub(" ", t)
    t = " ".join(t.split()).strip(" -:")
    return t or (title or "").strip()
