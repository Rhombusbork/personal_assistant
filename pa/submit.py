"""Canvas 과제 파일 제출 — 제출 전 확인 → (필요하면 .md → PDF) → 올리기 → Canvas 에서 다시 읽어 확인 → 기록.

- .md 는 절대 보내지 않는다. .md 를 주면 옆의 .pdf 를 보내고, .md 가 더 새것이면 PDF 를 다시 만든다 (pa/pdf.py).
- 하나라도 걸리면 안 낸다: 파일 올리기 과제가 아님 · 잠김 · 남은 횟수 없음 · 허용 확장자 아님 · 파일 없음 · 이미 같은 파일을 냄.
- 낸 뒤 Canvas 에서 다시 읽어 파일 크기와 제출 번호가 맞는지 확인 → events 'submitted' (대시보드·휴대폰 '제출 기록').
- 지금은 사람이 시킬 때만 (bin/pa submit, 채팅). 예약·자동 제출은 docs/week-grid-plan.md 4장 P7.
"""
import re
from datetime import datetime
from pathlib import Path

from pa import canvas, db, jobs, pdf
from pa.model import KST, now


class SubmitError(RuntimeError):
    pass


def ids(task):
    m = re.search(r"/courses/(\d+)/assignments/(\d+)", task["url"] or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def _file(conn, task, path):
    """보낼 파일과 (원고 .md, PDF 를 다시 만들어야 하는지)."""
    p = Path(path).expanduser() if path else jobs.report_path(task, conn)
    if p.suffix.lower() != ".md":
        return p, None, False
    out = p.with_suffix(".pdf")
    return out, p, p.exists() and (not out.exists() or p.stat().st_mtime > out.stat().st_mtime)


def check(conn, key, path=None):
    """제출 전 확인. problems 가 비어 있어야 낼 수 있다."""
    row = conn.execute("SELECT * FROM tasks WHERE key = ?", (key,)).fetchone()
    if not row:
        raise SubmitError(f"할 일을 찾지 못함: {key} (bin/pa list 의 맨 앞이 키)")
    task = dict(row)
    cid, aid = ids(task)
    if not cid:
        raise SubmitError(f"Canvas 과제가 아님: {task['title']}")
    file, md, remake = _file(conn, task, path)
    a = canvas.get(f"/courses/{cid}/assignments/{aid}")
    sub = canvas.get(f"/courses/{cid}/assignments/{aid}/submissions/self") or {}
    prev = sub.get("attempt") or 0
    if sub.get("workflow_state") in (None, "unsubmitted"):
        prev = 0
    problems, notes = [], []
    if "online_upload" not in (a.get("submission_types") or []):
        problems.append("파일 올리기 과제가 아님 (" + ", ".join(a.get("submission_types") or ["?"]) + ")")
    lock = a.get("lock_at") and datetime.fromisoformat(a["lock_at"].replace("Z", "+00:00"))
    if a.get("locked_for_user") or (lock and lock <= now()):
        problems.append("과제가 잠겨 더 낼 수 없음")
    allowed = a.get("allowed_attempts") or -1
    if allowed > 0 and prev >= allowed:
        problems.append(f"제출 횟수를 다 씀 ({prev}/{allowed})")
    exts = a.get("allowed_extensions") or []
    if exts and file.suffix.lower().lstrip(".") not in [e.lower() for e in exts]:
        problems.append(f"허용 확장자 아님: {file.suffix} (허용: {', '.join(exts)})")
    if not file.exists() and not remake:
        problems.append(f"파일 없음: {file}")
    elif file.suffix.lower() == ".md":
        problems.append(".md 는 보내지 않음")
    elif not remake:
        size = file.stat().st_size
        if any(x.get("size") == size for x in sub.get("attachments") or []):
            problems.append("이미 같은 파일을 냈음 (크기가 같음)")
    if remake:
        notes.append("원고(.md)가 PDF 보다 새것 → PDF 를 다시 만들어 냄")
        try:  # 새로 만들 PDF 에 글자로 남는 마크다운(그림 등)이 있으면 안 낸다
            problems += [f"PDF 에 변환 안 된 마크다운: {name} — {ex}" for name, ex in pdf.warnings(md)]
        except FileNotFoundError as e:
            problems.append(str(e))
    elif md and md.exists() and file.exists():  # 이미 있는 PDF: 원고의 그림보다 작으면 그림이 빠졌을 수 있음
        figs = [md.parent / m[2] for m in map(pdf.RE_IMG.match, md.read_text(encoding="utf-8").splitlines()) if m]
        if figs and file.stat().st_size < sum(f.stat().st_size for f in figs if f.exists()):
            notes.append("PDF 가 원고의 그림 파일들보다 작음 → 그림이 빠졌을 수 있음 (PDF 를 열어 확인)")
    due = a.get("due_at") and datetime.fromisoformat(a["due_at"].replace("Z", "+00:00")).astimezone(KST)
    if due and due < now():
        notes.append("마감이 지남 → 늦은 제출로 표시될 수 있음")
    return {"task": task, "cid": cid, "aid": aid, "file": file, "md": md, "remake": remake, "name": a.get("name"),
            "due": due, "attempt": prev, "allowed": allowed, "previous": [x.get("display_name") for x in sub.get("attachments") or []],
            "problems": problems, "notes": notes}


def submit(conn, key, path=None, reveal=True, auto=False):
    """확인을 통과하면 내고, Canvas 에서 다시 읽어 확인한 결과를 기록한다.
    auto: 자동 제출 (pa/autosubmit.py) → '확인 필요' 카드. 직접 낸 것(버튼·명령)은 본 것이므로 확인된 것으로."""
    info = check(conn, key, path)
    if info["problems"]:
        raise SubmitError("제출하지 않음: " + " / ".join(info["problems"]))
    file = info["file"]
    if info["remake"]:
        file, _ = pdf.make(info["md"])
    base = f"/courses/{info['cid']}/assignments/{info['aid']}/submissions"
    up = canvas.upload_file(f"{base}/self/files", file)
    canvas.post(base, {"submission[submission_type]": "online_upload", "submission[file_ids][]": [up["id"]]})
    after = canvas.get(f"{base}/self") or {}
    size = file.stat().st_size
    got = [x for x in after.get("attachments") or [] if x.get("size") == size]
    if not got or (after.get("attempt") or 0) <= info["attempt"]:
        db.log(conn, "submit_unverified", key, file=str(file))
        conn.commit()
        raise SubmitError("올렸지만 Canvas 에서 확인되지 않음 — Canvas 제출 페이지에서 직접 확인해 주세요")
    result = {"file": str(file), "name": got[0].get("display_name"), "size": size,
              "pages": pdf.pages(file) if file.suffix.lower() == ".pdf" else None,
              "attempt": after.get("attempt"), "late": bool(after.get("late")), "url": info["task"]["url"], "auto": auto}
    db.log(conn, "submitted", key, **result)
    db.set_status(conn, key, "done", "submit")
    conn.commit()
    if reveal:
        from pa import materials
        materials.reveal(file)
    return result


def recent(conn, days=14):
    """대시보드·휴대폰 '제출 기록'."""
    import json
    from datetime import timedelta
    since = (now() - timedelta(days=days)).isoformat()
    out = []
    for r in conn.execute("SELECT e.ts, e.key, e.detail, t.title, t.course FROM events e LEFT JOIN tasks t ON t.key = e.key "
                          "WHERE e.type = 'submitted' AND e.ts >= ? ORDER BY e.ts DESC", (since,)):
        d = json.loads(r["detail"] or "{}")
        out.append({"ts": r["ts"], "key": r["key"], "title": r["title"] or r["key"], "course": r["course"] or "",
                    **{k: d.get(k) for k in ("name", "size", "pages", "attempt", "late", "url")}})
    return out
