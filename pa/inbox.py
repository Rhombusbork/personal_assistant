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
from pa.model import KST, label, now, short_course

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
RE_START = re.compile(r"(?<!\S)>(?:(\d{4})-)?(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?:-(\d{1,2}):(\d{2}))?)?")
# >11-15 09:00 = 이때부터 하기 · >11-17 15:00-18:00 = 그 시간에 하기 (고정 블록, 마감 @ 와 따로)
RE_MIN = re.compile(r"~(\d+(?:\.\d+)?)\s*(h|m|시간|분)")
RE_COURSE = re.compile(r"#(\S+)")
RE_EVERY = re.compile(r"(?:매주|every):(\S+)")
RE_CHECK = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*)$")
RE_BULLET = re.compile(r"^\s*[-*]\s+(?:\[[ xX]\]\s+)?(.*)$")


KEYLIKE = re.compile(r"[a-z]\d+|[a-z]:\S+")  # 'a475087', 'm2890877', 'i:제목' 같은 키
RE_EXAM = re.compile(r"(?<!임상)시험|고사")  # '임상시험' 같은 말은 시험이 아님


def exam_reviews(key, base, exam, cfg, t_now):
    """시험 전 복습 블록: 시험 7·4·2일 전부터 각 이틀 안에 (설정: exam_review)."""
    ex = cfg.get("exam_review", {"offsets": [7, 4, 2], "minutes": 60})
    out, n = [], len(ex["offsets"])
    for i, d in enumerate(ex["offsets"], 1):
        start = datetime.combine(exam.date() - timedelta(days=d), time(0, 0), KST)
        end = min(datetime.combine(exam.date() - timedelta(days=max(d - 2, 1)), time(23, 59), KST), exam)
        if end < t_now:
            continue
        out.append({**base, "key": f"{key}@복습{i}", "title": f"{base['title']} 복습 {i}/{n}",
                    "minutes": ex["minutes"], "due": end.isoformat(), "earliest": start.isoformat()})
    return out


def parse_line(text, today, default_minutes):
    """할 일 한 줄 → dict. 잘못된 부분이 있으면 ValueError."""
    original = text
    item = {"due": None, "minutes": default_minutes, "course": "", "every": None, "earliest": None, "slot_end": None}
    m = RE_START.search(text)
    if m:
        y, mo, d, hh, mm, eh, em = m.groups()
        try:
            item["earliest"] = datetime(int(y) if y else today.year, int(mo), int(d), int(hh or 0), int(mm or 0), tzinfo=KST)
            if eh:
                end = item["earliest"].replace(hour=0, minute=0) + timedelta(hours=int(eh), minutes=int(em))  # 24:00 도 됨
                if end <= item["earliest"]:
                    raise ValueError
                item["slot_end"] = end
        except ValueError:
            raise ValueError(f"할 시간이 올바르지 않음: {m.group(0)}")
        if not y and item["earliest"].date() < today - timedelta(days=60):  # 연도 생략 + 먼 과거 → 내년
            item["earliest"] = item["earliest"].replace(year=item["earliest"].year + 1)
            item["slot_end"] = item["slot_end"] and item["slot_end"].replace(year=item["slot_end"].year + 1)
        text = text.replace(m.group(0), " ")
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
    if item["slot_end"] and not RE_MIN.search(original):  # 할 시간을 정했으면 예상 시간 = 그 길이
        item["minutes"] = int((item["slot_end"] - item["earliest"]).total_seconds() // 60)
    return item


def read_sections():
    """inbox.md → {'todo': [(줄번호, 체크여부, 내용)], 'done': [...], 'ignore': [...], 'habit': [...]} (습관은 pa/habits.py)"""
    out = {"todo": [], "done": [], "ignore": [], "habit": []}
    section, in_comment = "todo", False
    for no, line in enumerate(PATH.read_text(encoding="utf-8").splitlines(), 1):
        # <!-- 주석 --> 안의 줄은 무시
        if in_comment or line.lstrip().startswith("<!--"):
            in_comment = "-->" not in line
            continue
        if line.startswith("#"):
            section = "done" if "완료" in line else "ignore" if "제외" in line else "habit" if "습관" in line else "todo"
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

SECTION_HEAD = {"todo": "## 할 일", "done": "## 완료", "ignore": "## 제외", "habit": "## 습관"}
KO_DAYS = "월화수목금토일"


def format_line(title, due=None, minutes=None, course="", every=None, earliest=None, slot_end=None):
    """입력값 → inbox 한 줄. due: datetime, every: 요일 번호 목록(0=월), earliest~slot_end: 할 시간."""
    # 제목 안의 기호가 문법으로 읽히지 않게 비슷한 전각 문자로 바꾼다
    title = " ".join(title.replace("@", "＠").replace("~", "∼").replace("#", "＃").split())
    if not title:
        raise ValueError("제목이 없음")
    title = title.replace(">", "＞")
    parts = [f"- [ ] {title}"]
    if earliest:
        day = f">{earliest:%m-%d}" if earliest.year == now().year else f">{earliest:%Y-%m-%d}"
        span = f" {earliest:%H:%M}"
        if slot_end:
            em = int((slot_end - earliest.replace(hour=0, minute=0)).total_seconds() // 60)
            span += f"-{em // 60:02d}:{em % 60:02d}"
        parts.append(day + ("" if span == " 00:00" else span))
    if due:
        # 올해가 아니면 연도까지 (연도 없는 날짜는 올해/내년으로 짐작하므로)
        day = f"@{due:%m-%d}" if due.year == now().year else f"@{due:%Y-%m-%d}"
        parts.append(day + ("" if (due.hour, due.minute) == (23, 59) else f" {due:%H:%M}"))
    if minutes and not slot_end:  # 할 시간이 있으면 길이는 거기서 나온다
        parts.append(f"~{minutes}m")
    if course:
        parts.append("#" + "_".join(course.split()))
    if every:
        parts.append("매주:" + ",".join(KO_DAYS[d] for d in sorted(set(every))))
    return " ".join(parts)


def _insert(section, line):
    """section 맨 위(제목과 바로 아래 주석 다음)에 한 줄 넣는다. 섹션이 없으면 끝에 만든다."""
    lines = PATH.read_text(encoding="utf-8").splitlines() if PATH.exists() else TEMPLATE.splitlines()
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
    PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


RE_DUE_WORD = re.compile(r"@(오늘|내일|모레|[월화수목금토일])(?:요일)?(?:\s+(\d{1,2})(?::(\d{2})|시))?")
RE_HOUR_SI = re.compile(r"(@\d{1,2}-\d{1,2}\s+)(\d{1,2})시")


RE_SLOT_IN = re.compile(r"(?<!\S)>(오늘|내일|모레|[월화수목금토일](?:요일)?|(?:\d{4}-)?\d{1,2}-\d{1,2})"
                        r"(?:\s+(\d{1,2})(?::(\d{2}))?시?(?:\s*-\s*(\d{1,2})(?::(\d{2}))?시?)?)?(?!\S)")


def _day_word(w, today):
    w = w.replace("요일", "")
    if w in ("오늘", "내일", "모레"):
        return today + timedelta(days=("오늘", "내일", "모레").index(w))
    return today + timedelta(days=(DAY_MAP[w] - today.weekday()) % 7)


def quick_line(text, today=None):
    """빠른 입력 한 줄 → inbox 줄. '@내일 18시', '@금' 같은 말은 날짜로 바꿔 적는다
    (inbox 에 '내일'을 그대로 두면 날이 바뀔 때 뜻이 달라지므로).
    할 시간: '>내일 15-18시', '>수 15:30-17:00', '>11-17 15시' (시작만 = 이때부터)."""
    today = today or now().date()

    def word_to_date(m):
        w, hh, mm = m.groups()
        d = _day_word(w, today)
        out = f"@{d:%m-%d}"
        return out + (f" {int(hh):02d}:{mm or '00'}" if hh else "")

    def slot(m):
        w, sh, sm, eh, em = m.groups()
        d = _day_word(w, today) if not w[0].isdigit() else None
        out = ">" + (f"{d:%m-%d}" if d else w)
        if sh:
            out += f" {int(sh):02d}:{sm or '00'}"
            if eh:
                out += f"-{int(eh):02d}:{em or '00'}"
        return out

    text = RE_SLOT_IN.sub(slot, text)
    text = RE_HOUR_SI.sub(lambda m: f"{m.group(1)}{int(m.group(2)):02d}:00", RE_DUE_WORD.sub(word_to_date, text))
    it = parse_line(text, today, None)
    return format_line(it["title"], it["due"], it["minutes"], it["course"], it["every"], it["earliest"], it["slot_end"])


def add_task(**fields):
    return add_task_line(format_line(**fields))


def add_task_line(line):
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
        lines = PATH.read_text(encoding="utf-8").splitlines()
        i = _todo_line_index(lines, key[2:])
        if i is not None:
            lines[i] = re.sub(r"\[ \]", "[x]", lines[i], count=1)
            PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    _insert("done", f"- {key}")


def undone(conn, key):
    """완료 되돌리기 (대시보드 [되돌리기]): inbox 할 일이면 체크를 풀고, 그 밖은 ## 완료 의 그 줄을 지운 뒤 다시 '열림'으로."""
    lines = PATH.read_text(encoding="utf-8").splitlines()
    if key.startswith("i:") and "@" not in key:
        i = _todo_line_index(lines, key[2:])
        if i is not None and "[x]" in lines[i].lower():
            lines[i] = re.sub(r"\[[xX]\]", "[ ]", lines[i], count=1)
            PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        section = "todo"
        for i, line in enumerate(lines):
            if line.startswith("#"):
                section = "done" if "완료" in line else "ignore" if "제외" in line else "todo"
                continue
            m = RE_BULLET.match(line)
            if section == "done" and m and m.group(1).strip().strip("`") == key:
                del lines[i]
                PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
                break
    db.set_status(conn, key, "open", "user")
    conn.commit()


def ignore(key):
    _insert("ignore", f"- {key}")


def ignore_like(conn, key):
    """이 과제와 같은 이름이면 앞으로 생길 것도 계속 제외 — '과목 제목' 단어로 적는다."""
    row = conn.execute("SELECT course, title FROM tasks WHERE key = ?", (key,)).fetchone()
    if not row:
        raise ValueError("할 일을 찾지 못함")
    text = " ".join(f"{short_course(row['course'])} {row['title']}".split())
    _insert("ignore", f"- {text}")
    return text


def keep(key):
    """단어 제외 규칙에 걸린 과제 하나를 계속 보이게 ('!키' 예외)."""
    _insert("ignore", f"- !{key}")


def unignore(text):
    """## 제외 칸에서 그 줄을 지운다 (키든 단어든). 다음 반영 때 다시 나타난다."""
    lines = PATH.read_text(encoding="utf-8").splitlines()
    section, in_comment, hit = "todo", False, None
    for i, line in enumerate(lines):
        if in_comment or line.lstrip().startswith("<!--"):
            in_comment = "-->" not in line
            continue
        if line.startswith("#"):
            section = "done" if "완료" in line else "ignore" if "제외" in line else "todo"
            continue
        m = RE_BULLET.match(line)
        if section == "ignore" and m and m.group(1).strip().strip("`") == text:
            hit = i
            break
    if hit is None:
        raise ValueError("제외 목록에 없는 항목")
    del lines[hit]
    PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def excluded(conn):
    """대시보드용: ## 제외 의 각 줄과 그 줄에 걸린 과제들."""
    out = []
    for _, _, text in read_sections()["ignore"]:
        keys = match(conn, text, ("open", "ignored", "done"))
        titles = [r["title"] for k in keys[:5] if (r := conn.execute("SELECT title FROM tasks WHERE key = ?", (k,)).fetchone())]
        if text.startswith("!"):  # 예외 줄
            row = conn.execute("SELECT title FROM tasks WHERE key = ?", (text[1:],)).fetchone()
            out.append({"text": text, "keep": True, "pattern": False, "count": 1, "titles": [row["title"]] if row else []})
            continue
        out.append({"text": text, "pattern": not KEYLIKE.fullmatch(text), "count": len(keys), "titles": titles})
    return out


def set_due(key, due):
    """기한 없는 inbox 할 일에 마감을 붙인다 (예: 💭 하고 싶은 일 → 오늘 하기)."""
    lines = PATH.read_text(encoding="utf-8").splitlines()
    i = _todo_line_index(lines, key[2:]) if key.startswith("i:") else None
    if i is None:
        raise ValueError("inbox 에 없는 항목")
    it = parse_line(RE_CHECK.match(lines[i]).group(2), now().date(), None)
    lines[i] = format_line(it["title"], due, it["minutes"], it["course"], None)
    PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_slot(key, start, end):
    """inbox 할 일의 '할 시간'(>…)을 바꾸거나(start·end) 지운다(None). 마감·길이·과목·반복은 그대로."""
    lines = PATH.read_text(encoding="utf-8").splitlines()
    i = _todo_line_index(lines, key[2:]) if key.startswith("i:") else None
    if i is None:
        raise ValueError("inbox 에 없는 항목")
    it = parse_line(RE_CHECK.match(lines[i]).group(2), now().date(), None)
    if start and end - start > timedelta(hours=24):
        raise ValueError("할 시간은 하루 안에서")
    minutes = it["minutes"] if start or not it["slot_end"] else int((it["slot_end"] - it["earliest"]).total_seconds() // 60)
    lines[i] = format_line(it["title"], it["due"], minutes, it["course"], it["every"], start, end)
    PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def add_habit(text):
    """'## 습관' 에 한 줄 (pa/habits.py 문법). 잘못된 줄은 ValueError."""
    from pa import habits
    h = habits.parse(text)
    _insert("habit", "- " + " ".join(text.split()))
    return f"습관 추가: {h['title']}"


def remove(key):
    """inbox 에 직접 쓴 할 일 줄을 지운다."""
    lines = PATH.read_text(encoding="utf-8").splitlines()
    i = _todo_line_index(lines, key[2:]) if key.startswith("i:") else None
    if i is None:
        raise ValueError("inbox 에 없는 항목")
    del lines[i]
    PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
        PATH.write_text(TEMPLATE, encoding="utf-8")
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
        items.append({**base, "key": key, "due": it["due"].isoformat() if it["due"] else None,
                      "earliest": it["earliest"].isoformat() if it["earliest"] else None,
                      "slot_end": it["slot_end"].isoformat() if it["slot_end"] else None})
        if it["due"] and RE_EXAM.search(it["title"]) and not is_checked:
            items += exam_reviews(key, base, it["due"], cfg, now())
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

    # ## 제외 — 여기 있는 동안만 제외. '!키' 줄은 예외 (단어 규칙에 걸려도 계속 보이게)
    ignore_keys, keep, by_rule = set(), set(), {}
    for no, _, text in sections["ignore"]:
        if text.startswith("!"):
            keep.add(text[1:].strip())
            continue
        keys = match(conn, text, ("open", "ignored"))
        is_key = bool(KEYLIKE.fullmatch(text))
        if not keys and is_key:  # 단어 규칙은 앞으로 생길 과제를 위한 것이라 지금 없어도 괜찮다
            warnings.append(f"inbox.md {no}번째 줄 '{text}' 에 맞는 항목 없음")
        for k in keys:
            ignore_keys.add(k)
            if not is_key:
                by_rule.setdefault(k, text)
    ignore_keys -= keep
    for k in ignore_keys:
        # 단어 규칙이 '새로' 숨긴 과제는 기록해서 알려 준다 (모르고 놓치지 않게)
        if db.set_status(conn, k, "ignored", "inbox") and k in by_rule:
            db.log(conn, "rule_hidden", k, rule=by_rule[k])
    for r in conn.execute("SELECT key FROM tasks WHERE status = 'ignored' AND status_by = 'inbox'").fetchall():
        if r["key"] not in ignore_keys:
            db.set_status(conn, r["key"], "open", "inbox")

    db.set_meta(conn, "inbox_warnings", "\n".join(warnings))
    conn.commit()
    return warnings
