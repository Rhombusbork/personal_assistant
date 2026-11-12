"""시험 일정 후보: Canvas 공지에서 '기말고사 12월 15일 10:00' 같은 문장을 찾아 제안한다 (코드만, Claude 안 씀).

확정은 사용자가 한다 — 대시보드의 [할 일로 추가] 를 누르면 inbox 에
'<과목> 기말고사 @12-15 10:00 #<과목>' 이 들어가고, 시험 모드(시험 7·4·2일 전 복습)가 켜진다.
[아니요] 는 기억해서 다시 제안하지 않는다.
"""
import json
import re
from datetime import date, timedelta

from pa import db, materials
from pa.model import now, short_course

EXAM_WORD = re.compile(r"(기말|중간)\s*(고사|시험)")
DATE = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일|(?<![\d/])(\d{1,2})\s*/\s*(\d{1,2})(?![\d/])")
TIME = re.compile(r"(?:오전|오후)?\s*(\d{1,2})\s*(?::\s*(\d{2})|시\s*(?:(\d{1,2})\s*분)?)")
AHEAD_DAYS = 90


def _subject(course):
    dirs = materials.course_dirs(course)
    return dirs[1].name if dirs else short_course(course)


def find_in_text(text, today):
    """문장들에서 (종류, 날짜, 'HH:MM' 또는 None, 문장) 목록."""
    out = []
    for line in text.split("\n"):
        w = EXAM_WORD.search(line)
        if not w:
            continue
        for d in DATE.finditer(line):
            mo, da = (int(d.group(1)), int(d.group(2))) if d.group(1) else (int(d.group(3)), int(d.group(4)))
            try:
                when = date(today.year, mo, da)
            except ValueError:
                continue
            if when < today - timedelta(days=180):  # 12월에 1월 날짜를 쓴 경우
                when = when.replace(year=today.year + 1)
            if not today <= when <= today + timedelta(days=AHEAD_DAYS):
                continue
            hh = None
            t = TIME.search(line[d.end():d.end() + 25])
            if t:
                h = int(t.group(1))
                if "오후" in line[d.end():d.end() + 25] and h < 12:
                    h += 12
                if 7 <= h <= 21:
                    hh = f"{h:02d}:{int(t.group(2) or t.group(3) or 0):02d}"
            out.append((w.group(1) + w.group(2), when, hh, line.strip()[:120]))
    return out


def suggestions(conn):
    today = now().date()
    dismissed = set(json.loads(db.get_meta(conn, "exam_dismissed") or "[]"))
    have = {r["title"] for r in conn.execute("SELECT title FROM tasks WHERE source = 'inbox' AND status != 'gone'")}
    seen, out = set(), []
    for n in conn.execute("SELECT course, title, text FROM notices ORDER BY posted_at DESC"):
        subj = _subject(n["course"])
        for kind, when, hh, line in find_in_text(n["title"] + "\n" + n["text"], today):
            sid = f"{subj}|{kind}|{when.isoformat()}"
            title = f"{subj} {kind}"
            if sid in dismissed or sid in seen or title in have:
                continue
            seen.add(sid)
            out.append({"id": sid, "title": title, "course": subj, "date": when.isoformat(), "time": hh,
                        "from": n["title"][:60], "line": line})
    return sorted(out, key=lambda x: x["date"])


def dismiss(conn, sid):
    d = json.loads(db.get_meta(conn, "exam_dismissed") or "[]")
    if sid not in d:
        d.append(sid)
    db.set_meta(conn, "exam_dismissed", json.dumps(d, ensure_ascii=False))
    conn.commit()
