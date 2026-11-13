"""Canvas 에서 온라인 강의·퀴즈·과제를 읽어 저장소에 반영한다.

- 과제·퀴즈: 마감이 있는 것 (지난 7일 이내 마감 포함). 제출했으면 자동 완료 처리.
- 강의: 온라인 수업의 이번 주·다음 주 강의 영상 (배포용 자료는 제외).
"""
import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path

from pa import canvas, db, links, materials
from pa.config import load_timetable
from pa.model import KST, now, parse_dt

SKIP_TYPES = {"none", "on_paper", "not_graded", "wiki_page"}
MATERIAL = re.compile(r"배포용|handout|\[강의자료\]", re.I)


def lecture_deadline(module_name, week, sem_start):
    """모듈명 끝의 마지막 'MM/DD(요일) HH:MM' 을 출석 마감으로 본다. 없으면 해당 주 시작+6일 23:59."""
    found = re.findall(r"(\d{1,2})/(\d{1,2})\([^)]*\)\s*(\d{1,2}):(\d{2})", module_name)
    if found:
        mo, d, h, mi = map(int, found[-1])
        return datetime(sem_start.year, mo, d, h, mi, tzinfo=KST)
    end = sem_start + timedelta(days=(week - 1) * 7 + 6)
    return datetime.combine(end, time(23, 59), KST)


pairs_found = []
pair_candidates = {}  # 짝을 못 정한 강의 → 같은 주차 자료 후보 (📄 추천용)


def collect():
    pairs_found.clear()
    pair_candidates.clear()
    tt = load_timetable()
    minutes = tt["planner"]["minutes"]
    sem_start = date.fromisoformat(tt["semester_start"])
    t_now = now()
    this_week = (t_now.date() - sem_start).days // 7 + 1
    online = tt.get("online_classes", [])
    items = []

    for c in canvas.active_courses():
        cname = c["name"]
        for a in canvas.get(f"/courses/{c['id']}/assignments", **{"include[]": "submission"}):
            due = parse_dt(a.get("due_at"))
            if not due or due < t_now - timedelta(days=7) or SKIP_TYPES & set(a.get("submission_types", [])):
                continue
            sub = a.get("submission") or {}
            kind = "quiz" if a.get("quiz_id") else "assignment"
            items.append({
                "key": f"a{a['id']}", "kind": kind, "course": cname, "title": a["name"].strip(),
                "due": due.isoformat(), "earliest": None, "minutes": minutes[kind],
                "url": a.get("html_url", ""),
                "done": bool(sub.get("submitted_at") or sub.get("workflow_state") in ("submitted", "graded")),
            })

        if not any(n in cname for n in online):
            continue
        lec_start = len(items)
        dirs = materials.course_dirs(cname)
        local = [x["p"] for x in links.index() if dirs and x["p"].startswith(str(dirs[0]) + "/")]
        local_names = {links.norm_title(Path(f).stem) for f in local}
        for m in canvas.get(f"/courses/{c['id']}/modules", **{"include[]": "items"}):
            if local:  # 같은 주차의 강의 ↔ 자료 짝 (모든 주차, 이미 받은 파일 기준)
                pairs_found.extend(links.find_pairs(m.get("items", []), local, pair_candidates))
            wk = re.match(r"(\d+)주차", m["name"])
            if not wk or not this_week <= int(wk.group(1)) <= this_week + 1:
                continue
            due = lecture_deadline(m["name"], int(wk.group(1)), sem_start)
            for i in m.get("items", []):
                if i["type"] != "ExternalTool" or MATERIAL.search(i["title"]):
                    continue
                if links.norm_title(i["title"]) in local_names:  # 이미 받은 자료와 이름이 같음 → 강의가 아니라 자료
                    not_lectures.add(f"m{i['id']}")             # (LearningX 로그인이 끊겨도 자료를 강의로 잘못 올리지 않게)
                    continue
                items.append({
                    "key": f"m{i['id']}", "kind": "lecture", "course": cname, "title": i["title"].strip(),
                    "due": due.isoformat(), "earliest": None, "minutes": minutes["lecture"],
                    "url": i.get("html_url", ""),
                })
        enrich_lectures(items, lec_start, c, t_now)
    return items


def enrich_lectures(items, start, course, t_now):
    """LearningX 데이터로 강의 항목을 정확하게: 실제 출석 마감·영상 길이·수강 완료.
    지난 주차라도 아직 안 들었고 지각 수강 기간이 남은 강의는 추가한다. 실패하면 그대로 둔다."""
    from pa import learningx
    try:
        info = learningx.lecture_info(course["id"])
        learningx_errors.pop(course["name"], None)
    except Exception as e:
        learningx_errors[course["name"]] = str(e)
        return
    seen = set()
    for it in list(items[start:]):
        x = info.get(it["key"])
        if not x:
            continue
        if x.get("file"):  # 강의가 아니라 자료(슬라이드 PDF) → 할 일에서 뺀다
            items.remove(it)
            not_lectures.add(it["key"])
            continue
        seen.add(it["key"])
        if x["due"]:
            it["due"] = parse_dt(x["due"]).isoformat()
        if x["minutes"]:
            it["minutes"] = x["minutes"]
        it["done"] = x["done"]
    for key, x in info.items():
        if key in seen or x.get("file") or x["done"]:
            continue
        due, late = parse_dt(x["due"]), parse_dt(x["late"])
        if due and due >= t_now:
            pass
        elif late and late >= t_now:
            due = late  # 출석 마감은 지났지만 지각 수강 가능
        else:
            continue
        items.append({"key": key, "kind": "lecture", "course": course["name"],
                      "title": x["title"] + (" (지각 수강)" if due == late else ""), "due": due.isoformat(),
                      "earliest": None, "minutes": x["minutes"] or 50,
                      "url": f"https://canvas.jejunu.ac.kr/courses/{course['id']}/modules/items/{key[1:]}"})


learningx_errors = {}
not_lectures = set()  # LearningX 가 '자료'라고 알려 준 Canvas 항목


def sync(conn):
    items = collect()
    db.sync_source(conn, "canvas", items)
    n = links.save_pairs(conn, pairs_found)
    db.set_meta(conn, "pair_candidates", json.dumps(pair_candidates, ensure_ascii=False))
    if n:
        db.log(conn, "pairs_added", None, count=n)
    for key in not_lectures:
        db.set_status(conn, key, "gone", "auto")
    db.set_meta(conn, "learningx_lecture_error", "; ".join(f"{k}: {v}" for k, v in learningx_errors.items()))
    db.set_meta(conn, "canvas_synced_at", now().isoformat())
    return len(items)


def online_courses():
    online = load_timetable().get("online_classes", [])
    return [c for c in canvas.active_courses() if any(n in c["name"] for n in online)]


def sync_notices(conn, courses=None):
    """이번 학기 공지 중 처음 보는 것을 '새 공지'로 저장. 처음 실행 때는 지난 공지를 모두 읽음으로 둔다."""
    import html as htmlmod
    courses = courses or canvas.active_courses()
    names = {f"course_{c['id']}": c["name"] for c in courses}
    first_time = conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0] == 0
    rows = canvas.get("/announcements", **{"context_codes[]": list(names), "start_date": load_timetable()["semester_start"]})
    new = 0
    for a in rows:
        if conn.execute("SELECT 1 FROM notices WHERE id = ?", (str(a["id"]),)).fetchone():
            continue
        text = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", a.get("message") or "")
        text = re.sub(r"\n{3,}", "\n\n", htmlmod.unescape(re.sub(r"<[^>]+>", "", text))).strip()
        conn.execute("INSERT INTO notices (id, course, title, text, posted_at, url, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (str(a["id"]), names.get(a["context_code"], ""), a["title"], text[:4000],
                      a.get("posted_at") or a.get("delayed_post_at") or a.get("created_at") or now().isoformat(),
                      a.get("html_url", ""), "read" if first_time else "new"))
        if not first_time:
            db.log(conn, "notice_new", None, title=a["title"])
            new += 1
    conn.commit()
    return new
