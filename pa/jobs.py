"""R3 에이전트 작업: 대기열 + 보고서 준비·초안.

보고서 작업 단계
  1. 과제 읽기     Canvas 과제 설명 (Canvas 과제일 때)
  2. 자료 모으기   materials 의 관련 자료, study_system/notes 의 내 노트
  3. 파일 만들기   ~/report/<학번>_<이름>_<과목>_<종류>_<번호>.md  (report/CLAUDE.md 규칙)
  4. 초안 쓰기     내 구독의 Claude (`claude -p`, report 폴더에서 실행 → report 규칙 자동 적용)
  5. 열기          VSCode 편집기 탭

Claude 는 읽기(Read)만 허용한다. 파일은 엔진이 쓴다.
"""
import html
import re
import subprocess
from datetime import datetime
from pathlib import Path

from pa import ai, canvas, db, materials
from pa.model import KST, now, parse_dt, short_course

REPORT_DIR = Path.home() / "report"
MAX_REF_BYTES = 15 * 1024 * 1024  # 단서 없이 고른 참고 자료는 이보다 작은 것만
DOC_KINDS = [("결과보고서", "결과보고서"), ("예비보고서", "예비보고서"), ("성찰보고서", "성찰보고서"),
             ("배움노트", "배움노트"), ("보고서", "보고서"), ("발표", "발표자료"), ("텍스트", "텍스트"),
             ("연습문제", "연습문제"), ("에세이", "에세이")]


def _ts():
    return datetime.now(KST).isoformat(timespec="seconds")


def enqueue(conn, kind, key, title):
    row = conn.execute("SELECT id FROM jobs WHERE kind = ? AND key = ? AND status IN ('queued', 'running')",
                       (kind, key)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO jobs (kind, key, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                       (kind, key, title, _ts(), _ts()))
    db.log(conn, "job_queued", key, kind=kind)
    conn.commit()
    return cur.lastrowid


def _update(conn, job_id, **fields):
    fields["updated_at"] = _ts()
    conn.execute(f"UPDATE jobs SET {', '.join(k + ' = ?' for k in fields)} WHERE id = ?", (*fields.values(), job_id))
    conn.commit()


def recent(conn):
    since = (now().replace(hour=0, minute=0)).isoformat()
    return [dict(r) for r in conn.execute(
        "SELECT id, kind, key, title, status, step, result, error, claude, updated_at FROM jobs "
        "WHERE status IN ('queued', 'running') OR updated_at >= ? ORDER BY id DESC LIMIT 10", (since,))]


def run_next(conn):
    """대기 중인 작업 하나를 처리. 처리했으면 True."""
    row = conn.execute("SELECT * FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
    if not row:
        return False
    _update(conn, row["id"], status="running", step="시작")
    try:
        result = {"report": report_job, "report-force": lambda c, j: report_job(c, j, force=True),
                  "notices": notices_job, "summary": summary_job}[row["kind"]](conn, row)
        _update(conn, row["id"], status="done", step="완료", result=str(result))
        db.log(conn, "job_done", row["key"], kind=row["kind"], result=str(result))
    except Exception as e:
        _update(conn, row["id"], status="failed", error=str(e)[:500])
        db.log(conn, "job_failed", row["key"], kind=row["kind"], error=str(e)[:200])
    conn.commit()
    return True


def reset_stuck(conn):
    """엔진이 꺼지면서 '진행 중'으로 남은 작업은 다시 대기열로."""
    conn.execute("UPDATE jobs SET status = 'queued', step = '다시 시작 대기' WHERE status = 'running'")
    conn.commit()


# ---- 보고서 ---------------------------------------------------------------

def student():
    """학번·이름은 report/CLAUDE.md 에서 읽는다 (규칙 파일이 한 곳에서 관리)."""
    m = re.search(r"학번은\s*(\d+),\s*이름은\s*(\S+?)다", (REPORT_DIR / "CLAUDE.md").read_text())
    if not m:
        raise ValueError("report/CLAUDE.md 에서 학번·이름을 찾지 못함")
    return m.group(1), m.group(2)


def doc_kind(title):
    return next((v for k, v in DOC_KINDS if k in title), "과제")


def subject(task):
    dirs = materials.course_dirs(task["course"])
    if dirs:
        return dirs[1].name  # notes 폴더 이름 = 짧은 과목명 (예: 유기약화학)
    if task["course"]:
        return re.sub(r"\s+", "", short_course(task["course"]))
    return re.split(r"[\s_]+", task["title"])[0]


def report_path(task):
    sid, name = student()
    subj, kind = subject(task), doc_kind(task["title"])
    prefix = f"{sid}_{name}_{subj}_{kind}_"
    nums = [int(n) for (_, n) in materials.clues(task["title"])]
    if nums:
        num = nums[0]  # Ch22 배움노트 → 22
    else:
        used = [int(m.group(1)) for f in REPORT_DIR.glob(prefix + "*.md") if (m := re.search(r"_(\d+)\.md$", f.name))]
        num = max(used, default=0) + 1
    return REPORT_DIR / f"{prefix}{num}.md"


def assignment_text(task):
    m = re.search(r"/courses/(\d+)/assignments/(\d+)", task["url"] or "")
    if not m:
        return ""
    a = canvas.get(f"/courses/{m.group(1)}/assignments/{m.group(2)}")
    text = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", a.get("description") or "")
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    extra = []
    if a.get("points_possible") is not None:
        extra.append(f"배점: {a['points_possible']}")
    if a.get("submission_types"):
        extra.append("제출 형식: " + ", ".join(a["submission_types"]))
    if a.get("allowed_extensions"):
        extra.append("허용 파일: " + ", ".join(a["allowed_extensions"]))
    return (re.sub(r"\n{3,}", "\n\n", text).strip() + "\n" + " · ".join(extra)).strip()


def report_job(conn, job, force=False):
    task = conn.execute("SELECT * FROM tasks WHERE key = ?", (job["key"],)).fetchone()
    if not task:
        raise ValueError("할 일을 찾지 못함")
    task = dict(task)

    _update(conn, job["id"], step="1/5 과제 읽기")
    desc = assignment_text(task)

    _update(conn, job["id"], step="2/5 자료 모으기")
    dirs = materials.course_dirs(task["course"])
    # 정확히 맞는 자료(17강·Ch22 등) 우선. 아니면 작은 파일만 — 수백 쪽 교과서를 통째로 읽히지 않게
    mats = []
    if dirs:
        cand = materials.scan(dirs[0], task["title"])
        mats = [f for sc, f in cand if sc >= 10][:3] or [f for sc, f in cand if sc >= 2 and f.stat().st_size < MAX_REF_BYTES][:2]
    notes = [f for sc, f in materials.scan(dirs[1], task["title"])[:3] if sc >= 2] if dirs else []

    _update(conn, job["id"], step="3/5 파일 만들기")
    path = report_path(task)
    if path.exists() and not force:
        _update(conn, job["id"], step="이미 있는 파일 열기")
        materials.open_file(path)
        return path
    if path.exists():  # 새로 쓰기: 지금 파일은 _old 로 보관 (지우지 않음)
        n = 1
        while (old := path.with_name(f"{path.stem}_old{n}{path.suffix}")).exists():
            n += 1
        path.rename(old)

    _update(conn, job["id"], step="4/5 초안 쓰기 (Claude, 몇 분 걸림)")
    sid, name = student()
    due = parse_dt(task["due"])
    prompt = f"""학생의 과제 초안을 쓴다. 이 폴더의 CLAUDE.md(글쓰기 규칙)를 모두 지킨다.

과제: {task['title']}
과목: {short_course(task['course']) or '-'}
마감: {due:%Y-%m-%d %H:%M} 까지
과제 설명 (Canvas):
{desc or '(설명 없음 — 제목으로 판단)'}

참고 자료 (필요한 부분만 Read 로 읽는다):
{chr(10).join('- ' + str(f) for f in mats) or '- (없음)'}

학생 본인의 공부 노트 (학생의 말이다. 내용과 표현을 우선 활용한다):
{chr(10).join('- ' + str(f) for f in notes) or '- (없음)'}

출력 조건
- 문서 본문 마크다운만 출력한다. 앞뒤 인사, 설명, 코드 블록 표시를 넣지 않는다.
- 첫 줄은 "# 제목", 바로 아래 줄은 <div align="right">{sid} {name}</div>
- 과제 설명이 정한 형식과 분량을 따른다. 정해진 게 없으면 A4 한두 쪽.
- 학생 자신의 생각, 관찰, 경험, 의견이 들어가야 할 자리는 지어내지 말고
  [✍ 내 생각: 여기에 무엇을 쓰면 좋을지 한 줄 안내] 로 비워 둔다.
- 확인하지 않은 사실과 참고문헌은 쓰지 않는다. 자료에서 가져온 내용은 어느 자료인지 괄호로 적는다.
"""
    text = ai.ask(prompt, cwd=REPORT_DIR, add_dirs=[materials._cfg()["root"]], timeout=900)
    conn.execute("UPDATE jobs SET claude = claude + 1 WHERE id = ?", (job["id"],))
    text = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", text.strip())
    if not text.startswith("#"):
        raise ValueError("초안 형식이 이상함: " + text[:120])
    path.write_text(text + "\n")

    _update(conn, job["id"], step="5/5 열기")
    try:
        materials.open_file(path)
    except Exception:
        pass
    return path


# ---- 공지 정리 (버튼을 눌렀을 때만) ------------------------------------------

def notices_job(conn, job):
    """새 공지를 Claude 가 읽고: 공지마다 한 줄 요약 + '이 학생이 안 해도 되는' 과제 제외 후보."""
    import json as _json
    notes = conn.execute("SELECT * FROM notices WHERE status = 'new' ORDER BY posted_at").fetchall()
    if not notes:
        return "새 공지 없음"
    tasks = conn.execute("SELECT key, course, title, due FROM tasks WHERE source = 'canvas' AND status = 'open' "
                         "AND kind IN ('assignment', 'quiz')").fetchall()
    _update(conn, job["id"], step=f"공지 {len(notes)}개 읽는 중 (Claude)")
    prompt = "학생의 Canvas 과목 공지를 정리한다. JSON 만 출력한다 (설명·코드 블록 표시 없이).\n\n[공지]\n" + "\n\n".join(
        f"id={n['id']} | {short_course(n['course'])} | {n['title']} | {n['posted_at'][:10]}\n{n['text'][:2500]}" for n in notes
    ) + "\n\n[학생의 남은 과제·퀴즈]\n" + "\n".join(
        f"key={t['key']} | {short_course(t['course'])} | {t['title']} | 마감 {t['due'][:16]}" for t in tasks
    ) + """

출력 형식:
{"summaries": [{"id": "공지 id", "summary": "학생이 할 일 중심의 한 줄 (해라체)"}],
 "exclude": [{"key": "과제 key", "reason": "공지의 어느 문장 때문인지 짧게"}]}
exclude 에는 공지가 '이 학생은 내지 않아도 된다'고 분명히 말하는 과제만 넣는다
(예: 조장·대표만 제출, 해당자만 제출, 과제 취소). 애매하면 넣지 않는다. 학생이 조장인지 모르면 넣고 이유에 그 조건을 적는다."""
    text = ai.ask(prompt, timeout=600)
    conn.execute("UPDATE jobs SET claude = claude + 1 WHERE id = ?", (job["id"],))
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Claude 응답을 읽지 못함: " + text[:120])
    data = _json.loads(m.group(0))
    for x in data.get("summaries", []):
        conn.execute("UPDATE notices SET summary = ? WHERE id = ?", (x.get("summary", ""), str(x.get("id"))))
    known = {t["key"]: t for t in tasks}
    sugg = [{"key": x["key"], "title": known[x["key"]]["title"], "course": short_course(known[x["key"]]["course"]),
             "reason": x.get("reason", "")} for x in data.get("exclude", []) if x.get("key") in known]
    db.set_meta(conn, "notice_suggestions", _json.dumps(sugg, ensure_ascii=False))
    conn.commit()
    return f"공지 {len(notes)}개 요약 · 제외 후보 {len(sugg)}개"


# ---- 자료 요약 (버튼을 눌렀을 때만) ------------------------------------------

MAX_SUMMARY_BYTES = 25 * 1024 * 1024  # 교과서 통째 같은 큰 파일은 요약하지 않음 (사용량 보호)


def summary_path(pdf):
    pdf = Path(pdf)
    return pdf.parent / "요약" / f"{pdf.stem}_요약.md"


def summary_job(conn, job):
    """materials 의 PDF → 같은 과목 폴더의 요약/<이름>_요약.md (내 노트 notes/ 와 섞지 않는다)."""
    pdf = Path(job["key"]).resolve()
    root = materials._cfg()["root"].resolve() / "materials"
    if not str(pdf).startswith(str(root)) or not pdf.exists():
        raise ValueError("materials 안의 파일만 요약합니다")
    if pdf.stat().st_size > MAX_SUMMARY_BYTES:
        raise ValueError("파일이 너무 큽니다 (교과서 전체 등) — 필요한 장만 따로 저장해서 요약하세요")
    out = summary_path(pdf)
    if out.exists():
        materials.open_file(out)
        return out
    _update(conn, job["id"], step="요약 쓰는 중 (Claude, 몇 분 걸림)")
    prompt = f"""약학과 학생이 공부할 강의 자료를 요약한다. 이 파일을 Read 로 읽는다: {pdf}

마크다운만 출력한다 (인사·설명·코드 블록 표시 없이). 구성:
# {pdf.stem} 요약
## 핵심 내용 — 자료의 흐름대로, 슬라이드에 있는 내용만
## 꼭 알아야 할 용어·식 — 표 (용어 | 뜻)
## 시험에 나올 만한 포인트 — 자료에서 강조된 것 위주
## 헷갈리기 쉬운 것
자료에 없는 내용은 쓰지 않는다. 그림·구조식은 말로 설명하고 몇 쪽에 있는지 적는다. 해라체."""
    text = ai.ask(prompt, cwd=pdf.parent, timeout=900)
    conn.execute("UPDATE jobs SET claude = claude + 1 WHERE id = ?", (job["id"],))
    text = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", text.strip())
    if not text.startswith("#"):
        raise ValueError("요약 형식이 이상함: " + text[:120])
    out.parent.mkdir(exist_ok=True)
    out.write_text(text + "\n")
    try:
        materials.open_file(out)
    except Exception:
        pass
    return out
