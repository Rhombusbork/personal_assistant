"""운영체제마다 다른 일 — 링크·파일 열기, 탐색기, 다운로드 폴더, 실행 잠금.

세 환경을 지원한다. 나머지 코드는 이 모듈만 부르고 환경을 따지지 않는다.
  wsl      WSL 안의 리눅스: Windows 브라우저·탐색기(explorer.exe)로 연다, 다운로드는 /mnt/c/Users/<나>/Downloads
  windows  Windows 의 Python 그대로: os.startfile·explorer, 다운로드는 ~/Downloads
  linux    그 밖 (리눅스·Mac): 기본 프로그램(xdg-open / open), 다운로드는 ~/Downloads
"""
import os
import platform
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

IS_WINDOWS = os.name == "nt"
IS_WSL = not IS_WINDOWS and "microsoft" in platform.uname().release.lower()
KIND = "windows" if IS_WINDOWS else "wsl" if IS_WSL else "linux"


def _spawn(cmd):
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _win_path(path):
    """WSL 경로 → Windows 경로 (\\\\wsl.localhost\\… 또는 C:\\…)."""
    return subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True, encoding="utf-8").stdout.strip()


def open_url(url):
    """기본 브라우저로 링크를 연다 (학교 로그인이 남아 있는 평소 브라우저)."""
    if IS_WSL:
        _spawn(["explorer.exe", url])
    elif IS_WINDOWS:
        os.startfile(url)
    else:
        webbrowser.open(url)


def open_app(url):
    """대시보드를 주소창 없는 '앱 창'으로 연다 (Edge/Chrome 의 --app). 없으면 보통 브라우저 탭."""
    if IS_WSL or IS_WINDOWS:
        cmd = ["cmd.exe" if IS_WSL else "cmd", "/c", "start", "", "msedge", f"--app={url}"]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=20, **({"cwd": "/mnt/c"} if IS_WSL else {}))
            if r.returncode == 0:
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
        return open_url(url)
    import shutil
    for b in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        if shutil.which(b):
            return _spawn([b, f"--app={url}"])
    webbrowser.open(url)


def _ps(script):
    """Windows PowerShell 한 덩어리 실행 (WSL·Windows). (성공, 출력)"""
    exe = "powershell.exe" if IS_WSL else "powershell"
    script = "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + script  # 한글 출력이 깨지지 않게
    r = subprocess.run([exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                       **({"cwd": "/mnt/c"} if IS_WSL else {}))
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def _vscode_target(folder):
    """(PowerShell 에서 Code.exe 를 찾는 코드, 넘길 인자) — 바로가기·VSCode 열기 공통."""
    folder = Path(folder).resolve()
    if IS_WSL:
        args = f"--folder-uri vscode-remote://wsl+{os.environ.get('WSL_DISTRO_NAME', 'Ubuntu')}{folder.as_posix()}"
    else:
        args = f'"{folder}"'
    find = """
$code = (Get-Command code.cmd -ErrorAction SilentlyContinue).Source
if ($code) { $exe = Join-Path (Split-Path (Split-Path $code)) 'Code.exe' }
if (-not $exe -or -not (Test-Path $exe)) { $exe = Join-Path $env:LOCALAPPDATA 'Programs/Microsoft VS Code/Code.exe' }
if (-not (Test-Path $exe)) { throw 'VSCode(Code.exe)를 찾지 못했습니다' }
"""
    return find, args


def launch_vscode(folder):
    """VSCode 로 이 폴더를 연다 (이미 열려 있으면 그 창이 앞으로)."""
    if IS_WSL or IS_WINDOWS:
        find, args = _vscode_target(folder)
        ok, out = _ps("$ErrorActionPreference = 'Stop'\n" + find + f"Start-Process -FilePath $exe -ArgumentList '{args}'")
        if not ok:
            raise RuntimeError(out.splitlines()[-1] if out else "VSCode 를 열지 못했습니다")
        return
    import shutil
    if not shutil.which("code"):
        raise RuntimeError("VSCode 명령(code)을 찾지 못했습니다")
    _spawn(["code", str(Path(folder).resolve())])


def desktop_shortcut(folder, name="비서"):
    """바탕화면에 'VSCode 로 이 폴더 열기' 바로가기. 만든 파일 경로를 돌려준다.
    WSL: VSCode(Windows) 가 WSL 폴더를 원격으로 연다 (--folder-uri vscode-remote://wsl+<배포판>/…)."""
    folder = Path(folder).resolve()
    if IS_WSL or IS_WINDOWS:
        if IS_WSL:
            distro = os.environ.get("WSL_DISTRO_NAME", "Ubuntu")
            args = f"--folder-uri vscode-remote://wsl+{distro}{folder.as_posix()}"
        else:
            args = f'"{folder}"'
        script = f"""
$ErrorActionPreference = 'Stop'
$code = (Get-Command code.cmd -ErrorAction SilentlyContinue).Source
if ($code) {{ $exe = Join-Path (Split-Path (Split-Path $code)) 'Code.exe' }}
if (-not $exe -or -not (Test-Path $exe)) {{ $exe = Join-Path $env:LOCALAPPDATA 'Programs/Microsoft VS Code/Code.exe' }}
if (-not (Test-Path $exe)) {{ throw 'VSCode(Code.exe)를 찾지 못했습니다' }}
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) '{name}.lnk'
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = $exe
$s.Arguments = '{args}'
$s.Description = '개인 비서 — VSCode 로 비서 폴더 열기 (엔진·대시보드가 자동으로 켜짐)'
$s.IconLocation = "$exe,0"
$s.Save()
Write-Output $lnk
"""
        ok, out = _ps(script)
        if not ok:
            raise RuntimeError(out.splitlines()[-1] if out else "바로가기를 만들지 못했습니다")
        return out.splitlines()[-1]
    desk = Path.home() / "Desktop"
    desk.mkdir(exist_ok=True)
    f = desk / f"{name}.desktop"
    f.write_text(f"[Desktop Entry]\nType=Application\nName={name}\nExec=code {folder}\nIcon=code\nTerminal=false\n", encoding="utf-8")
    f.chmod(0o755)
    return str(f)


def open_path(path):
    """파일·폴더를 기본 프로그램으로 연다."""
    if IS_WSL:
        _spawn(["explorer.exe", _win_path(path)])
    elif IS_WINDOWS:
        os.startfile(str(path))
    else:
        _spawn(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


def reveal(path):
    """탐색기에서 그 파일을 선택한 채로 보여 준다 (리눅스는 들어 있는 폴더를 연다)."""
    if IS_WSL:
        _spawn(["explorer.exe", "/select," + _win_path(path)])
    elif IS_WINDOWS:
        subprocess.Popen(f'explorer /select,"{path}"')
    elif sys.platform == "darwin":
        _spawn(["open", "-R", str(path)])
    else:
        open_path(Path(path).parent)


def browser_name():
    """webbrowser 에 넘길 브라우저 이름 (Google 로그인 창). WSL 이면 Windows 브라우저를 등록해 쓴다."""
    if IS_WSL:
        webbrowser.register("wsl-windows", None, webbrowser.GenericBrowser("explorer.exe"))
        return "wsl-windows"
    return None


def downloads_dir():
    if IS_WSL:
        users = Path("/mnt/c/Users")
        for u in sorted(users.iterdir()) if users.exists() else []:
            d = u / "Downloads"
            if d.is_dir() and u.name not in ("Public", "Default", "Default User", "All Users"):
                return d
        return None
    d = Path.home() / "Downloads"
    return d if d.is_dir() else None


def pa_command(*args):
    """비서 명령(bin/pa …)을 다른 프로세스로 실행할 때의 명령 줄 — 모든 환경에서 같다."""
    return [sys.executable, "-m", "pa", *args]


def lock(f, wait=True):
    """열어 둔 파일 f 로 프로세스 사이 잠금을 잡는다. wait=False 면 바로 못 잡을 때 False.
    파일을 닫거나 프로세스가 끝나면 풀린다."""
    if IS_WINDOWS:
        import msvcrt
        while True:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                if not wait:
                    return False
                time.sleep(0.2)
    import fcntl
    try:
        fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        return True
    except BlockingIOError:
        return False


# 엔진(watch)이 새 코드로 다시 시작할 때 Windows 에서 쓰는 종료 코드. bin/pa.cmd 가 이 코드를 보면 다시 실행한다.
RESTART_CODE = 75


def restart_self(args):
    """이 프로세스를 새 코드로 다시 시작한다. 리눅스는 그 자리에서 바꿔치기(exec)하고,
    Windows 는 exec 가 새 프로세스를 띄우고 끝나 버려 VSCode 작업 창과 끊기므로 종료 코드로 알리고 bin/pa.cmd 가 다시 띄운다."""
    if IS_WINDOWS:
        os._exit(RESTART_CODE)  # 서버·작업 스레드까지 바로 끝냄 (포트·잠금이 풀림)
    os.execv(sys.executable, [sys.executable, "-m", "pa", *args])
