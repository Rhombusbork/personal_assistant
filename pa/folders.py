"""기본 할 일의 VSCode 폴더 고르기 보조 — 입력하면서 하위 폴더 추천(Tab 완성), 칸을 누르면 후보 목록.

후보: VSCode 에서 최근 연 폴더(workspaceStorage 기록) + 홈 아래 git 저장소. 실제로 있는 폴더만.
Windows·WSL·리눅스 모두: VSCode 기록 위치와 경로 모양(vscode-remote://wsl+…, file:///c%3A/…)을 osutil.KIND 로 맞춘다.
"""
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from pa import osutil

SKIP = {"node_modules", ".venv", "venv", "__pycache__", ".git", ".cache", ".local", ".npm", ".vscode-server",
        "site-packages", "AppData", "snap"}


def _home_short(p):
    home = str(Path.home())
    s = str(p)
    return "~" + s[len(home):] if s == home or s.startswith(home + os.sep) else s


def complete(text, limit=30):
    """'~/qu' → ['~/quiz_system_project'] (그 폴더 안의 하위 폴더, 이름이 그렇게 시작하는 것).
    '~/quiz_system_project/' 처럼 / 로 끝나면 그 안의 하위 폴더 전부. 숨김 폴더는 '.' 을 쳤을 때만."""
    text = (text or "").strip() or "~/"
    full = Path(os.path.expanduser(text))
    if text.endswith(("/", "\\")):
        parent, stem = full, ""
    else:
        parent, stem = full.parent, full.name
    try:
        subs = sorted((d for d in parent.iterdir() if d.is_dir()), key=lambda d: d.name.lower())
    except OSError:
        return []
    low = stem.lower()
    out = [d for d in subs if d.name.lower().startswith(low) and (stem.startswith(".") or not d.name.startswith("."))]
    return [_home_short(d) for d in out[:limit]]


def _vscode_storage_dirs():
    """VSCode 의 workspaceStorage 폴더들 (안정판·Insiders)."""
    if osutil.IS_WINDOWS:
        bases = [Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))]
    elif osutil.IS_WSL:
        users = Path("/mnt/c/Users")
        bases = [u / "AppData/Roaming" for u in (users.iterdir() if users.exists() else [])
                 if u.name not in ("Public", "Default", "Default User", "All Users")]
    else:
        bases = [Path.home() / ".config"]
    return [b / app / "User/workspaceStorage" for b in bases for app in ("Code", "Code - Insiders")]


def _uri_to_path(uri):
    """VSCode 폴더 주소 → 이 컴퓨터에서 쓰는 경로. 다른 환경(예: Windows 쪽 폴더를 WSL 에서)도 되는 만큼."""
    u = urlparse(uri)
    path = unquote(u.path)
    if u.scheme == "vscode-remote" and unquote(u.netloc).lower().startswith("wsl+"):
        return Path(path) if not osutil.IS_WINDOWS else None   # WSL 폴더는 WSL·리눅스 쪽 엔진에서만
    if u.scheme == "file":
        if u.netloc.lower().startswith("wsl"):                    # file://wsl.localhost/Ubuntu/home/…
            parts = path.split("/", 2)
            return Path("/" + parts[2]) if len(parts) > 2 and not osutil.IS_WINDOWS else None
        if len(path) > 2 and path[2] == ":":                      # /c:/Users/…
            drive, rest = path[1].lower(), path[3:]
            if osutil.IS_WINDOWS:
                return Path(f"{drive.upper()}:{rest}")
            return Path(f"/mnt/{drive}{rest}") if osutil.IS_WSL else None
        return Path(path)
    return None


def recent_vscode(limit=15):
    found = []
    for base in _vscode_storage_dirs():
        try:
            entries = list(base.iterdir())
        except OSError:
            continue
        for d in entries:
            f = d / "workspace.json"
            try:
                uri = json.loads(f.read_text(encoding="utf-8")).get("folder")
                found.append((f.stat().st_mtime, uri))
            except (OSError, ValueError):
                continue
    out = []
    for _, uri in sorted(found, reverse=True):
        p = uri and _uri_to_path(uri)
        if p and p.is_dir() and p not in out:
            out.append(p)
    return out[:limit]


def git_repos(root=None, depth=3, limit=30):
    """홈 아래(깊이 3까지) .git 이 있는 폴더."""
    root = Path(root or Path.home())
    out = []

    def walk(d, n):
        if len(out) >= limit:
            return
        try:
            subs = [x for x in d.iterdir() if x.is_dir()]
        except OSError:
            return
        if any(x.name == ".git" for x in subs):
            out.append(d)
            return  # 저장소 안은 더 내려가지 않는다
        if n < depth:
            for x in sorted(subs, key=lambda x: x.name.lower()):
                if not x.name.startswith(".") and x.name not in SKIP:
                    walk(x, n + 1)
    walk(root, 0)
    return out


def suggestions():
    """[{path, why}] — VSCode 최근 폴더 먼저, 그다음 git 저장소."""
    seen, out = set(), []
    for p, why in [(p, "VSCode 최근") for p in recent_vscode()] + [(p, "git 저장소") for p in git_repos()]:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append({"path": _home_short(p), "why": why})
    return out
