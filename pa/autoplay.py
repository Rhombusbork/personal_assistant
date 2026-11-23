"""강의 페이지를 연 뒤 플레이어의 ▶(재생) 버튼을 눌러 준다 — Windows 접근성(UI Automation)으로 버튼을 '이름'으로 찾는다.

마우스 위치를 짐작해 누르지 않는다:
  - 창 제목(= 지금 보이는 탭)에 강의 제목이 들어 있는 브라우저 창만 (Firefox·Edge·Chrome).
    최소화돼 있으면 화면에 띄우고 앞으로 가져온다 (최소화된 창의 버튼은 '화면 밖'이라 찾을 수 없음)
  - 그 창의 화면에 보이는 버튼 중 이름이 '재생'/'Play' 인 것만
  - 누르기는 버튼의 기본 동작(Invoke)으로. 그게 없으면 그 버튼 한가운데를 클릭
못 찾으면 아무것도 안 누른다. 페이지가 뜨는 동안 몇 번 다시 찾는다 (pa/autoopen.py 에서 부름).
Windows·WSL 에서만 (리눅스·Mac 은 건너뜀).

강의 블록 동안 지켜보기 (watch, 2026-11-23 — 출석을 '돕는' 것까지만):
  - "계속 보시겠습니까?" 같은 확인 버튼이 뜨면: 내가 최근 2분 안에 키보드·마우스를 썼으면(자리에 있음) 눌러 주고,
    자리에 없으면 누르지 않고 그 창을 앞으로 + 대시보드 알림 (자리 비운 동안 출석을 채우지 않음)
  - 배속: config auto_open.speed 에 과목별로 적으면 재생 뒤 그 배속 버튼을 찾아 누름 (버튼 이름을 못 찾으면 그대로)
  - 탭을 닫으면 그만 지켜봄.  확인: python -m pa.autoplay --list <강의 제목>  (그 창의 버튼 이름 목록)
"""
import base64
import subprocess
import time

from pa import osutil

NAMES = ("재생", "Play", "play")

SCRIPT = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$want = '__TITLE__'
$names = @(__NAMES__)
$list = $__LIST__
$dry = $__DRY__
$A = [Windows.Automation.AutomationElement]
$wins = $A::RootElement.FindAll([Windows.Automation.TreeScope]::Children, [Windows.Automation.Condition]::TrueCondition) |
  Where-Object { $_.Current.ClassName -in @('MozillaWindowClass', 'Chrome_WidgetWin_1') -and $_.Current.Name.Contains($want) }
Add-Type -Name M -Namespace W -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern void mouse_event(int f, int x, int y, int d, int e);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);'
foreach ($w in $wins) {
  $h = [IntPtr]$w.Current.NativeWindowHandle
  if (-not $dry) {
    if ([W.M]::IsIconic($h)) { [W.M]::ShowWindow($h, 9) | Out-Null; Start-Sleep -Milliseconds 800 }  # 최소화돼 있으면 화면에 띄움
    [W.M]::SetForegroundWindow($h) | Out-Null
  }
  $cond = New-Object Windows.Automation.PropertyCondition($A::ControlTypeProperty, [Windows.Automation.ControlType]::Button)
  foreach ($b in $w.FindAll([Windows.Automation.TreeScope]::Descendants, $cond)) {
    if ($list) { if (-not $b.Current.IsOffscreen -and $b.Current.Name) { 'BTN ' + $b.Current.Name }; continue }
    if ($b.Current.IsOffscreen -or $names -notcontains $b.Current.Name) { continue }
    if ($dry) { 'found'; exit }
    $p = $null
    if ($b.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern, [ref]$p)) { $p.Invoke(); 'invoked'; exit }
    $r = $b.Current.BoundingRectangle
    [W.M]::SetCursorPos([int]($r.Left + $r.Width / 2), [int]($r.Top + $r.Height / 2))
    [W.M]::mouse_event(2, 0, 0, 0, 0); [W.M]::mouse_event(4, 0, 0, 0, 0)
    'clicked'; exit
  }
}
'none'
"""


def _key(title):
    """창 제목과 맞춰 볼 강의 제목 앞부분 (Canvas 가 탭 제목 뒤를 자르거나 덧붙여도 맞게)."""
    return title.strip()[:20].replace("'", "''")


def press(title, names, dry=False):
    """그 강의 창에서 이름이 names 중 하나인 버튼을 누른다 (누를 때는 창을 앞으로). 'invoked' · 'clicked' · 'none' · 'skip' (dry → 'found')."""
    if not (osutil.IS_WSL or osutil.IS_WINDOWS):
        return "skip"
    script = (SCRIPT.replace("__TITLE__", _key(title)).replace("__NAMES__", ", ".join("'" + n.replace("'", "''") + "'" for n in names))
              .replace("__DRY__", "true" if dry else "false").replace("__LIST__", "false"))
    out = _ps(script)
    return out[-1] if out else "none"


def press_play(title, dry=False):
    """'invoked' · 'clicked' · 'none' · 'skip'(Windows 아님). dry=True 면 찾기만 ('found')."""
    return press(title, NAMES, dry)


def buttons(title):
    """그 강의 창에 보이는 버튼 이름 목록 (배속·확인 버튼 이름을 알아낼 때)."""
    if not (osutil.IS_WSL or osutil.IS_WINDOWS):
        return []
    script = SCRIPT.replace("__TITLE__", _key(title)).replace("__NAMES__", "''").replace("__DRY__", "true").replace("__LIST__", "true")
    return sorted({l[4:] for l in _ps(script) if l.startswith("BTN ")})


IDLE = r"""
Add-Type -Name I -Namespace W -MemberDefinition '[StructLayout(LayoutKind.Sequential)] public struct L { public uint s; public uint t; }
[DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref L l);'
$l = New-Object W.I+L; $l.s = 8; [W.I]::GetLastInputInfo([ref]$l) | Out-Null
[int](([Environment]::TickCount - $l.t) / 1000)
"""


def idle_seconds():
    """마지막 키보드·마우스 입력 뒤 몇 초. 모르면 큰 값 (= 자리에 없다고 봄)."""
    try:
        out = _ps(IDLE)
        return int(out[-1]) if out else 10 ** 6
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return 10 ** 6


CONTINUE = ("계속 보기", "계속 시청", "계속 학습", "계속 학습하기", "이어서 보기", "이어 보기", "계속하기", "Continue", "계속")
SPEED_BTN = ("재생 속도", "배속", "속도", "Playback speed", "Speed")


def _ps(script):
    """PowerShell 실행 → 출력 줄 목록. 한글이 깨지지 않게 스크립트를 인코딩해서 넘긴다."""
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    exe = "powershell.exe" if osutil.IS_WSL else "powershell"
    r = subprocess.run([exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=60, **({"cwd": "/mnt/c"} if osutil.IS_WSL else {}))
    return (r.stdout or "").strip().splitlines()


TABS = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$A = [Windows.Automation.AutomationElement]
$c = New-Object Windows.Automation.PropertyCondition($A::ControlTypeProperty, [Windows.Automation.ControlType]::TabItem)
$A::RootElement.FindAll([Windows.Automation.TreeScope]::Children, [Windows.Automation.Condition]::TrueCondition) |
  Where-Object { $_.Current.ClassName -in @('MozillaWindowClass', 'Chrome_WidgetWin_1') } |
  ForEach-Object { foreach ($t in $_.FindAll([Windows.Automation.TreeScope]::Descendants, $c)) { 'TAB ' + $t.Current.Name } }
"""


def tab_open(title):
    """그 제목의 브라우저 탭이 열려 있나. Windows 가 아니거나 읽지 못하면 None (모름)."""
    if not (osutil.IS_WSL or osutil.IS_WINDOWS):
        return None
    try:
        tabs = [l[4:] for l in _ps(TABS) if l.startswith("TAB ")]
    except (OSError, subprocess.TimeoutExpired):
        return None
    key = title.strip()[:20]
    return any(key in t for t in tabs) if tabs else None


def play_when_ready(title, tries=12, every=5, log=lambda m: None):
    """페이지가 뜰 때까지 every 초마다 최대 tries 번 찾아서 한 번 누른다. 결과를 돌려준다."""
    for _ in range(tries):
        try:
            got = press_play(title)
        except (OSError, subprocess.TimeoutExpired) as e:
            got = f"error: {e}"
        if got in ("invoked", "clicked", "skip"):
            log(f"강의 재생 버튼: {got}")
            return got
        time.sleep(every)
    log("강의 재생 버튼을 못 찾음 — 직접 ▶ 를 눌러 주세요")
    return "none"


def set_speed(title, speed, log=lambda m: None):
    """배속 버튼 → 그 배속 항목 (예: 1.5 → '1.5x' · '1.5배' · '1.5'). 못 찾으면 그대로 두고 알림."""
    if press(title, SPEED_BTN) in ("invoked", "clicked"):
        time.sleep(1)
        got = press(title, (f"{speed}x", f"{speed}X", f"x{speed}", f"{speed}배", f"{speed}배속", str(speed)))
        if got in ("invoked", "clicked"):
            log(f"강의 배속 {speed}")
            return True
    log(f"배속 버튼을 못 찾음 ({speed}) — python -m pa.autoplay --list '{title}' 로 버튼 이름 확인")
    return False


def watch(title, until, idle_limit=120, every=60, log=lambda m: None, alert=lambda m: None):
    """강의 블록이 끝날 때까지 (또는 탭을 닫을 때까지) 확인창을 지켜본다. 자리에 없으면 누르지 않고 알린다."""
    import datetime as _dt
    from pa.model import now
    alerted = False
    while now() < until:
        time.sleep(every)
        if tab_open(title) is False:
            log("강의 탭이 닫혀 지켜보기 끝")
            return
        if press(title, CONTINUE, dry=True) != "found":
            alerted = False
            continue
        if idle_seconds() <= idle_limit:
            log(f"강의 확인창 '계속' 누름 ({press(title, CONTINUE)}) — 자리에 있음")
        elif not alerted:  # 자리에 없음 → 누르지 않고 알림 (출석을 대신 채우지 않음)
            press(title, ("__없는 버튼__",))  # 누르는 것 없이 창만 앞으로
            alert(f"강의가 확인창에서 멈췄어요: {title} — 돌아와서 '계속'을 눌러 주세요")
            alerted = True


if __name__ == "__main__":  # python -m pa.autoplay [--find | --list] <강의 제목>
    import sys
    rest = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    if "--list" in sys.argv:
        print("\n".join(buttons(rest)) or "(버튼 없음 — 창 제목에 강의 제목이 있는 브라우저 창이 있어야 함)")
    else:
        print(press_play(rest, dry="--find" in sys.argv))
