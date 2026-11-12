"""R11 퀴즈 연결: 퀴즈 앱의 '기록 내보내기' 파일로 복습 일정을 만든다. 퀴즈 앱은 고치지 않는다.

1. 퀴즈 앱(브라우저)에서 [기록 내보내기] → Windows 다운로드 폴더에 quizapp-backup-날짜.json
2. 엔진이 가장 새 백업을 읽어 풀이 기록(quiz_log)에 합친다 (파일은 그대로 둔다)
3. 문제마다 간격 반복: 마지막에 틀렸으면 다음 날, 연속으로 맞힌 횟수에 따라 1·3·7·14·30일 뒤
4. 복습할 문제가 있는 덱마다 '퀴즈 복습' 할 일 → 계획에 들어감.
   다시 풀고 내보내면 그 할 일은 자동 완료.
"""
import json
import math
import os
from datetime import datetime, time, timedelta
from pathlib import Path

import yaml

from pa import db, materials
from pa.config import ROOT
from pa.model import KST, now, parse_dt

INTERVALS = [1, 3, 7, 14, 30]  # 연속 정답 1·2·3·4·5회 이상 → 다음 복습까지 날짜
LOOKAHEAD_DAYS = 2             # 오늘부터 이 기간 안에 복습할 문제를 모아 한 번에
RECENT_DAYS = 120              # 이보다 오래 안 푼 문제는 복습 대상에서 뺀다
FRESH_DAYS = 14                # 백업이 이보다 오래됐으면 복습을 만들지 않고 '내보내기' 를 부탁한다
SCHEMA = """
CREATE TABLE IF NOT EXISTS quiz_log (qid TEXT NOT NULL, correct INTEGER NOT NULL, at TEXT NOT NULL,
                                     PRIMARY KEY (qid, at));
"""


def cfg():
    c = yaml.safe_load((ROOT / "config" / "courses.yaml").read_text()).get("quiz", {})
    return {"dir": Path(os.path.expanduser(c.get("dir", "~/quiz_system_project/pharmacy"))),
            "url": c.get("url", "https://rhombusbork.github.io/Pharmacy/")}


def latest_backup():
    d = materials.downloads_dir()
    files = sorted(d.glob("quizapp-backup*.json"), key=lambda f: f.stat().st_mtime) if d else []
    return files[-1] if files else None


def decks():
    """deckId → {subject, title} (퀴즈 앱의 덱 목록에서 읽기만)."""
    base = cfg()["dir"] / "decks"
    out = {}
    for idx in ("index.json", "index-hidden.json"):
        try:
            paths = json.loads((base / idx).read_text())["decks"]
        except (OSError, ValueError, KeyError):
            continue
        for p in paths:
            try:
                d = json.loads((base / p).read_text())
                out[d["deckId"]] = {"subject": d.get("subject", ""), "title": d.get("title", d["deckId"])}
            except (OSError, ValueError, KeyError):
                continue
    return out


def import_backup(conn, path):
    """백업의 풀이 기록을 합친다. 같은 기록은 한 번만. 들어간 수 반환."""
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or not isinstance(data.get("answerLog"), list):
        raise ValueError("퀴즈 기록 백업 형식이 아님")
    conn.executescript(SCHEMA)
    n = 0
    for a in data["answerLog"]:
        if isinstance(a, dict) and isinstance(a.get("qid"), str) and a.get("at"):
            n += conn.execute("INSERT OR IGNORE INTO quiz_log VALUES (?, ?, ?)",
                              (a["qid"], int(bool(a.get("correct"))), a["at"])).rowcount
    db.set_meta(conn, "quiz_backup", json.dumps({"file": Path(path).name, "mtime": Path(path).stat().st_mtime}))
    if n:
        db.log(conn, "quiz_imported", None, file=Path(path).name, answers=n)
    conn.commit()
    return n


def next_review(results):
    """한 문제의 풀이 결과 [(시각, 맞음)] (시간순) → 다음 복습 날짜."""
    last_at, last_ok = results[-1]
    if not last_ok:
        return (last_at + timedelta(days=1)).date()
    streak = 0
    for _, ok in reversed(results):
        if not ok:
            break
        streak += 1
    return (last_at + timedelta(days=INTERVALS[min(streak, len(INTERVALS)) - 1])).date()


def due_by_deck(conn, today):
    """덱 → [(문제 id, 복습 날짜, 마지막에 틀림)] — 오늘+LOOKAHEAD 안에 복습할 것만."""
    conn.executescript(SCHEMA)
    hist = {}
    for r in conn.execute("SELECT qid, correct, at FROM quiz_log ORDER BY at"):
        hist.setdefault(r["qid"], []).append((parse_dt(r["at"]), bool(r["correct"])))
    out = {}
    for qid, res in hist.items():
        if res[-1][0].date() < today - timedelta(days=RECENT_DAYS):
            continue
        d = next_review(res)
        if d <= today + timedelta(days=LOOKAHEAD_DAYS):
            out.setdefault(qid.rsplit("/", 1)[0], []).append((qid, d, not res[-1][1]))
    return out


def sync(conn):
    """새 백업이 있으면 합치고, 덱별 복습 할 일을 만든다. 새로 합친 풀이 수 반환."""
    conn.executescript(SCHEMA)
    added = 0
    f = latest_backup()
    seen = json.loads(db.get_meta(conn, "quiz_backup") or "{}")
    if f and (f.name != seen.get("file") or f.stat().st_mtime > seen.get("mtime", 0)):
        added = import_backup(conn, f)

    today = now().date()
    info, url = decks(), cfg()["url"]
    items = []
    seen = json.loads(db.get_meta(conn, "quiz_backup") or "{}")
    fresh = seen.get("mtime", 0) >= (now() - timedelta(days=FRESH_DAYS)).timestamp()
    for deck, qs in (due_by_deck(conn, today).items() if fresh else []):
        if deck not in info:  # 지금 퀴즈 앱에 없는 덱(예: 중간고사 브랜치) — 열 수 없으니 복습도 안 만든다
            continue
        d = max(today, min(x[1] for x in qs))
        wrong = sum(1 for x in qs if x[2])
        meta = info.get(deck, {"subject": "", "title": deck})
        items.append({
            "key": f"q:{deck}@{d.isoformat()}", "kind": "review", "course": meta["subject"],
            "title": f"퀴즈 복습: {meta['title']} ({len(qs)}문제" + (f", 틀린 {wrong}" if wrong else "") + ")",
            "due": datetime.combine(d + timedelta(days=LOOKAHEAD_DAYS), time(23, 59), KST).isoformat(),
            "earliest": datetime.combine(d, time(0, 0), KST).isoformat(),
            "minutes": max(10, math.ceil(len(qs) * 1.5)), "url": url,
        })

    before = {r["key"] for r in conn.execute("SELECT key FROM tasks WHERE source = 'quiz' AND status = 'open'")}
    db.sync_source(conn, "quiz", items, mark_missing_gone=True)
    if added:  # 새 기록을 가져온 뒤 사라진 복습 = 다시 풀었음 → 완료
        for k in before - {it["key"] for it in items}:
            db.set_status(conn, k, "done", "auto")
    conn.commit()
    return added


def status(conn):
    """대시보드용: 마지막 백업 시각, 과목별 복습할 문제 수."""
    conn.executescript(SCHEMA)
    seen = json.loads(db.get_meta(conn, "quiz_backup") or "{}")
    info = decks() if seen else {}
    by_subject = {}
    for deck, qs in (due_by_deck(conn, now().date()) if seen else {}).items():
        if deck in info:
            s = info[deck]["subject"] or "기타"
            by_subject[s] = by_subject.get(s, 0) + len(qs)
    at = seen.get("mtime")
    return {"backupAt": datetime.fromtimestamp(at, KST).isoformat() if at else None,
            "stale": not at or at < (now() - timedelta(days=FRESH_DAYS)).timestamp(),
            "dueBySubject": by_subject, "url": cfg()["url"]}
