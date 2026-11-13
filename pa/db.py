"""SQLite 저장소 (data/pa.db).

tasks   할 일 하나당 한 줄. 출처(canvas/inbox)에서 다시 읽을 때마다 갱신된다.
events  자동 기록 (추가·완료·제외·마감 변경·계획 누락 …) — 시각화와 3단계 재료
plan    현재 학습 계획 (Google Calendar 일정 id 포함)
busy    계획 기간의 대면 수업·약속 (시각화용)
sessions 실제로 한 시간 기록 (⏱) — 예상 시간 보정에 쓴다
jobs    에이전트 작업 대기열과 결과 (🤖 작업 칸)
notices Canvas 과목 공지
"""
import json
import sqlite3
from datetime import datetime

from pa.config import ROOT
from pa.model import KST, Task, now, parse_dt

PATH = ROOT / "data" / "pa.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  key TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  kind TEXT NOT NULL,
  course TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL,
  due TEXT,
  earliest TEXT,
  minutes INTEGER NOT NULL,
  minutes_override INTEGER,
  url TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',   -- open | done | ignored | gone
  status_by TEXT NOT NULL DEFAULT 'auto', -- auto | cli | inbox
  first_seen TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  done_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  type TEXT NOT NULL,
  key TEXT,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS plan (
  key TEXT PRIMARY KEY,
  start TEXT NOT NULL,
  end TEXT NOT NULL,
  summary TEXT NOT NULL,
  event_id TEXT
);
CREATE TABLE IF NOT EXISTS busy (start TEXT NOT NULL, end TEXT NOT NULL, label TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS jobs (               -- 에이전트 작업 (보고서 초안 등)
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,                           -- report | …
  key TEXT,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',        -- queued | running | done | failed
  step TEXT NOT NULL DEFAULT '',
  result TEXT,                                  -- 결과 파일 경로
  error TEXT,
  claude INTEGER NOT NULL DEFAULT 0,            -- Claude(구독) 호출 횟수
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notices (            -- Canvas 과목 공지
  id TEXT PRIMARY KEY,
  course TEXT NOT NULL,
  title TEXT NOT NULL,
  text TEXT NOT NULL,
  posted_at TEXT NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'new',           -- new | read
  summary TEXT                                  -- 🤖 한 줄 요약 (버튼을 눌렀을 때만)
);
CREATE TABLE IF NOT EXISTS sessions (           -- 실제로 한 시간 (⏱ 시작 ~ 끝)
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL,
  start TEXT NOT NULL,
  end TEXT,                                     -- NULL = 진행 중
  minutes INTEGER
);
"""

FIELDS = ("kind", "course", "title", "due", "earliest", "minutes", "url")


def connect():
    PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def log(conn, type_, key=None, **detail):
    conn.execute("INSERT INTO events (ts, type, key, detail) VALUES (?, ?, ?, ?)",
                 (now().isoformat(), type_, key, json.dumps(detail, ensure_ascii=False) if detail else None))


def get_meta(conn, k, default=None):
    row = conn.execute("SELECT v FROM meta WHERE k = ?", (k,)).fetchone()
    return row["v"] if row else default


def set_meta(conn, k, v):
    conn.execute("INSERT INTO meta (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (k, v))


def sync_source(conn, source, items, mark_missing_gone=False):
    """출처에서 읽은 항목들을 반영하고 변화를 events 에 기록한다.

    items: dict(key, kind, course, title, due, earliest, minutes, url, [done])
    done=True 는 출처가 '이미 끝남'을 알려준 경우 (Canvas 제출 완료 등).
    """
    ts = now().isoformat()
    seen = set()
    for it in items:
        seen.add(it["key"])
        row = conn.execute("SELECT * FROM tasks WHERE key = ?", (it["key"],)).fetchone()
        vals = [it.get(f) for f in FIELDS]
        if row is None:
            status = "done" if it.get("done") else "open"
            conn.execute(
                f"INSERT INTO tasks (key, source, {', '.join(FIELDS)}, status, first_seen, updated_at, done_at)"
                f" VALUES (?, ?, {', '.join('?' * len(FIELDS))}, ?, ?, ?, ?)",
                (it["key"], source, *vals, status, ts, ts, ts if status == "done" else None))
            if status == "open":
                log(conn, "task_added", it["key"], title=it["title"], source=source)
            continue
        if row["due"] != it.get("due") and row["status"] == "open":
            log(conn, "due_changed", it["key"], old=row["due"], new=it.get("due"))
        conn.execute(f"UPDATE tasks SET {', '.join(f + ' = ?' for f in FIELDS)}, updated_at = ? WHERE key = ?",
                     (*vals, ts, it["key"]))
        if row["status"] == "gone":
            set_status(conn, it["key"], "open", "auto")
        if it.get("done") and row["status"] == "open":
            set_status(conn, it["key"], "done", "auto")
    if mark_missing_gone:
        for row in conn.execute("SELECT key, status FROM tasks WHERE source = ? AND status IN ('open', 'ignored')",
                                (source,)).fetchall():
            if row["key"] not in seen:
                set_status(conn, row["key"], "gone", "auto")


def set_status(conn, key, status, by):
    row = conn.execute("SELECT status FROM tasks WHERE key = ?", (key,)).fetchone()
    if row is None or row["status"] == status:
        return False
    conn.execute("UPDATE tasks SET status = ?, status_by = ?, done_at = ?, updated_at = ? WHERE key = ?",
                 (status, by, now().isoformat() if status == "done" else None, now().isoformat(), key))
    log(conn, {"open": "task_reopened", "done": "task_done", "ignored": "task_ignored",
               "gone": "task_removed"}[status], key, by=by)
    return True


def to_task(row):
    return Task(
        key=row["key"], kind=row["kind"], course=row["course"], title=row["title"],
        due=parse_dt(row["due"]), minutes=row["minutes_override"] or row["minutes"], url=row["url"],
        earliest=parse_dt(row["earliest"]), source=row["source"], status=row["status"])


def tasks(conn, where="1", params=()):
    rows = conn.execute(f"SELECT * FROM tasks WHERE {where} ORDER BY due IS NULL, due", params).fetchall()
    return [to_task(r) for r in rows]


# ---- 시간 기록 (⏱) ---------------------------------------------------------

def active_session(conn):
    return conn.execute("SELECT * FROM sessions WHERE end IS NULL ORDER BY id DESC LIMIT 1").fetchone()


def start_session(conn, key):
    """하나만 진행한다 — 다른 게 진행 중이면 먼저 끝낸다."""
    stop_session(conn)
    conn.execute("INSERT INTO sessions (key, start) VALUES (?, ?)",
                 (key, datetime.now(KST).isoformat(timespec="seconds")))
    log(conn, "session_start", key)


def stop_session(conn):
    """진행 중인 기록을 끝내고 (키, 분) 을 돌려준다. 1분 미만은 버린다."""
    row = active_session(conn)
    if not row:
        return None
    t_end = datetime.now(KST).replace(microsecond=0)
    minutes = int((t_end - parse_dt(row["start"])).total_seconds() // 60)
    if minutes < 1:
        conn.execute("DELETE FROM sessions WHERE id = ?", (row["id"],))
        return None
    conn.execute("UPDATE sessions SET end = ?, minutes = ? WHERE id = ?", (t_end.isoformat(), minutes, row["id"]))
    log(conn, "session_end", row["key"], minutes=minutes)
    return row["key"], minutes


def prune_events(conn, days=365):
    """오래된 자동 기록 지우기 (하루 한 번, 전체 동기화 때). 지운 개수."""
    from datetime import timedelta
    n = conn.execute("DELETE FROM events WHERE ts < ?", ((now() - timedelta(days=days)).isoformat(),)).rowcount
    set_meta(conn, "events_pruned_at", now().isoformat())
    conn.commit()
    return n
