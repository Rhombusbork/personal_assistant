"""inbox.md — 할 일 입력 블록.

## 할 일
- [ ] 리바이어던 발표자료 제출 @11-20 ~2h          마감 11/20 23:59, 2시간
- [ ] 린스타트업 발표 @11-13 18:00 ~90m #창업       시각·과목 지정
- [ ] 생화학 공부 ~1h 매주:화,목                    매주 화·목 그날 안에
- [ ] 논문 읽기                                      기한 없음 = 장기 할 일
- [x] 린스타트업 텍스트 제출 @11-11                  체크 = 완료 (체크 해제하면 다시 열림)

## 완료        한 번 적으면 완료 처리 (지워도 그대로 완료)
- 생약학 근류 -1                                     키 또는 제목 단어들

## 제외        여기 있는 동안 계속 제외 (지우면 다시 나타남)
- 생약학 조별학습활동
"""
import re
from datetime import date, datetime, time, timedelta

from pa import db
from pa.config import ROOT, load_timetable
from pa.model import KST, label, now

PATH = ROOT / "inbox.md"
TEMPLATE = """# 📥 inbox — 할 일 입력 (저장하면 자동 반영)
<!--
쓰는 법
- [ ] 제목 @11-20 ~2h #과목       마감 11/20 23:59, 예상 2시간, 과목
- [ ] 제목 @11-13 18:00 ~90m       마감 시각 지정
- [ ] 제목 ~1h 매주:화,목           매주 그 요일에 하는 일
- [ ] 제목                          기한 없음 (장기 할 일)
- [x] 제목 ...                      체크 = 완료 (체크 풀면 다시 열림)
이 주석 안의 줄은 무시됩니다.
-->

## 할 일

## 완료
<!-- 키(TODAY.md 의 `a123`, `m456` 등)나 제목 단어를 적으면 완료 처리. 지워도 완료는 유지 -->

## 제외
<!-- 여기 적혀 있는 동안 계속 제외 (조장만 제출하는 과제 등). 지우면 다시 나타남 -->
"""

DAY_MAP = {**{d: i for i, d in enumerate("월화수목금토일")},
           **{d: i for i, d in enumerate(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])}}
RE_DUE = re.compile(r"@(?:(\d{4})-)?(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?")
RE_MIN = re.compile(r"~(\d+(?:\.\d+)?)\s*(h|m|시간|분)")
RE_COURSE = re.compile(r"#(\S+)")
RE_EVERY = re.compile(r"(?:매주|every):(\S+)")
RE_CHECK = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*)$")
RE_BULLET = re.compile(r"^\s*[-*]\s+(?:\[[ xX]\]\s+)?(.*)$")


def parse_line(text, today, default_minutes):
    """할 일 한 줄 → dict. 잘못된 부분이 있으면 ValueError."""
    item = {"due": None, "minutes": default_minutes, "course": "", "every": None}
    m = RE_DUE.search(text)
    if m:
        y, mo, d, hh, mm = m.groups()
        year = int(y) if y else today.year
        try:
            dt = datetime(year, int(mo), int(d), int(hh or 23), int(mm or 59), tzinfo=KST)
        except ValueError:
            raise ValueError(f"날짜가 올바르지 않음: {m.group(0)}")
        if not y and dt.date() < today - timedelta(days=60):  # 연도 생략 + 먼 과거 → 내년
            dt = dt.replace(year=year + 1)
        item["due"] = dt
        text = text.replace(m.group(0), " ")
    m = RE_MIN.search(text)
    if m:
        n, unit = float(m.group(1)), m.group(2)
        item["minutes"] = int(n * 60 if unit in ("h", "시간") else n)
        text = text.replace(m.group(0), " ")
    m = RE_EVERY.search(text)
    if m:
        try:
            item["every"] = sorted({DAY_MAP[d.strip().lower()] for d in m.group(1).split(",") if d.strip()})
        except KeyError:
            raise ValueError(f"요일을 알 수 없음: {m.group(0)}")
        text = text.replace(m.group(0), " ")
    m = RE_COURSE.search(text)
    if m:
        item["course"] = m.group(1)
        text = text.replace(m.group(0), " ")
    item["title"] = " ".join(text.split())
    if not item["title"]:
        raise ValueError("제목이 없음")
    return item


def read_sections():
    """inbox.md → {'todo': [(줄번호, 체크여부, 내용)], 'done': [...], 'ignore': [...]}"""
    out = {"todo": [], "done": [], "ignore": []}
    section, in_comment = "todo", False
    for no, line in enumerate(PATH.read_text().splitlines(), 1):
        # <!-- 주석 --> 안의 줄은 무시
        if in_comment or line.lstrip().startswith("<!--"):
            in_comment = "-->" not in line
            continue
        if line.startswith("#"):
            section = "done" if "완료" in line else "ignore" if "제외" in line else "todo"
            continue
        if section == "todo":
            m = RE_CHECK.match(line)
            if m:
                out["todo"].append((no, m.group(1).lower() == "x", m.group(2).strip()))
        else:
            m = RE_BULLET.match(line)
            if m and m.group(1).strip():
                out[section].append((no, False, m.group(1).strip().strip("`")))
    return out


# ---- 쓰기 (대시보드 입력 → inbox.md) ----------------------------------------

SECTION_HEAD = {"todo": "## 할 일", "done": "## 완료", "ignore": "## 제외"}
KO_DAYS = "월화수목금토일"


def format_line(title, due=None, minutes=None, course="", every=None):
    """입력값 → inbox 한 줄. due: datetime, every: 요일 번호 목록(0=월)."""
    # 제목 안의 기호가 문법으로 읽히지 않게 비슷한 전각 문자로 바꾼다
    title = " ".join(title.replace("@", "＠").replace("~", "∼").replace("#", "＃").split())
    if not title:
        raise ValueError("제목이 없음")
    parts = [f"- [ ] {title}"]
    if due:
        parts.append(f"@{due:%m-%d}" + ("" if (due.hour, due.minute) == (23, 59) else f" {due:%H:%M}"))
    if minutes:
        parts.append(f"~{minutes}m")
    if course:
        parts.append("#" + "_".join(course.split()))
    if every:
        parts.append("매주:" + ",".join(KO_DAYS[d] for d in sorted(set(every))))
    return " ".join(parts)


def _insert(section, line):
    """section 맨 위(제목과 바로 아래 주석 다음)에 한 줄 넣는다. 섹션이 없으면 끝에 만든다."""
    lines = PATH.read_text().splitlines() if PATH.exists() else TEMPLATE.splitlines()
    head = SECTION_HEAD[section]
    idx = next((i for i, l in enumerate(lines) if l.strip() == head), None)
    if idx is None:
        lines += ["", head, line]
    else:
        pos, in_comment = idx + 1, False
        while pos < len(lines) and (in_comment or lines[pos].lstrip().startswith("<!--")):
            in_comment = "-->" not in lines[pos]
            pos += 1
        lines.insert(pos, line)
    PATH.write_text("\n".join(lines) + "\n")


def add_task(**fields):
    line = format_line(**fields)
    _insert("todo", line)
    return line


def _todo_line_index(lines, title):
    """제목이 같은 (반복 아닌) 할 일 줄 번호."""
    for i, l in enumerate(lines):
        m = RE_CHECK.match(l)
        if m:
            try:
                it = parse_line(m.group(2), now().date(), 60)
            except ValueError:
                continue
            if it["title"] == title and it["every"] is None:
                return i
    return None


def mark_done(key):
    """inbox 할 일이면 체크, 그 밖(Canvas·반복 할 일)은 ## 완료 에 키를 적는다."""
    if key.startswith("i:") and "@" not in key:
        lines = PATH.read_text().splitlines()
        i = _todo_line_index(lines, key[2:])
        if i is not None:
            lines[i] = re.sub(r"\[ \]", "[x]", lines[i], count=1)
            PATH.write_text("\n".join(lines) + "\n")
            return
    _insert("done", f"- {key}")


def ignore(key):
    _insert("ignore", f"- {key}")


def remove(key):
    """inbox 에 직접 쓴 할 일 줄을 지운다."""
    lines = PATH.read_text().splitlines()
    i = _todo_line_index(lines, key[2:]) if key.startswith("i:") else None
    if i is None:
        raise ValueError("inbox 에 없는 항목")
    del lines[i]
    PATH.write_text("\n".join(lines) + "\n")


def match(conn, text, statuses):
    """키가 정확히 같거나, 적은 단어가 모두 '과목 · 제목'에 들어 있는 항목들."""
    marks = ",".join("?" * len(statuses))
    row = conn.execute(f"SELECT key FROM tasks WHERE key = ? AND status IN ({marks})", (text, *statuses)).fetchone()
    if row:
        return [row["key"]]
    words = text.lower().split()
    return [t.key for t in db.tasks(conn, f"status IN ({marks})", statuses)
            if all(w in label(t).lower() for w in words)]


def sync(conn):
    """inbox.md 를 읽어 저장소에 반영. 경고 문장 목록을 반환 (TODAY.md 에 표시)."""
    if not PATH.exists():
        PATH.write_text(TEMPLATE)
    cfg = load_timetable()["planner"]
    today = now().date()
    horizon = today + timedelta(days=cfg["horizon_days"])
    sections = read_sections()
    warnings, items, checked = [], [], set()

    for no, is_checked, text in sections["todo"]:
        try:
            it = parse_line(text, today, cfg["minutes"]["assignment"])
        except ValueError as e:
            warnings.append(f"inbox.md {no}번째 줄 해석 실패 ({e}): `{text}`")
            continue
        base = {"kind": "todo", "course": it["course"], "title": it["title"], "minutes": it["minutes"], "url": ""}
        if it["every"] is not None:
            if is_checked:  # 반복 할 일에 체크 = 반복 중지
                continue
            d = today
            while d <= horizon:
                if d.weekday() in it["every"]:
                    items.append({**base, "key": f"i:{it['title']}@{d:%m-%d}",
                                  "due": datetime.combine(d, time(23, 59), KST).isoformat(),
                                  "earliest": datetime.combine(d, time(0, 0), KST).isoformat()})
                d += timedelta(days=1)
            continue
        key = f"i:{it['title']}"
        items.append({**base, "key": key, "due": it["due"].isoformat() if it["due"] else None, "earliest": None})
        if is_checked:
            checked.add(key)

    db.sync_source(conn, "inbox", items, mark_missing_gone=True)

    # 체크박스: 체크 = 완료, 체크 해제 = 다시 열기 (inbox 로 완료한 것만)
    for it in items:
        k = it["key"]
        row = conn.execute("SELECT status, status_by FROM tasks WHERE key = ?", (k,)).fetchone()
        if k in checked:
            db.set_status(conn, k, "done", "inbox")
        elif row["status"] == "done" and row["status_by"] == "inbox":
            db.set_status(conn, k, "open", "inbox")

    # ## 완료 — 한 번 처리하면 끝 (한 항목에만 맞아야 함)
    for no, _, text in sections["done"]:
        keys = match(conn, text, ("open",))
        if not keys and not match(conn, text, ("done",)):
            warnings.append(f"inbox.md {no}번째 줄 '{text}' 에 맞는 항목 없음")
        elif len(keys) == 1:
            db.set_status(conn, keys[0], "done", "inbox")
        elif len(keys) > 1:
            warnings.append(f"inbox.md {no}번째 줄 '{text}' 가 {len(keys)}개 항목에 맞음 — 더 구체적으로 쓰거나 키를 쓰세요: "
                            + ", ".join(f"`{k}`" for k in keys[:5]))

    # ## 제외 — 여기 있는 동안만 제외
    ignore_keys = set()
    for no, _, text in sections["ignore"]:
        keys = match(conn, text, ("open", "ignored"))
        if not keys:
            warnings.append(f"inbox.md {no}번째 줄 '{text}' 에 맞는 항목 없음")
        ignore_keys.update(keys)
    for k in ignore_keys:
        db.set_status(conn, k, "ignored", "inbox")
    for r in conn.execute("SELECT key FROM tasks WHERE status = 'ignored' AND status_by = 'inbox'").fetchall():
        if r["key"] not in ignore_keys:
            db.set_status(conn, r["key"], "open", "inbox")

    db.set_meta(conn, "inbox_warnings", "\n".join(warnings))
    conn.commit()
    return warnings
