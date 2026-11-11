"""온라인 수업의 이번 주차 강의 목록을 보여주고, 브라우저로 열어준다.

사용법:
  python -m pa.lectures              # 온라인 수업 전체의 이번 주차 항목
  python -m pa.lectures 생약 --week 10
  python -m pa.lectures 생약 --open 1  # 1번 항목을 Windows 브라우저로 열기
"""
import argparse
import re
import subprocess
from datetime import date

from pa import canvas
from pa.config import load_timetable

TYPE_LABEL = {"ExternalTool": "강의", "Quiz": "퀴즈", "Assignment": "과제", "Discussion": "토론", "File": "파일"}


def current_week(sem_start):
    return (date.today() - sem_start).days // 7 + 1


def week_items(course, week):
    modules = canvas.get(f"/courses/{course['id']}/modules", **{"include[]": "items"})
    for m in modules:
        match = re.match(r"(\d+)주차", m["name"])
        if match and int(match.group(1)) == week:
            return m["name"], m.get("items", [])
    return None, []


def open_in_browser(url):
    # WSL 에서 Windows 기본 브라우저로 연다 (이미 로그인된 세션 사용)
    subprocess.run(["explorer.exe", url], check=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("course", nargs="?", help="과목명 일부 (생략 시 온라인 수업 전체)")
    parser.add_argument("--week", type=int, help="주차 (기본: 이번 주)")
    parser.add_argument("--open", type=int, metavar="N", help="N번 항목을 브라우저로 열기")
    args = parser.parse_args()

    tt = load_timetable()
    week = args.week or current_week(date.fromisoformat(tt["semester_start"]))
    names = [args.course] if args.course else tt.get("online_classes", [])
    courses = [c for c in canvas.active_courses() if any(n in c["name"] for n in names)]
    if not courses:
        raise SystemExit(f"'{args.course}' 과목을 찾지 못했습니다.")

    if args.open:
        if len(courses) != 1:
            raise SystemExit("--open 은 과목을 하나로 지정해야 합니다.")
        _, items = week_items(courses[0], week)
        items = [i for i in items if i.get("html_url")]
        if not 1 <= args.open <= len(items):
            raise SystemExit("번호가 범위를 벗어났습니다.")
        print("열기:", items[args.open - 1]["title"])
        open_in_browser(items[args.open - 1]["html_url"])
        return

    for c in courses:
        title, items = week_items(c, week)
        print(f"\n📘 {c['name']} — {title or f'{week}주차 없음'}")
        for n, i in enumerate((i for i in items if i.get("html_url")), 1):
            print(f"  {n}. [{TYPE_LABEL.get(i['type'], i['type'])}] {i['title']}")


if __name__ == "__main__":
    main()
