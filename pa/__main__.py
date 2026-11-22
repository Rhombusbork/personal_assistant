"""비서 명령 모음. 프로젝트 폴더에서 `bin/pa <명령>` 으로 실행한다 (Windows 는 `bin\\pa.cmd <명령>`).

  bin/pa watch                자동 감시 (VSCode 를 열면 자동 실행)
  bin/pa run [--full]         한 번 실행: inbox → (Canvas) → 계획 → TODAY.md
  bin/pa today                TODAY.md 다시 만들고 출력
  bin/pa pull                 내 git 저장소를 GitHub 과 대조해 내려받기 (엔진은 켤 때 한 번 자동)
  bin/pa peer [sync|init <주소>]   두 PC 같이 쓰기: 이 PC 가 일하는 PC 인지 대기 PC 인지 / 지금 맞추기 / 처음 연결
  bin/pa list                 남은 할 일 (마감 순, 맨 앞이 키)
  bin/pa sync                 Canvas 확인 → 저장소 반영
  bin/pa inbox                inbox.md → 저장소 반영
  bin/pa plan [--dry-run]     학습 계획 → '학습 계획' 캘린더
  bin/pa done <키>            완료 표시
  bin/pa ignore <키>          계속 제외 / unignore 로 되돌리기
  bin/pa time <키> <분>       예상 소요 시간 조정
  bin/pa quiz-help <키>|off   퀴즈 도움: 이제부터 찍은 스크린샷을 AI 에 보내 답·풀이 (퀴즈 페이지를 열면 자동으로 켜짐)
  bin/pa task <키>            할 일 하나: 마감·주소·Canvas 과제 설명·보고서 파일·연결된 자료 (채팅 작업용)
  bin/pa notices [--all]      새 공지 (읽지 않은 것; --all 은 최근 2주 전부) — 본문 앞부분과 🤖 요약
  bin/pa pdf <보고서.md>       제출용 A4 PDF 만들기 (쪽수 출력) → 탐색기에서 위치 보여 주기
  bin/pa reveal <파일>         탐색기에서 파일 위치 보기
  bin/pa links [키]           연결된 자료 (키 없이: 자료가 연결된 할 일 전부)
  bin/pa link <키> <파일>...  자료 연결 (config/materials.yaml 범위 안, 최대 max_links) / unlink 로 빼기
  bin/pa lectures [과목] [--open N]   이번 주 강의 목록·열기
  bin/pa browser login | probe <과목> <제목>   로그인 브라우저 (자료 다운로드 시험)
  bin/pa google-login         Google Calendar 다시 로그인 (브라우저가 열림)
  bin/pa sync-timetable [--dry-run]   config/timetable.yaml 의 수업 시간표 → '수업 시간표' 캘린더 (포털을 안 쓸 때만)
  bin/pa timetable [--dry-run]        학교 포털(하영드리미)의 내 시간표를 지금 읽어 대면 수업만 캘린더에 (엔진은 매주 자동)
  bin/pa open                 대시보드 열기: VSCode 안 탭 (VSCode 가 꺼져 있으면 VSCode 를 엶) 또는 앱 창 (dashboard.mode)
  bin/pa shortcut             바탕화면에 '비서' 바로가기 (누르면 VSCode 로 비서 폴더 → 엔진·대시보드 자동)
  bin/pa vscode-ext           비서 VSCode 확장 설치 (대시보드를 VSCode 안 탭으로 — 창 늘 하나·다시 열기)
"""
import argparse
import os
import sys

from pa import collect_canvas, db, inbox, pipeline, plan, render
from pa.model import KIND_LABEL, fmt, kday, label


def cmd_peer(conn, args):
    """두 PC 같이 쓰기: 상태 보기 / init <저장소 주소> (처음 한 번, .env 에 PA_STATE_REPO 를 적고 맞춤)."""
    from pa import config, peer
    if args.action == "init":
        if not args.url:
            sys.exit("bin/pa peer init <비공개 저장소 주소>  예: https://github.com/<나>/pa_state.git")
        env = config.ROOT / ".env"
        text = env.read_text(encoding="utf-8") if env.exists() else ""
        if "PA_STATE_REPO=" not in text.replace("# PA_STATE_REPO=", ""):
            env.write_text(text.rstrip("\n") + f"\nPA_STATE_REPO={args.url}\n", encoding="utf-8")
    p = peer.get()
    if not p.enabled():
        sys.exit("두 PC 같이 쓰기가 꺼져 있습니다 — bin/pa peer init <비공개 저장소 주소>")
    if args.action in ("init", "sync"):
        res = p.tick()
        for w in res.get("warnings", []):
            print(f"⚠️ {w}")
    st = p.status()
    import time as _time
    ago = f"{int((_time.time() - float(st['leader_at'])) // 60)}분 전" if st["leader_at"] else "-"
    print(f"이 PC: {st['host']} (우선순위 {st['priority']}) — {'일하는 PC' if st['leader'] else '대기 PC'}\n"
          f"일하는 PC: {st['leader_host'] or '-'} (마지막 신호 {ago}) · 보낼 입력 {st['pending']}건")


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
    from pa import peer
    if peer.standby():  # 두 PC: 대기 PC 는 고친 inbox.md 를 일하는 PC 로 보내고 화면만
        peer.get().inbox_changed()
        try:
            peer.get().tick()
        except Exception as e:
            print(f"⚠️ 저장소와 맞추지 못함: {e}")
        pipeline.run(full=False)
        print(f"대기 PC — 입력을 일하는 PC({peer.get().status()['leader_host']})로 보냈습니다. 1~2분 뒤 반영")
        return
    if args.full and _ask_engine_sync():
        print("엔진이 켜져 있어 엔진에게 최신화를 맡겼습니다 (data/pa.log)")
        return
    pipeline.run(full=args.full)


def _ask_engine_sync():
    """엔진(bin/pa watch)이 켜져 있으면 그 안에서 최신화하게 부탁한다 — 작업 스케줄러의 하루 3번 실행이
    엔진과 따로 돌며 로그인 상태를 바꾸거나 같은 일을 두 번 하지 않게. 엔진이 없으면 False."""
    import json as _json
    import urllib.request
    from pa import server
    req = urllib.request.Request(f"http://localhost:{server.PORT}/api/sync", data=b"{}", method="POST",
                                 headers={"X-PA": "1", "Content-Type": "application/json", "Host": f"localhost:{server.PORT}"})
    try:
        return bool(_json.loads(urllib.request.urlopen(req, timeout=5).read()).get("ok"))
    except (OSError, ValueError):
        return False


def cmd_watch(conn, args):
    pipeline.watch()


def cmd_pull(conn, args):
    from pa import repos
    if not repos.paths():
        print("config/repos.yaml 의 pull_on_start 가 비어 있어요")
    for _, _, msg in repos.pull_all(log=lambda m: None):
        print(msg)


def cmd_today(conn, args):
    render.write(conn)
    print(render.TODAY_PATH.read_text(encoding="utf-8"))


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


def cmd_open(conn, args):
    import urllib.request
    from pa import osutil, server
    from pa.config import ROOT
    url = f"http://localhost:{server.PORT}/"
    try:
        urllib.request.urlopen(url, timeout=3)
    except OSError:
        print("엔진이 꺼져 있습니다 — VSCode: Ctrl+Shift+P → Tasks: Run Task → '비서: 자동 감시', 또는 bin/pa watch")
        sys.exit(1)
    if pipeline.dash_mode() == "vscode":
        import json as _json
        req = urllib.request.Request(url + "api/open-request", data=b"{}", method="POST",
                                     headers={"X-PA": "1", "Content-Type": "application/json"})
        if _json.loads(urllib.request.urlopen(req, timeout=5).read()).get("vscode"):
            print("VSCode 안 탭으로 엽니다 (몇 초 안에)")
        else:
            osutil.launch_vscode(ROOT)
            print("VSCode 를 비서 폴더로 엽니다 — 대시보드는 그 안 탭으로 열립니다")
        return
    osutil.open_app(url)
    print("대시보드 창을 열었습니다:", url)


def cmd_vscode_ext(conn, args):
    from pa import vscode_ext
    name, _ = vscode_ext.install()
    print(f"설치됨: {name} — VSCode 를 열면 대시보드가 그 안 탭으로 열립니다 (이미 연 창은 몇 초 안에 적용)")


def cmd_shortcut(conn, args):
    from pa import osutil
    from pa.config import ROOT
    print("만듦:", osutil.desktop_shortcut(ROOT))


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
            from pa import peer
            action = {"done": "/api/done", "ignored": "/api/ignore"}.get(status)
            if peer.standby():  # 두 PC: 일하는 PC 에도
                if action:
                    peer.get().queue(action, {"key": args.key})
                else:
                    print("⚠️ 대기 PC 라 일하는 PC 에는 안 넘어갑니다 — 대시보드에서 하세요")
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
        path = jobs.report_path(t, conn)
        print(f"보고서 파일: {path}" + (" (있음)" if path.exists() else " (아직 없음)"))
        b = jobs.brief(conn, args.key)
        if b["text"]:
            print("✍ 창에 적은 작성 지침: " + b["text"] + ("" if b["blanks"] else " (내 생각 자리도 초안으로)"))
    if t["kind"] == "assignment":
        try:
            print("\n[Canvas 과제 설명]\n" + (jobs.assignment_text(t) or "(설명 없음)"))
        except Exception as e:
            print(f"\n[Canvas 과제 설명] 읽지 못함: {e}")
    files = links.get(conn, args.key)
    print("\n[연결된 자료]" + ("" if files else " 없음 — 📄 자료 창에서 고르거나 bin/pa link"))
    for x in files:
        print(("  ⚠️ 파일 없음 " if not x["exists"] else "  ") + x["p"])


def cmd_submit(conn, args):
    from pa import submit
    try:
        c = submit.check(conn, args.key, args.file)
    except submit.SubmitError as e:
        sys.exit(str(e))
    print(f"{c['name']}  (마감 {c['due']:%m/%d %H:%M})" if c["due"] else c["name"])
    print(f"  낼 파일: {c['file']}" + (" (원고에서 다시 만듦)" if c["remake"] else ""))
    print(f"  지금까지 {c['attempt']}번 냄" + (f" / 최대 {c['allowed']}" if c["allowed"] > 0 else "")
          + (f" — 마지막: {', '.join(c['previous'])}" if c["previous"] else ""))
    for n in c["notes"]:
        print("  · " + n)
    if c["problems"]:
        sys.exit("제출하지 않음:\n" + "\n".join("  ✗ " + x for x in c["problems"]))
    if not args.yes:
        if not sys.stdin.isatty():
            sys.exit("확인 없이 내려면 --yes")
        if input("Canvas 에 제출할까요? [y/N] ").strip().lower() not in ("y", "yes", "ㅛ"):
            sys.exit("취소함")
    try:
        r = submit.submit(conn, args.key, args.file, reveal=not args.no_reveal)
    except submit.SubmitError as e:
        sys.exit(str(e))
    print(f"✓ 제출됨 — {r['name']} · {r['size']:,}바이트" + (f" · {r['pages']}쪽" if r["pages"] else "")
          + f" · {r['attempt']}번째" + (" · 늦은 제출" if r["late"] else "") + "\n  Canvas 에서 다시 읽어 확인함. 탐색기에 파일을 띄움.")


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


def cmd_quiz_help(conn, args):
    from pa import quizhelp
    if args.key == "off":
        quizhelp.stop(conn)
        return print("퀴즈 도움 끔")
    row = conn.execute("SELECT * FROM tasks WHERE key = ?", (args.key,)).fetchone()
    if not row:
        raise SystemExit(f"'{args.key}' 를 찾지 못했습니다 (bin/pa list)")
    s = quizhelp.start(conn, dict(row))
    if not s:
        raise SystemExit("config/timetable.yaml 에 quiz_help 가 없습니다 (꺼짐)")
    print(f"퀴즈 도움 켬 — {s['until'][11:16]} 까지 찍은 스크린샷을 AI 에 보냅니다")


def cmd_time(conn, args):
    conn.execute("UPDATE tasks SET minutes_override = ? WHERE key = ?", (args.minutes, args.key))
    conn.commit()
    print(f"{args.key} → {args.minutes}분")


# .env 의 PA_ENGINE=off 인 PC(두 번째 노트북)에서 막는 명령 — 일정·캘린더·휴대폰 화면은 엔진 PC 한 대만 고친다
ENGINE_ONLY = ("watch", "run", "plan", "timetable", "sync-timetable", "dashboard-check")


def engine_off():
    from pa import config
    config.load_env()
    return os.environ.get("PA_ENGINE", "").strip().lower() == "off"


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ENGINE_ONLY and engine_off():
        print("이 PC 는 엔진을 끈 PC 입니다 (.env 의 PA_ENGINE=off) — 일정·할 일은 엔진 PC 나 휴대폰 화면에서")
        sys.exit(1 if sys.argv[1] == "dashboard-check" else 0)  # 서버 대기는 실패로 → 대시보드 열기를 건너뜀
    for s in (sys.stdout, sys.stderr):  # Windows 콘솔·파이프에서도 한글·이모지가 깨지지 않게
        if s and hasattr(s, "reconfigure") and (s.encoding or "").lower().replace("-", "") != "utf8":
            s.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) > 1 and sys.argv[1] == "google-login":
        from pa import gcal
        return gcal.login()
    if len(sys.argv) > 2 and sys.argv[1] in ("pdf", "reveal"):
        from pa import materials, pdf
        path = sys.argv[2]
        if sys.argv[1] == "pdf":
            path, pages = pdf.make(path)
            print(f"{path} ({pages}쪽)")
        return materials.reveal(path)
    if len(sys.argv) > 1 and sys.argv[1] == "browser":
        from pa import browser
        return browser.main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "lectures":
        from pa import lectures
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return lectures.main()
    if len(sys.argv) > 1 and sys.argv[1] == "power":
        from pa import power
        return power.main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "timetable":
        from pa import portal
        return portal.main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "sync-timetable":
        from pa import sync_timetable
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return sync_timetable.main()

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
    sub.add_parser("pull", help="내 git 저장소를 GitHub 과 대조해 내려받기 (config/repos.yaml)").set_defaults(fn=cmd_pull)
    sub.add_parser("dashboard-check").set_defaults(fn=cmd_dashboard_check)
    sp = sub.add_parser("peer", help="두 PC 같이 쓰기: 상태 / sync (지금 맞추기) / init <비공개 저장소 주소>")
    sp.add_argument("action", nargs="?", default="status", choices=["status", "sync", "init"])
    sp.add_argument("url", nargs="?")
    sp.set_defaults(fn=cmd_peer)
    sub.add_parser("open").set_defaults(fn=cmd_open)
    sub.add_parser("shortcut").set_defaults(fn=cmd_shortcut)
    sub.add_parser("vscode-ext").set_defaults(fn=cmd_vscode_ext)
    sp = sub.add_parser("plan")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(fn=cmd_plan)
    for name, status in (("done", "done"), ("ignore", "ignored"), ("unignore", "open")):
        sp = sub.add_parser(name)
        sp.add_argument("key")
        sp.set_defaults(fn=cmd_status(status))
    sp = sub.add_parser("quiz-help", help="퀴즈 도움 켜기 (<키>) · 끄기 (off)")
    sp.add_argument("key")
    sp.set_defaults(fn=cmd_quiz_help)
    sp = sub.add_parser("time")
    sp.add_argument("key")
    sp.add_argument("minutes", type=int)
    sp.set_defaults(fn=cmd_time)
    sub.add_parser("lectures", help="이번 주 강의 목록·열기")
    sub.add_parser("sync-timetable", help="수업 시간표 → Google 캘린더 (--dry-run)")
    sp = sub.add_parser("submit", help="Canvas 과제에 파일 제출 (확인 → .md 면 PDF 로 → 올리기 → 다시 읽어 확인)")
    sp.add_argument("key")
    sp.add_argument("file", nargs="?", help="없으면 그 과제의 보고서 파일 (.md → 옆의 .pdf)")
    sp.add_argument("--yes", action="store_true", help="묻지 않고 제출")
    sp.add_argument("--no-reveal", action="store_true", help="탐색기 안 띄움")
    sp.set_defaults(fn=cmd_submit)
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
