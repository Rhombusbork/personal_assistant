"""두 PC 같이 쓰기 — .env 의 PA_STATE_REPO (비공개 git 저장소)가 있을 때만. 없으면 PC 한 대처럼 동작한다.

- 한 번에 한 PC(일하는 PC)만 엔진 일을 한다: Canvas·계획·캘린더·휴대폰 화면·휴대폰 입력. 다른 PC 는 대기.
  둘 다 켜져 있으면 .env 의 PA_PRIORITY 가 큰 PC 가 일한다 (같으면 먼저 일하던 PC). 일하는 PC 소식이 10분 없으면 이어받는다.
- 대기 PC 에서 한 입력(대시보드 버튼·inbox.md 고치기)은 그 PC 에도 바로 보이고, 저장소를 거쳐 일하는 PC 가 다시 실행한다.
  일하는 PC 가 다 받았다고 적으면(acks) 대기 PC 는 일하는 PC 의 기록으로 맞춘다.
- 저장소 (이 PC 에는 data/state 에 받아 둠 — 매번 GitHub 것으로 맞춘 뒤 내 몫을 적어 올리므로 지워도 된다):
  leader.json               일하는 PC · 우선순위 · 마지막 신호
  peers/<PC>.json           각 PC 의 마지막 신호 · 우선순위
  db/<표>.jsonl             일하는 PC 의 DB (첫 줄은 칸 이름). jobs 와 PC 마다 다른 meta(autoopen:…) 는 빼고
  inbox.md                  일하는 PC 의 inbox.md
  ops/<PC>.jsonl, acks.json 대기 PC 의 입력 / 일하는 PC 가 어디까지 실행했는지
  config/*.yaml, config/profile.md   설정 — 어느 PC 에서 고쳐도 다른 PC 로 (양쪽에서 같은 파일을 고쳤으면 이 PC 것을 두고,
                            GitHub 쪽은 data/peer-conflict/ 에 남김)
- 비밀(.env, token.json, credentials.json, 로그인 상태)은 올리지 않는다. PC 마다 따로.
"""
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from pa import osutil
from pa.config import ROOT, load_env

STALE = 600          # 일하는 PC 신호가 이만큼(초) 없으면 다른 PC 가 이어받는다
BEAT = 180           # 신호 간격
CONFIRM = STALE - BEAT - 60  # 마지막 확인이 이보다 오래면 스스로 일하는 PC 라고 믿지 않는다 (잠들었다 깬 직후 등)
TICK = 30            # 엔진이 저장소와 맞추는 간격
LOCAL_TABLES = {"jobs", "sqlite_sequence"}
LOCAL_META = ("autoopen:", "peer_")
# 대기 PC 에서 일하는 PC 로 넘기는 대시보드 요청 (공유 기록을 바꾸는 것). 창 열기·파일·다운로드 정리·에이전트 작업은 그 PC 에서만
SHARED_ACTIONS = {
    "/api/add", "/api/done", "/api/ignore", "/api/redo", "/api/undone", "/api/exam-add", "/api/keep", "/api/unignore",
    "/api/remove", "/api/today", "/api/quick", "/api/timer/start", "/api/timer/stop", "/api/worklog/add",
    "/api/worklog/delete", "/api/notice/read", "/api/suggest/dismiss", "/api/ack", "/api/exam-dismiss", "/api/link",
    "/api/unlink", "/api/report-brief", "/api/report-file", "/api/defaults", "/api/sync", "/api/move", "/api/unslot",
}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _replay_http(action, body):
    """일하는 PC: 대기 PC 의 입력을 내 대시보드 서버에 그대로 보낸다 (처리하는 코드는 한 곳)."""
    import urllib.request
    from pa import server
    req = urllib.request.Request(f"http://localhost:{server.PORT}{action}", data=json.dumps(body).encode(), method="POST",
                                 headers={"X-PA": "1", "Content-Type": "application/json", "Host": f"localhost:{server.PORT}"})
    urllib.request.urlopen(req, timeout=60).read()


def merge_text(cur, base, new):
    """inbox.md 3방향 합치기 (git merge-file). 겹치면 None."""
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for name, text in (("cur", cur), ("base", base), ("new", new)):
            p = Path(d) / name
            p.write_text(text, encoding="utf-8")
            paths.append(str(p))
        r = subprocess.run(["git", "merge-file", "-p", *paths], capture_output=True, text=True, encoding="utf-8")
        return r.stdout if r.returncode == 0 else None


class Peer:
    def __init__(self, root=ROOT, remote=None, host=None, priority=None, replay=None, log=None):
        load_env()
        self.root = Path(root)
        self.data = self.root / "data"
        self.dir = self.data / "state"
        self.remote = (remote if remote is not None else os.environ.get("PA_STATE_REPO", "")).strip()
        self.host = (host or os.environ.get("PA_HOST", "").strip() or socket.gethostname()).replace("/", "_")
        self.priority = int(priority if priority is not None else (os.environ.get("PA_PRIORITY") or 1))
        self.replay = replay or _replay_http
        self.log = log or (lambda m: None)
        self.local_path = self.data / "peer.json"  # 이 PC 만의 상태: 역할 · 마지막 확인 · 보낼 입력 · 기준
        self._mem = threading.Lock()
        self._handing = False  # 넘겨주는 중 — 그동안은 캘린더를 쓰지 않는다
        self._taking = False   # 넘겨받는 중 (올리기는 성공) — 다시 실행하는 입력을 또 보낼 목록에 넣지 않게

    # ── 이 PC 의 상태 ──────────────────────────────────────────────
    def enabled(self):
        return bool(self.remote)

    def local(self):
        try:
            st = json.loads(self.local_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            st = {}
        if st.get("host") != self.host:  # 다른 PC 에서 복사해 온 파일 → 역할·입력은 믿지 않는다 (설정 기준만 둠)
            st = {"host": self.host, "config_base": st.get("config_base", {})}
        st.setdefault("role", "")
        st.setdefault("confirmed", 0)
        st.setdefault("outbox", [])
        st.setdefault("next_id", 1)
        st.setdefault("applied", {})
        st.setdefault("config_base", {})
        return st

    def _save(self, st):
        self.data.mkdir(exist_ok=True)
        tmp = self.local_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.local_path)

    def is_leader(self):
        """이 PC 가 지금 엔진 일(Canvas·계획·캘린더·휴대폰)을 해도 되나. 같이 쓰기가 꺼져 있으면 늘 그렇다."""
        if not self.enabled():
            return True
        if self._handing:
            return False
        if self._taking:
            return True
        st = self.local()
        return st["role"] == "leader" and time.time() - st["confirmed"] < CONFIRM

    def status(self):
        st = self.local()
        leader = self._read_json(self.dir / "leader.json") or {}
        return {"enabled": self.enabled(), "host": self.host, "priority": self.priority, "leader": self.is_leader(),
                "leader_host": leader.get("host"), "leader_at": leader.get("at"), "pending": len(st["outbox"]),
                "confirmed": st["confirmed"]}

    # ── 대기 PC 의 입력 ─────────────────────────────────────────────
    def queue(self, action, body):
        """대기 PC 에서 한 입력을 보낼 목록에 (다음 맞추기 때 저장소로). inbox 기준도 지금 것으로."""
        with self._mem:
            st = self.local()
            st["outbox"].append({"id": st["next_id"], "action": action, "body": body, "at": time.time()})
            st["next_id"] += 1
            st["inbox_base"] = self._inbox_text()
            self._save(st)

    def inbox_changed(self):
        """대기 PC 에서 inbox.md 를 직접 고쳤으면 (기준과 다르면) 그 차이를 일하는 PC 로. 보냈으면 True."""
        if not self.enabled() or self.is_leader():
            return False
        with self._mem:
            st = self.local()
            cur, base = self._inbox_text(), st.get("inbox_base")
            if base is None or cur == base:
                return False
            st["outbox"].append({"id": st["next_id"], "action": "inbox", "body": {"base": base, "new": cur}, "at": time.time()})
            st["next_id"] += 1
            st["inbox_base"] = cur
            self._save(st)
            return True

    def _inbox_text(self):
        p = self.root / "inbox.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # ── git ───────────────────────────────────────────────────────
    def _git(self, *args, check=True):
        r = subprocess.run(["git", "-C", str(self.dir), "-c", f"user.name=pa-{self.host}", "-c", "user.email=pa@localhost",
                            *args], capture_output=True, text=True, encoding="utf-8", timeout=120)
        if check and r.returncode != 0:
            raise RuntimeError(f"git {args[0]}: {(r.stderr or r.stdout).strip()[:200]}")
        return r

    def _fresh_copy(self):
        """저장소 사본을 GitHub 것과 똑같이 (내 커밋이 밀렸으면 버림 — 내 몫은 매번 다시 적는다)."""
        if not (self.dir / ".git").exists():
            self.data.mkdir(exist_ok=True)
            shutil.rmtree(self.dir, ignore_errors=True)
            r = subprocess.run(["git", "clone", "-q", self.remote, str(self.dir)], capture_output=True, text=True,
                               encoding="utf-8", timeout=300)
            if r.returncode != 0:
                raise RuntimeError(f"git clone: {r.stderr.strip()[:200]}")
        self._git("fetch", "-q", "origin")
        if self._git("rev-parse", "--verify", "-q", "origin/main", check=False).returncode == 0:
            self._git("checkout", "-q", "-B", "main", "origin/main")
            self._git("reset", "-q", "--hard", "origin/main")
        else:  # 빈 저장소
            if self._git("rev-parse", "--verify", "-q", "HEAD", check=False).returncode != 0:
                self._git("checkout", "-q", "--orphan", "main", check=False)
        self._git("clean", "-q", "-fd")

    def _push(self, msg):
        """바뀐 게 있으면 커밋·push. (True, 커밋함) / 밀리면 (False, …)."""
        self._git("add", "-A")
        if self._git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return True, False
        self._git("commit", "-q", "-m", msg)
        return self._git("push", "-q", "origin", "HEAD:main", check=False).returncode == 0, True

    # ── 맞추기 ────────────────────────────────────────────────────
    def tick(self):
        """저장소와 한 번 맞춘다. 무슨 일이 있었는지 dict 로 (became: leader/standby, restored, replayed, warnings)."""
        if not self.enabled():
            return {}
        self.data.mkdir(exist_ok=True)
        with open(self.data / "peer.lock", "a", encoding="utf-8") as lf:
            osutil.lock(lf)
            last = None
            for _ in range(4):  # 다른 PC 가 먼저 올렸으면 GitHub 것으로 다시 맞춘 뒤 다시
                self._fresh_copy()
                with self._mem:
                    st = self.local()
                res, after = self._step(st)
                ok, committed = self._push(f"{self.host}: {res.get('note', 'sync')}")
                if ok:
                    self._finish(st, res, after)
                    return res
                last = res
            raise RuntimeError("저장소에 올리지 못함 (다른 PC 와 계속 겹침)" + (f" — {last}" if last else ""))

    def _finish(self, st, res, after):
        """올리기에 성공한 뒤: 역할 바꾸기·기록 받기, 그리고 맞추는 사이 들어온 입력을 합쳐 저장."""
        st["confirmed"] = time.time()
        self._taking = res.get("became") == "leader"
        try:
            for fn in after:
                fn(st)
            self._handing = False
            self._merge_saved(st, res)
        finally:
            self._taking = False

    def _merge_saved(self, st, res):
        with self._mem:
            cur = self.local()
            known = {o["id"] for o in res["outbox_seen"]}
            late = [o for o in cur["outbox"] if o["id"] not in known]
            redo = late if st["role"] == "leader" and res.get("became") == "leader" else []
            if st["role"] == "leader":  # 일하는 PC 의 입력은 이미 이 PC 에 적용됨
                st["outbox"] = []
            else:
                st["outbox"] = [o for o in st["outbox"] if o["id"] > res.get("acked", 0)] + late
            st["next_id"] = max(st["next_id"], cur["next_id"])
            if late and not res.get("restored"):
                st["inbox_base"] = cur.get("inbox_base")
            self._save(st)
        for o in redo:  # 넘겨받는 순간 들어온 입력 — 받아 온 기록에 덮였을 수 있어 다시 실행
            try:
                self._apply(o)
            except Exception as e:
                self.log(f"두 PC: 입력 다시 실행 실패 ({o['action']}): {str(e)[:80]}")

    def _step(self, st):
        """GitHub 최신 상태를 보고 이번에 할 일을 정해 사본에 적는다. 올린 뒤에 할 일은 after 로."""
        now = time.time()
        self._handing = False
        res, after = {"warnings": []}, []
        res["outbox_seen"] = list(st["outbox"])
        res["warnings"] += self._sync_config(st)
        leader = self._read_json(self.dir / "leader.json")
        peers = {p.stem: self._read_json(p) or {} for p in (self.dir / "peers").glob("*.json")} if (self.dir / "peers").exists() else {}
        acks = self._read_json(self.dir / "acks.json") or {}
        mine = bool(leader) and leader.get("host") == self.host
        fresh = bool(leader) and now - float(leader.get("at", 0)) < STALE
        # 내 신호
        me = peers.get(self.host) or {}
        if now - float(me.get("at", 0)) >= BEAT or me.get("priority") != self.priority:
            self._write_json(self.dir / "peers" / f"{self.host}.json", {"priority": self.priority, "at": now})

        if mine:
            better = sorted(((float(p.get("priority", 0)), h) for h, p in peers.items()
                             if h != self.host and now - float(p.get("at", 0)) < STALE
                             and float(p.get("priority", 0)) > self.priority), reverse=True)
            if better and st["role"] == "leader":  # 우선순위가 높은 PC 가 켜져 있음 → 넘겨준다 (마지막 기록을 올리고)
                to = better[0][1]  # 그 PC 의 입력은 그 PC 가 넘겨받은 뒤 스스로 다시 실행한다
                self._handing = True
                with self._run_lock():
                    self._dump()
                    self._write_json(self.dir / "leader.json", {"host": to, "priority": better[0][0], "at": now, "from": self.host})
                res.update(note=f"hand over to {to}", became="standby")
                after.append(lambda s: self._now_standby(s))
                return res, after
            if st["role"] != "leader":  # 넘겨받음 (또는 이 PC 가 일하는 PC 였는데 잠깐 대기였음)
                if leader.get("from") and leader.get("from") != self.host:
                    after.append(lambda s: self._take_over(s, restore=True))
                else:
                    after.append(lambda s: self._take_over(s, restore=False))
                res["became"] = "leader"
            else:  # 넘겨받은 바로 그 차례에는 기록만 받고, 다른 PC 입력은 다음 차례에
                self._replay_others(st, acks, res)
            self._dump()
            if now - float(leader.get("at", 0)) >= BEAT or leader.get("priority") != self.priority or "from" in leader:
                self._write_json(self.dir / "leader.json", {"host": self.host, "priority": self.priority, "at": now})
            res["note"] = "leader"
            return res, after

        if not fresh:  # 일하는 PC 가 없거나 오래 소식이 없음 → 이어받는다
            had = bool(leader) and (self.dir / "db").exists()
            self._write_json(self.dir / "leader.json", {"host": self.host, "priority": self.priority, "at": now})
            if not had:  # 처음: 이 PC 의 기록이 시작점
                self._dump()
            res.update(note="take over", became="leader")
            after.append(lambda s: self._take_over(s, restore=had))
            return res, after

        # 대기: 내 입력을 올리고, 일하는 PC 가 다 받았으면 그 기록으로 맞춘다
        if st["role"] != "standby":
            res["became"] = "standby"
        ops = st["outbox"]
        ack = int(acks.get(self.host, 0))
        pending = [o for o in ops if o["id"] > ack]
        path = self.dir / "ops" / f"{self.host}.jsonl"
        if pending:
            path.parent.mkdir(exist_ok=True)
            path.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in pending), encoding="utf-8")
        elif path.exists():
            path.unlink()
        res.update(acked=ack, note="standby")
        tree = self._tree()
        if not pending and tree and tree != st.get("restored"):
            after.append(lambda s: self._restore(s))
            res["restored"] = True
        after.append(lambda s: s.update(role="standby"))
        return res, after

    # ── 역할 바꾸기 ────────────────────────────────────────────────
    def _now_standby(self, st):
        st["role"] = "standby"
        st["restored"] = self._tree()
        st["inbox_base"] = self._inbox_text()
        self.log(f"두 PC: 우선순위가 높은 PC 에 일을 넘김 — 이 PC 는 대기")

    def _take_over(self, st, restore):
        if restore:
            self._restore(st)
            mine = list(st["outbox"])  # 대기 때 한 입력 — 이 PC 에는 적용했지만 방금 맞추면서 덮였다 → 다시 실행
            for o in mine:
                try:
                    self._apply(o)
                except Exception as e:
                    self.log(f"두 PC: 대기 때 입력 다시 실행 실패 ({o['action']}): {str(e)[:80]}")
        st["outbox"] = []
        st["role"] = "leader"
        self.log("두 PC: 이 PC 가 일하는 PC" + (" (기록을 받아 옴)" if restore else ""))

    def _replay_others(self, st, acks, res):
        """다른 PC(대기)의 입력을 순서대로 실행하고 acks 에 적는다. 하나가 실패하면 그 PC 는 다음에 이어서."""
        n = 0
        for p in sorted((self.dir / "ops").glob("*.jsonl")) if (self.dir / "ops").exists() else []:
            host = p.stem
            if host == self.host:
                p.unlink()
                continue
            done = max(int(acks.get(host, 0)), int(st["applied"].get(host, 0)))
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                o = json.loads(line)
                if o["id"] <= done:
                    continue
                try:
                    self._apply(o)
                except Exception as e:
                    res["warnings"].append(f"{host} 입력 실행 실패 ({o['action']}): {str(e)[:80]}")
                    break
                done = o["id"]
                st["applied"][host] = done
                n += 1
            acks[host] = done
        if n or acks:
            self._write_json(self.dir / "acks.json", acks)
        res["replayed"] = n
        if n:
            with self._mem:  # 다시 실행해 적은 기록이 맞추는 중에 사라지지 않게 바로 저장
                cur = self.local()
                cur["applied"] = st["applied"]
                self._save(cur)

    def _apply(self, o):
        if o["action"] == "inbox":
            p = self.root / "inbox.md"
            cur = self._inbox_text()
            merged = merge_text(cur, o["body"]["base"], o["body"]["new"])
            if merged is None:
                raise ValueError("다른 PC 의 inbox.md 수정이 이 PC 수정과 겹침 — 직접 확인")
            if merged != cur:
                p.write_text(merged, encoding="utf-8")
            return
        self.replay(o["action"], o["body"])

    def _run_lock(self):
        """엔진이 계획·캘린더를 쓰는 중이면 끝날 때까지 기다린다 (넘겨줄 때 마지막 기록이 빠지지 않게)."""
        class L:
            def __enter__(s):
                s.f = open(self.data / "run.lock", "a", encoding="utf-8")
                osutil.lock(s.f)

            def __exit__(s, *a):
                s.f.close()
        return L()

    # ── DB 올리기·받기 ────────────────────────────────────────────
    def _conn(self):
        conn = sqlite3.connect(self.data / "pa.db", timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _tables(self, conn):
        return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
                if r[0] not in LOCAL_TABLES]

    def _dump(self):
        if not (self.data / "pa.db").exists():
            return
        out = self.dir / "db"
        out.mkdir(parents=True, exist_ok=True)
        conn = self._conn()
        try:
            names = self._tables(conn)
            for t in names:
                cur = conn.execute(f"SELECT * FROM {t} ORDER BY rowid")
                cols = [d[0] for d in cur.description]
                rows = [list(r) for r in cur]
                if t == "meta":
                    rows = [r for r in rows if not str(r[0]).startswith(LOCAL_META)]
                lines = [json.dumps(cols, ensure_ascii=False)] + [json.dumps(r, ensure_ascii=False) for r in rows]
                (out / f"{t}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
            for p in out.glob("*.jsonl"):
                if p.stem not in names:
                    p.unlink()
        finally:
            conn.close()
        src = self.root / "inbox.md"
        if src.exists():
            shutil.copyfile(src, self.dir / "inbox.md")

    def _tree(self):
        """저장소의 DB·inbox 판 (바뀌었는지 비교용)."""
        r = self._git("rev-parse", "HEAD:db", check=False)
        if r.returncode != 0:
            return None
        return r.stdout.strip() + ":" + str(_sha(self.dir / "inbox.md"))

    def _restore(self, st):
        """저장소의 DB·inbox 로 이 PC 를 맞춘다 (jobs 와 PC 마다 다른 meta 는 그대로)."""
        src = self.dir / "db"
        if not src.exists():
            return
        from pa import db as padb
        conn = self._conn()
        try:
            conn.executescript(padb.SCHEMA)
            have = set(self._tables(conn))
            with conn:
                for p in sorted(src.glob("*.jsonl")):
                    t = p.stem
                    if t not in have:
                        continue
                    lines = p.read_text(encoding="utf-8").splitlines()
                    cols = json.loads(lines[0])
                    mine = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
                    use = [i for i, c in enumerate(cols) if c in mine]
                    if t == "meta":
                        conn.execute("DELETE FROM meta WHERE " + " AND ".join("k NOT LIKE ?" for _ in LOCAL_META),
                                     [f"{x}%" for x in LOCAL_META])
                    else:
                        conn.execute(f"DELETE FROM {t}")
                    names = ", ".join(cols[i] for i in use)
                    marks = ", ".join("?" for _ in use)
                    conn.executemany(f"INSERT OR REPLACE INTO {t} ({names}) VALUES ({marks})",
                                     ([json.loads(x)[i] for i in use] for x in lines[1:] if x.strip()))
        finally:
            conn.close()
        if (self.dir / "inbox.md").exists():
            shutil.copyfile(self.dir / "inbox.md", self.root / "inbox.md")
        st["restored"] = self._tree()
        st["inbox_base"] = self._inbox_text()

    # ── 설정 파일 ────────────────────────────────────────────────
    def _config_names(self):
        names = set()
        for d in (self.root / "config", self.dir / "config"):
            if d.exists():
                names |= {p.name for p in d.glob("*.yaml") if not p.name.endswith(".example.yaml")}
                if (d / "profile.md").exists():
                    names.add("profile.md")
        return sorted(names)

    def _sync_config(self, st):
        """3방향: 이 PC 에서만 바뀜 → 올림 / GitHub 에서만 바뀜 → 받음 / 둘 다 → 이 PC 것을 두고 GitHub 것은 따로 보관."""
        warns = []
        base = st["config_base"]
        for name in self._config_names():
            mine, theirs = self.root / "config" / name, self.dir / "config" / name
            lh, rh, bh = _sha(mine), _sha(theirs), base.get(name)
            if lh == rh:
                base[name] = lh
            elif rh == bh and lh:  # 이 PC 에서 고침
                theirs.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(mine, theirs)
                base[name] = lh
            elif lh == bh and rh:  # 다른 PC 에서 고침
                mine.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(theirs, mine)
                base[name] = rh
                self.log(f"두 PC: 다른 PC 에서 고친 설정 받음 — config/{name}")
            elif lh and rh:  # 양쪽에서 고침
                keep = self.data / "peer-conflict"
                keep.mkdir(exist_ok=True)
                shutil.copyfile(theirs, keep / name)
                shutil.copyfile(mine, theirs)
                base[name] = lh
                warns.append(f"config/{name} 을 두 PC 에서 고침 — 이 PC 것을 씀 (다른 PC 것: data/peer-conflict/{name})")
            elif lh:  # GitHub 에 없음
                theirs.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(mine, theirs)
                base[name] = lh
            elif rh:  # 이 PC 에 없음
                mine.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(theirs, mine)
                base[name] = rh
        for w in warns:
            self.log(f"⚠️ 두 PC: {w}")
        return warns

    @staticmethod
    def _read_json(p):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    @staticmethod
    def _write_json(p, obj):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


_default = {}


def get():
    """이 PC 의 Peer (엔진·대시보드·명령이 함께 씀). .env 가 바뀌면 (bin/pa peer init 등) 다시 읽는다."""
    env = ROOT / ".env"
    m = env.stat().st_mtime if env.exists() else 0
    if "p" not in _default or _default.get("m") != m:
        if "p" in _default:
            for k in ("PA_STATE_REPO", "PA_PRIORITY", "PA_HOST"):
                os.environ.pop(k, None)
        _default.update(p=Peer(), m=m)
    return _default["p"]


def is_leader():
    return get().is_leader()


def enabled():
    return get().enabled()


def standby():
    """같이 쓰기가 켜져 있고 이 PC 가 대기 중."""
    p = get()
    return p.enabled() and not p.is_leader()
