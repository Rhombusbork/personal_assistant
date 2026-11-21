"""퀴즈 도움 — 퀴즈를 푸는 동안 찍은 스크린샷을 AI 에 보내 답과 풀이를 받는다 (AI 도움이 허용된 퀴즈용).

  1. 퀴즈 페이지가 열리면 (계획 시간 자동 열기 · 대시보드 ▶) '퀴즈 도움'이 켜진다.
     그 퀴즈 탭을 닫으면 꺼진다 (켜져 있는 동안만 15초마다 탭 제목을 봄). 늦어도 minutes 분 뒤엔 꺼짐
  2. 그동안 Win+Shift+S 나 PrtSc 로 문제를 찍으면 → Windows 스크린샷 폴더에 새 사진이 생김
  3. 엔진이 사진을 materials/<과목>/퀴즈풀이/<날짜>_<퀴즈>/ 로 복사하고, AI 에 답·풀이를 묻는다 (작업 'quizhelp')
  4. 풀이는 같은 폴더의 풀이.md 에 사진과 함께 쌓이고, VSCode 에 열린다

- 답 체크·제출은 사용자가 한다. 프로그램은 퀴즈를 시작하거나 답을 고르지 않는다.
- 꺼져 있을 때(퀴즈 도움 시간 밖) 찍은 스크린샷은 보내지 않는다.
- 풀이는 AI 의 글이라 notes/(내 말 기록)에 넣지 않고 materials/ 에 둔다 (study_system/CLAUDE.md 기록 원칙, git 제외).

설정: config/timetable.yaml 의 quiz_help (없으면 꺼짐). 손으로: bin/pa quiz-help <키> | off
"""
import json
import re
import shutil
from datetime import timedelta
from pathlib import Path

from pa import db, osutil
from pa.config import load_timetable
from pa.model import now, parse_dt, short_course

PIC_EXT = {".png", ".jpg", ".jpeg"}


def cfg():
    c = load_timetable().get("quiz_help")
    if not c or c.get("enabled") is False:
        return None
    return {"minutes": int(c.get("minutes", 120)), "screenshots_dir": c.get("screenshots_dir") or ""}


def screenshots_dir(c):
    if c["screenshots_dir"]:
        return Path(c["screenshots_dir"]).expanduser()
    if osutil.IS_WSL:
        users = Path("/mnt/c/Users")
        for u in sorted(users.iterdir()) if users.exists() else []:
            for d in (u / "Pictures" / "Screenshots", *u.glob("OneDrive*/Pictures/Screenshots")):
                if d.is_dir():
                    return d
        return None
    return Path.home() / "Pictures" / "Screenshots"


def state(conn):
    s = json.loads(db.get_meta(conn, "quiz_help") or "{}")
    return s if s and parse_dt(s["until"]) > now() else None


def start(conn, task, t_now=None):
    """이 퀴즈로 '퀴즈 도움'을 켠다 (켜진 뒤 찍은 사진만 보낸다)."""
    c = cfg()
    if not c:
        return None
    t_now = t_now or now()
    s = {"key": task["key"], "title": task["title"], "course": task["course"], "since": t_now.isoformat(),
         "until": (t_now + timedelta(minutes=c["minutes"])).isoformat()}
    db.set_meta(conn, "quiz_help", json.dumps(s, ensure_ascii=False))
    db.log(conn, "quiz_help_on", task["key"])
    conn.commit()
    return s


TAB_EVERY = 15  # 초


def watch_tab(conn, tab_open=None):
    """퀴즈 탭이 닫혔으면 퀴즈 도움을 끈다. 탭을 한 번이라도 본 뒤, 연달아 두 번 안 보이면 닫힌 것으로
    (페이지가 뜨기 전·제목을 못 읽을 때 잘못 끄지 않게). 껐으면 True."""
    s = state(conn)
    if not s:
        return False
    if tab_open is None:
        from pa.autoplay import tab_open
    here = tab_open(s["title"])
    if here is None:
        return False
    if here:
        s["seen"], s["missing"] = True, 0
    elif s.get("seen"):
        s["missing"] = s.get("missing", 0) + 1
        if s["missing"] >= 2:
            stop(conn)
            db.log(conn, "quiz_help_off", s["key"], why="tab_closed")
            conn.commit()
            return True
    db.set_meta(conn, "quiz_help", json.dumps(s, ensure_ascii=False))
    conn.commit()
    return False


def stop(conn):
    db.set_meta(conn, "quiz_help", "")
    conn.commit()


def folder(s):
    """materials/<과목>/퀴즈풀이/<날짜>_<퀴즈 제목>/"""
    from pa import materials
    dirs = materials.course_dirs(s["course"])
    base = dirs[0] if dirs else materials._cfg()["root"] / "materials" / "기타"
    name = re.sub(r'[\\/:*?"<>|]+', " ", s["title"]).strip()[:60]
    return base / "퀴즈풀이" / f"{parse_dt(s['since']):%Y-%m-%d}_{name}"


def scan(conn):
    """퀴즈 도움이 켜져 있으면 새 스크린샷을 가져와 작업으로 맡긴다. 맡긴 사진 수."""
    c, s = cfg(), state(conn)
    if not c or not s:
        return 0
    src = screenshots_dir(c)
    if not src or not src.is_dir():
        return 0
    seen = max(parse_dt(s["since"]).timestamp(), float(db.get_meta(conn, "quiz_help_seen") or 0))
    new = sorted((f for f in src.iterdir() if f.suffix.lower() in PIC_EXT and f.stat().st_mtime > seen),
                 key=lambda f: f.stat().st_mtime)
    if not new:
        return 0
    from pa import jobs
    dest = folder(s)
    dest.mkdir(parents=True, exist_ok=True)
    for f in new:
        n = len(list(dest.glob("문제_*"))) + 1
        pic = dest / f"문제_{n:02d}{f.suffix.lower()}"
        shutil.copy2(f, pic)
        db.set_meta(conn, "quiz_help_task:" + str(pic), json.dumps(s, ensure_ascii=False))
        jobs.enqueue(conn, "quizhelp", str(pic), f"📸 퀴즈 풀이 {n}: {short_course(s['course']) or ''} {s['title']}".strip())
    db.set_meta(conn, "quiz_help_seen", str(new[-1].stat().st_mtime))
    conn.commit()
    return len(new)


def job(conn, row):
    """사진 하나 → AI 답·풀이 → 풀이.md 에 덧붙임. 풀이.md 경로를 돌려준다."""
    from pa import ai, materials
    pic = Path(row["key"])
    s = json.loads(db.get_meta(conn, "quiz_help_task:" + str(pic)) or "{}")
    dirs = materials.course_dirs(s.get("course", ""))
    prompt = f"""학생이 푸는 퀴즈 문제의 스크린샷이다. 이 퀴즈는 AI 도움이 허용된 퀴즈다.
과목: {short_course(s.get('course', '')) or '-'} / 퀴즈: {s.get('title', '-')}

사진 속 문제마다:
1. **답**: 보기 번호·내용 (여러 개 고르는 문제면 모두)
2. **풀이**: 왜 그 답인지, 다른 보기는 왜 틀렸는지를 공부용으로 쉽게
3. 강의 자료에서 근거를 찾았으면 어느 자료인지 괄호로. 못 찾았으면 '일반 지식'이라고 적는다
- 확실하지 않으면 그렇다고 적는다 (학생이 확인하고 체크한다).
- 사진이 퀴즈 문제가 아니면 '퀴즈 문제가 아님' 한 줄만.
- 마크다운 본문만 출력한다. 제목(#)은 쓰지 않는다.
"""
    text = ai.ask(prompt, images=[pic], cwd=materials._cfg()["root"], add_dirs=[dirs[0]] if dirs and dirs[0].exists() else [],
                  timeout=600)
    conn.execute("UPDATE jobs SET claude = claude + 1 WHERE id = ?", (row["id"],))
    out = pic.parent / "풀이.md"
    head = "" if out.exists() else f"# {s.get('title', '퀴즈')} — 풀이 ({ai.name()})\n\n답 체크·제출은 직접. AI 답은 틀릴 수 있다.\n\n"
    with out.open("a", encoding="utf-8") as f:
        f.write(f"{head}## {pic.stem}\n\n![{pic.stem}]({pic.name})\n\n{text.strip()}\n\n")
    try:
        materials.open_file(out)
    except Exception:
        pass
    return out
