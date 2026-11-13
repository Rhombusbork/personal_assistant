"""비서 명령 모음. 프로젝트 폴더에서 `bin/pa <명령>` 으로 실행한다.

  bin/pa watch                자동 감시 (VSCode 를 열면 자동 실행)
  bin/pa run [--full]         한 번 실행: inbox → (Canvas) → 계획 → TODAY.md
  bin/pa today                TODAY.md 다시 만들고 출력
  bin/pa list                 남은 할 일 (마감 순, 맨 앞이 키)
  bin/pa sync                 Canvas 확인 → 저장소 반영
  bin/pa inbox                inbox.md → 저장소 반영
  bin/pa plan [--dry-run]     학습 계획 → '학습 계획' 캘린더
  bin/pa done <키>            완료 표시
  bin/pa ignore <키>          계속 제외 / unignore 로 되돌리기
  bin/pa time <키> <분>       예상 소요 시간 조정
  bin/pa task <키>            할 일 하나: 마감·주소·Canvas 과제 설명·보고서 파일·연결된 자료 (채팅 작업용)
  bin/pa notices [--all]      새 공지 (읽지 않은 것; --all 은 최근 2주 전부) — 본문 앞부분과 🤖 요약
  bin/pa links [키]           연결된 자료 (키 없이: 자료가 연결된 할 일 전부)
  bin/pa link <키> <파일>...  자료 연결 (config/materials.yaml 범위 안, 최대 max_links) / unlink 로 빼기
  bin/pa lectures [과목] [--open N]   이번 주 강의 목록·열기
  bin/pa browser login | probe <과목> <제목>   로그인 브라우저 (자료 다운로드 시험)
  bin/pa google-login         Google Calendar 다시 로그인 (Windows 브라우저가 열림)
"""
import argparse
import sys

from pa import collect_canvas, db, inbox, pipeline, plan, render
from pa.model import KIND_LABEL, fmt, kday, label


def cmd_list(conn, args):
    for t in db.tasks(conn, "status = 'open' AND due IS NOT NULL AND due >= ?", (plan.now().isoformat(),)):
        print(fmt(t))


def cmd_sync(conn, args):
    n = collect_canvas.sync(conn)
    conn.commit()
    print(f"Canvas 확인: {n}건")


def cmd_inbox(conn, args):
    warnings = inbox.sync(conn)
    print("inbox.md 반영 완료" + "".join(f"\n⚠️ {w}" for w in warnings))


def cmd_run(conn, args):
    pipeline.run(full=args.full)


def cmd_watch(conn, args):
    pipeline.watch()


def cmd_today(conn, args):
    render.write(conn)
    print(render.TODAY_PATH.read_text())


def cmd_dashboard_check(conn, args):
    """VSCode 작업용: 엔진 서버가 뜰 때까지 기다린 뒤, 대시보드가 이미 열려 있으면 실패(→ 열기 건너뜀)."""
    import json as _json
    import time as _time
    import urllib.request
    base = "http://localhost:8765"
    for _ in range(90):
        try:
            urllib.request.urlopen(base + "/", timeout=2)
            break
        except OSError:
            _time.sleep(1)
    else:
        print("대시보드 서버가 뜨지 않았습니다 (아래 '비서: 자동 감시' 확인)")
        sys.exit(1)
    # 다시 연 창에서 복원된 대시보드 탭이 신호를 보낼 시간을 잠깐 준다
    for _ in range(8):
        n = _json.loads(urllib.request.urlopen(base + "/api/viewers", timeout=2).read())["count"]
        if n:
            print(f"대시보드가 이미 열려 있음 ({n}개) — 새로 열지 않음")
            sys.exit(3)
        _time.sleep(1)
    print("대시보드 열기")


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


def cmd_task(conn, args):
    from pa import jobs, links
    row = conn.execute("SELECT * FROM tasks WHERE key = ?", (args.key,)).fetchone()
    if not row:
        sys.exit("할 일을 찾지 못함 — bin/pa list 의 맨 앞이 키")
    t = dict(row)
    print(f"{t['title']}\n  종류 {KIND_LABEL.get(t['kind'], t['kind'])} · 과목 {t['course'] or '-'} · 상태 {t['status']}"
          f" · 마감 {t['due'] or '없음'}\n  {t['url'] or ''}".rstrip())
    if t["kind"] in ("assignment", "todo") and t["due"]:
        path = jobs.report_path(t)
        print(f"보고서 파일: {path}" + (" (있음)" if path.exists() else " (아직 없음)"))
    if t["kind"] == "assignment":
        try:
            print("\n[Canvas 과제 설명]\n" + (jobs.assignment_text(t) or "(설명 없음)"))
        except Exception as e:
            print(f"\n[Canvas 과제 설명] 읽지 못함: {e}")
    files = links.get(conn, args.key)
    print("\n[연결된 자료]" + ("" if files else " 없음 — 📄 자료 창에서 고르거나 bin/pa link"))
    for x in files:
        print(("  ⚠️ 파일 없음 " if not x["exists"] else "  ") + x["p"])


def cmd_notices(conn, args):
    from datetime import timedelta

    from pa.model import short_course
    where, params = ("posted_at >= ?", ((plan.now() - timedelta(days=14)).isoformat(),)) if args.all else ("status = 'new'", ())
    rows = conn.execute(f"SELECT * FROM notices WHERE {where} ORDER BY posted_at DESC", params).fetchall()
    for n in rows:
        print(f"[{n['posted_at'][:10]}] {short_course(n['course'])} · {n['title']}" + ("" if n["status"] == "new" else " (읽음)"))
        if n["summary"]:
            print(f"  🤖 {n['summary']}")
        print("  " + " ".join(n["text"].split())[:300])
    if not rows:
        print("새 공지 없음" if not args.all else "최근 2주 공지 없음")


def cmd_links(conn, args):
    from pa import links
    if args.key:
        rows = links.get(conn, args.key)
        for x in rows:
            print(("⚠️ 파일 없음  " if not x["exists"] else "") + x["p"] + ("  (강의 짝)" if x["origin"] == "pair" else ""))
        if not rows:
            print("연결된 자료 없음")
        return
    titles = {r["key"]: r["title"] for r in conn.execute("SELECT key, title FROM tasks WHERE status = 'open'")}
    for key, names in sorted(links.summary_map(conn, set(titles)).items()):
        print(f"{key}  {titles[key]}  📎{len(names)}: {', '.join(names)}")


def cmd_link(conn, args):
    from pathlib import Path

    from pa import links
    for f in args.files:
        try:
            if args.cmd == "link":
                links.add(conn, args.key, f)
            else:
                links.remove(conn, args.key, str(Path(f).resolve()))
        except ValueError as e:
            sys.exit(f"{f}: {e}")
        print(("연결: " if args.cmd == "link" else "뺌: ") + f)


def cmd_time(conn, args):
    conn.execute("UPDATE tasks SET minutes_override = ? WHERE key = ?", (args.minutes, args.key))
    conn.commit()
    print(f"{args.key} → {args.minutes}분")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "google-login":
        from pa import gcal
        return gcal.login()
    if len(sys.argv) > 1 and sys.argv[1] == "browser":
        from pa import browser
        return browser.main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "lectures":
        from pa import lectures
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return lectures.main()

    p = argparse.ArgumentParser(prog="pa", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("sync").set_defaults(fn=cmd_sync)
    sub.add_parser("inbox").set_defaults(fn=cmd_inbox)
    sp = sub.add_parser("run")
    sp.add_argument("--full", action="store_true", help="Canvas·과제 캘린더까지")
    sp.set_defaults(fn=cmd_run)
    sub.add_parser("watch").set_defaults(fn=cmd_watch)
    sub.add_parser("today").set_defaults(fn=cmd_today)
    sub.add_parser("dashboard-check").set_defaults(fn=cmd_dashboard_check)
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
    sp = sub.add_parser("notices")
    sp.add_argument("--all", action="store_true")
    sp.set_defaults(fn=cmd_notices)
    sp = sub.add_parser("task")
    sp.add_argument("key")
    sp.set_defaults(fn=cmd_task)
    sp = sub.add_parser("links")
    sp.add_argument("key", nargs="?")
    sp.set_defaults(fn=cmd_links)
    for name in ("link", "unlink"):
        sp = sub.add_parser(name)
        sp.add_argument("key")
        sp.add_argument("files", nargs="+")
        sp.set_defaults(fn=cmd_link)

    args = p.parse_args()
    conn = db.connect()
    args.fn(conn, args)


if __name__ == "__main__":
    main()
