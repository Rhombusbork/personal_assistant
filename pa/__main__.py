"""비서 명령 모음. 프로젝트 폴더에서 `bin/pa <명령>` 으로 실행한다.

  bin/pa list                 남은 할 일 (마감 순, 맨 앞이 키)
  bin/pa sync                 Canvas 확인 → 저장소 반영
  bin/pa plan [--dry-run]     학습 계획 → '학습 계획' 캘린더
  bin/pa done <키>            완료 표시
  bin/pa ignore <키>          계속 제외 / unignore 로 되돌리기
  bin/pa time <키> <분>       예상 소요 시간 조정
  bin/pa lectures [과목] [--open N]   이번 주 강의 목록·열기
"""
import argparse
import sys

from pa import collect_canvas, db, plan
from pa.model import KIND_LABEL, fmt, kday, label


def cmd_list(conn, args):
    for t in db.tasks(conn, "status = 'open' AND due IS NOT NULL AND due >= ?", (plan.now().isoformat(),)):
        print(fmt(t))


def cmd_sync(conn, args):
    n = collect_canvas.sync(conn)
    conn.commit()
    print(f"Canvas 확인: {n}건")


def cmd_plan(conn, args):
    result, failed = plan.run(conn, write=not args.dry_run)
    day = None
    for t, s, e in result:
        if s.date() != day:
            day = s.date()
            print(f"\n📅 {kday(s)}")
        print(f"  {s:%H:%M}–{e:%H:%M}  [{KIND_LABEL[t.kind]}] {label(t)}  (마감 {kday(t.due)} {t.due:%H:%M})")
    for t in failed:
        print(f"\n⚠️ 마감 전 빈 시간 부족: {fmt(t).strip()}")
    print("\n(미리보기 — 캘린더는 그대로)" if args.dry_run else f"\n✅ 계획 {len(result)}건 반영")


def cmd_status(status):
    def run(conn, args):
        if db.set_status(conn, args.key, status, "cli"):
            conn.commit()
            print(f"{args.key} → {status}")
        else:
            print(f"{args.key}: 없는 키이거나 이미 {status} 상태입니다.")
    return run


def cmd_time(conn, args):
    conn.execute("UPDATE tasks SET minutes_override = ? WHERE key = ?", (args.minutes, args.key))
    conn.commit()
    print(f"{args.key} → {args.minutes}분")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "lectures":
        from pa import lectures
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return lectures.main()

    p = argparse.ArgumentParser(prog="pa", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("sync").set_defaults(fn=cmd_sync)
    sp = sub.add_parser("plan")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(fn=cmd_plan)
    for name, status in (("done", "done"), ("ignore", "ignored"), ("unignore", "open")):
        sp = sub.add_parser(name)
        sp.add_argument("key")
        sp.set_defaults(fn=cmd_status(status))
    sp = sub.add_parser("time")
    sp.add_argument("key")
    sp.add_argument("minutes", type=int)
    sp.set_defaults(fn=cmd_time)
    sub.add_parser("lectures", help="이번 주 강의 목록·열기")

    args = p.parse_args()
    conn = db.connect()
    args.fn(conn, args)


if __name__ == "__main__":
    main()
