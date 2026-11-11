"""Canvas 에서 해야 할 항목(온라인 강의, 퀴즈, 과제)을 모으고 관리한다.

사용법:
  python -m pa.tasks                    # 남은 항목 목록 (마감 순)
  python -m pa.tasks ignore <키>         # 제외 (조장만 제출 등) — 이후 계속 무시
  python -m pa.tasks unignore <키>
  python -m pa.tasks done <키>           # 강의 수강 완료 표시 (과제·퀴즈는 제출하면 자동 제외)
  python -m pa.tasks time <키> <분>      # 예상 소요 시간 조정
  python -m pa.tasks ignored            # 제외 목록 보기
"""
import argparse
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from pa import canvas, state
from pa.config import load_timetable

KST = timezone(timedelta(hours=9))
SKIP_TYPES = {"none", "on_paper", "not_graded", "wiki_page"}
MATERIAL = re.compile(r"배포용|handout|\[강의자료\]", re.I)


@dataclass
class Task:
    key: str
    kind: str  # lecture | quiz | assignment
    course: str
    title: str
    due: datetime
    minutes: int
    url: str


def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(KST) if s else None


def lecture_deadline(module_name, week, sem_start):
    """모듈명 끝의 마지막 'MM/DD(요일) HH:MM' 을 출석 마감으로 본다. 없으면 해당 주 시작+6일 23:59."""
    found = re.findall(r"(\d{1,2})/(\d{1,2})\([^)]*\)\s*(\d{1,2}):(\d{2})", module_name)
    if found:
        mo, d, h, mi = map(int, found[-1])
        return datetime(sem_start.year, mo, d, h, mi, tzinfo=KST)
    end = sem_start + timedelta(days=(week - 1) * 7 + 6)
    return datetime.combine(end, time(23, 59), KST)


def collect(include_hidden=False):
    tt = load_timetable()
    cfg = tt["planner"]
    st = state.load()
    sem_start = date.fromisoformat(tt["semester_start"])
    now = datetime.now(KST)
    horizon = now + timedelta(days=cfg["horizon_days"])
    this_week = (now.date() - sem_start).days // 7 + 1
    online = tt.get("online_classes", [])
    tasks = []

    for c in canvas.active_courses():
        cname = c["name"]
        for a in canvas.get(f"/courses/{c['id']}/assignments", **{"include[]": "submission"}):
            due = parse_dt(a.get("due_at"))
            sub = a.get("submission") or {}
            if (not due or due < now or due > horizon or a.get("locked_for_user")
                    or SKIP_TYPES & set(a.get("submission_types", []))
                    or sub.get("submitted_at") or sub.get("workflow_state") in ("submitted", "graded")):
                continue
            kind = "quiz" if a.get("quiz_id") else "assignment"
            tasks.append(Task(f"a{a['id']}", kind, cname, a["name"], due,
                              cfg["minutes"][kind], a.get("html_url", "")))

        if not any(n in cname for n in online):
            continue
        for m in canvas.get(f"/courses/{c['id']}/modules", **{"include[]": "items"}):
            wk = re.match(r"(\d+)주차", m["name"])
            if not wk or not this_week <= int(wk.group(1)) <= this_week + 1:
                continue
            due = lecture_deadline(m["name"], int(wk.group(1)), sem_start)
            if due < now or due > horizon:
                continue
            for i in m.get("items", []):
                if i["type"] != "ExternalTool" or MATERIAL.search(i["title"]):
                    continue
                tasks.append(Task(f"m{i['id']}", "lecture", cname, i["title"].strip(), due,
                                  cfg["minutes"]["lecture"], i.get("html_url", "")))

    for t in tasks:
        t.minutes = st["minutes"].get(t.key, t.minutes)
    if not include_hidden:
        tasks = [t for t in tasks if t.key not in st["ignored"] and t.key not in st["done"]]
    return sorted(tasks, key=lambda t: t.due)


KIND_LABEL = {"lecture": "강의", "quiz": "퀴즈", "assignment": "과제"}


def short_course(name):
    return re.sub(r"\s*\d{6}$", "", name)


WEEKDAY = "월화수목금토일"


def kday(dt):
    return f"{dt:%m/%d}({WEEKDAY[dt.weekday()]})"


def fmt(t):
    return (f"{t.key:>10}  {kday(t.due)} {t.due:%H:%M}  [{KIND_LABEL[t.kind]}] "
            f"{short_course(t.course)} · {t.title}  ({t.minutes}분)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", nargs="?", default="list",
                   choices=["list", "ignore", "unignore", "done", "time", "ignored"])
    p.add_argument("key", nargs="?")
    p.add_argument("minutes", nargs="?", type=int)
    args = p.parse_args()
    st = state.load()

    if args.cmd == "list":
        for t in collect():
            print(fmt(t))
        return
    if args.cmd == "ignored":
        for k, title in st["ignored"].items():
            print(f"{k:>10}  {title}")
        return
    if not args.key:
        raise SystemExit("키를 지정하세요 (목록 맨 앞의 a123 / m456 같은 값).")
    if args.cmd == "unignore":
        st["ignored"].pop(args.key, None)
    else:
        found = {t.key: t for t in collect(include_hidden=True)}
        label = fmt(found[args.key]).strip() if args.key in found else args.key
        if args.cmd == "ignore":
            st["ignored"][args.key] = label
        elif args.cmd == "done":
            st["done"][args.key] = label
        elif args.cmd == "time":
            if not args.minutes:
                raise SystemExit("분을 지정하세요.")
            st["minutes"][args.key] = args.minutes
    state.save(st)
    print(f"{args.cmd}: {args.key}")


if __name__ == "__main__":
    main()
