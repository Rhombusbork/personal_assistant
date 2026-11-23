"""휴대폰 보기 (GitHub Pages): config/mobile.yaml 의 pages_url

- gh-pages 브랜치: 대시보드 화면 + 비밀번호로 잠근 데이터(data.enc.json). 올릴 때마다 이력 없이 덮어쓴다.
- phone-inbox 브랜치: 휴대폰에서 한 입력(추가·완료·제외·오늘 하기)도 잠가서 phone-inbox.json 에 쌓인다.
  엔진이 몇 분마다 읽어 inbox.md 에 반영한다 (엔진은 읽기만, 쓰는 건 휴대폰).
- 잠금: 비밀번호 → PBKDF2-SHA256 → AES-GCM. 비밀번호는 .env 의 PA_MOBILE_PASSWORD.
"""
import base64
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from pa import db, inbox, render
from pa.config import ROOT, load_env, load_yaml
from pa.model import KST, now

ITER = 200_000
PUB = ROOT / "data" / "publish"
SITE_FILES = ["index.html", "manifest.webmanifest", "icon.svg"]


def cfg():
    return load_yaml("mobile")


def enabled():
    """휴대폰 기능은 config/mobile.yaml 에 내 저장소(repo)를 적고 .env 에 PA_MOBILE_PASSWORD 가 있을 때만.
    견본은 repo 가 비어 있어, 받은 사람은 꺼진 채로 시작하고 남의 저장소에 올리거나 읽지 않는다."""
    load_env()
    return bool(cfg().get("repo")) and bool(os.environ.get("PA_MOBILE_PASSWORD"))


def password():
    load_env()
    pw = os.environ.get("PA_MOBILE_PASSWORD")
    if not pw:
        raise RuntimeError(".env 에 PA_MOBILE_PASSWORD 가 없습니다")
    return pw


def _key(pw, salt, it=ITER):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=it).derive(pw.encode())


def encrypt(obj, pw):
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(_key(pw, salt)).encrypt(iv, json.dumps(obj, ensure_ascii=False).encode(), None)
    b = lambda x: base64.b64encode(x).decode()
    return {"v": 1, "iter": ITER, "salt": b(salt), "iv": b(iv), "ct": b(ct)}


def decrypt(box, pw):
    d = lambda k: base64.b64decode(box[k])
    return json.loads(AESGCM(_key(pw, d("salt"), box.get("iter", ITER))).decrypt(d("iv"), d("ct"), None))


# ---- 올리기 ------------------------------------------------------------------

def _git(*args, cwd=PUB, check=True):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120, check=check, encoding="utf-8")


RESULT_MAX = 200_000  # 결과 글 하나 최대 (바이트)


def results(job_list):
    """끝난 작업의 결과 글(보고서 초안·내용정리 .md) → {경로: 글}. 휴대폰 화면의 '열기'가 이것을 보여 준다 (잠가서 올림)."""
    out = {}
    for j in job_list:
        p = Path(j.get("result") or "")
        if j.get("status") == "done" and p.suffix.lower() in (".md", ".txt") and p.is_file() and p.stat().st_size <= RESULT_MAX:
            out[str(p)] = p.read_text(encoding="utf-8", errors="replace")
    return out


def build():
    """data/publish/ 에 올릴 파일들을 만든다. 데이터 해시(시각 제외)를 돌려준다."""
    conn = db.connect()
    try:
        data = render.dashboard_data(conn)
    finally:
        conn.close()
    c = cfg()
    data["mobile"] = {"repo": c["repo"], "inboxBranch": c["inbox_branch"], "inboxFile": c["inbox_file"]}
    data["results"] = results(data.get("jobs") or [])
    stable = {k: v for k, v in data.items() if k not in ("generated", "sessionsToday", "active", "jobs", "downloads")}
    stable["jobs"] = [(j["id"], j["status"]) for j in data.get("jobs") or []]  # 진행 단계는 빼고, 끝났을 때만 다시 올림
    digest = hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    PUB.mkdir(parents=True, exist_ok=True)
    for f in SITE_FILES:
        shutil.copy(ROOT / "dashboard" / f, PUB / f)
    (PUB / "data.enc.json").write_text(json.dumps(encrypt(data, password())), encoding="utf-8")
    (PUB / ".nojekyll").write_text("", encoding="utf-8")
    return digest


def publish(force=False):
    """바뀐 게 있고 최소 간격이 지났으면 gh-pages 로 올린다. 올렸으면 True."""
    if not enabled():
        return False
    c = cfg()
    conn = db.connect()
    try:
        last = float(db.get_meta(conn, "mobile_published_at") or 0)
        last_hash = db.get_meta(conn, "mobile_hash")
    finally:
        conn.close()
    if not force and time.time() - last < c["min_interval_minutes"] * 60:
        return False
    digest = build()
    if not force and digest == last_hash and time.time() - last < 3600:
        return False  # 바뀐 게 없으면 한 시간에 한 번만 (시각 갱신용)
    if (PUB / ".git").exists():
        shutil.rmtree(PUB / ".git")
    _git("init", "-q", "-b", "gh-pages")
    _git("add", "-A")
    _git("commit", "-q", "-m", f"update {datetime.now(KST):%Y-%m-%d %H:%M}")
    _git("push", "-q", "-f", f"https://github.com/{c['repo']}.git", "gh-pages")
    ensure_inbox_branch(c)
    conn = db.connect()
    try:
        db.set_meta(conn, "mobile_published_at", str(time.time()))
        db.set_meta(conn, "mobile_hash", digest)
        conn.commit()
    finally:
        conn.close()
    return True


def ensure_inbox_branch(c):
    """휴대폰 입력용 브랜치가 없으면 빈 파일로 만든다 (한 번만)."""
    url = f"https://github.com/{c['repo']}.git"
    if _git("ls-remote", "--heads", url, c["inbox_branch"], cwd=ROOT).stdout.strip():
        return
    tmp = ROOT / "data" / "phone-inbox-init"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    (tmp / c["inbox_file"]).write_text("[]\n", encoding="utf-8")
    _git("init", "-q", "-b", c["inbox_branch"], cwd=tmp)
    _git("add", "-A", cwd=tmp)
    _git("commit", "-q", "-m", "phone inbox", cwd=tmp)
    _git("push", "-q", url, c["inbox_branch"], cwd=tmp)
    shutil.rmtree(tmp, ignore_errors=True)


# ---- 휴대폰 입력 가져오기 ------------------------------------------------------

def fetch_phone_entries():
    c = cfg()
    url = f"https://api.github.com/repos/{c['repo']}/contents/{c['inbox_file']}?ref={c['inbox_branch']}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "pa"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
    return json.loads(base64.b64decode(body["content"]).decode() or "[]")


def apply_entry(op):
    """휴대폰 입력 하나를 inbox.md 에 반영 (대시보드 버튼과 같은 효과)."""
    from pa.server import parse_add
    kind = op.get("op")
    if kind == "add" and op.get("text"):
        inbox.add_task_line(inbox.quick_line(op["text"]))
    elif kind == "add":
        inbox.add_task(**parse_add(op.get("fields", {})))
    elif kind == "done":
        inbox.mark_done(op["key"])
    elif kind == "ignore" and op.get("pattern"):
        conn = db.connect()
        try:
            inbox.ignore_like(conn, op["key"])
        finally:
            conn.close()
    elif kind == "ignore":
        inbox.ignore(op["key"])
    elif kind == "exam-dismiss":
        from pa import exams
        conn = db.connect()
        try:
            exams.dismiss(conn, op["id"])
        finally:
            conn.close()
    elif kind == "keep":
        inbox.keep(op["key"])
    elif kind == "unignore":
        inbox.unignore(op["text"])
    elif kind == "remove":
        inbox.remove(op["key"])
    elif kind == "undone":
        conn = db.connect()
        try:
            inbox.undone(conn, op["key"])
        finally:
            conn.close()
    elif kind == "redo":
        from pa import plan
        conn = db.connect()
        try:
            plan.set_redo(conn, op["key"], op.get("day") or None)
        finally:
            conn.close()
    elif kind == "today":
        inbox.set_due(op["key"], datetime.now(KST).replace(hour=23, minute=59, second=0, microsecond=0))
    elif kind == "act":  # 대기열: 동기화·보고서 초안·제출·시간 정하기·예약·메모 … (PC 가 켜져 있을 때 실행, 결과는 다음 화면에)
        from pa import server
        if op.get("action") in server.PHONE_HTTP:
            from pa import peer
            peer._replay_http(op["action"], op.get("body") or {})
            return
        if op.get("action") not in server.PHONE_ACTIONS:
            raise ValueError(f"휴대폰에서 맡길 수 없는 요청: {op.get('action')}")
        r = server.side_action(op["action"], op.get("body") or {}, remote=True)
        if not r.get("ok"):
            raise ValueError(r.get("error") or "실패")
    elif kind == "awake":  # ☀️ PC 깨워 두기: 이 시간 동안 절전 안 함 (Remote Control 쓰기)
        from pa import power
        mins = max(10, min(600, int(op.get("minutes") or 60)))
        power.keep_awake(mins)
        conn = db.connect()
        try:
            db.set_meta(conn, "pc_awake_until", (datetime.now(KST) + timedelta(minutes=mins)).isoformat())
            db.set_meta(conn, "pc_sleep_at", "")
            conn.commit()
        finally:
            conn.close()
    elif kind == "sleep":  # 💤 PC 절전: 진행 중인 AI 작업이 끝난 뒤 (엔진이 1분마다 확인)
        conn = db.connect()
        try:
            db.set_meta(conn, "pc_sleep_at", datetime.now(KST).isoformat())
            db.set_meta(conn, "pc_awake_until", "")
            conn.commit()
        finally:
            conn.close()
    else:
        raise ValueError(f"모르는 입력: {kind}")


def pull_phone_inbox():
    """새 휴대폰 입력을 반영. 반영한 수 반환. (처리한 id 는 기억해서 두 번 하지 않는다)"""
    if not enabled():
        return 0
    entries = fetch_phone_entries()
    if not entries:
        return 0
    conn = db.connect()
    try:
        done = set(json.loads(db.get_meta(conn, "phone_processed") or "[]"))
        pw, n = password(), 0
        for e in entries:
            if e.get("id") in done:
                continue
            op = None
            try:
                op = decrypt(e, pw)
                try:
                    apply_entry(op)
                    db.log(conn, "phone_input", None, id=e.get("id"))
                except ValueError as err:
                    # 추가가 '할 시간' 때문에 막히면 할 시간만 빼고라도 넣는다 (입력을 통째로 잃지 않게)
                    if op.get("op") != "add" or not (op.get("fields") or {}).get("sfrom"):
                        raise
                    fields = {k: v for k, v in op["fields"].items() if k not in ("sdate", "sfrom", "sto")}
                    apply_entry({**op, "fields": fields})
                    db.log(conn, "phone_input", None, id=e.get("id"), dropped=f"할 시간 ({err})")
                n += 1
            except Exception as err:  # 하나가 잘못돼도 나머지는 반영
                title = ((op or {}).get("fields") or {}).get("title") or (op or {}).get("text") or ""
                db.log(conn, "phone_input_failed", None, id=e.get("id"), error=str(err)[:200], title=str(title)[:60])
            done.add(e.get("id"))
        db.set_meta(conn, "phone_processed", json.dumps(sorted(done)[-2000:]))
        conn.commit()
    finally:
        conn.close()
    return n
