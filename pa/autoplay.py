"""강의 페이지를 연 뒤 플레이어의 ▶(재생) 버튼을 눌러 준다 — Windows 접근성(UI Automation)으로 버튼을 '이름'으로 찾는다.

마우스 위치를 짐작해 누르지 않는다:
  - 창 제목(= 지금 보이는 탭)에 강의 제목이 들어 있는 브라우저 창만 (Firefox·Edge·Chrome).
    최소화돼 있으면 화면에 띄우고 앞으로 가져온다 (최소화된 창의 버튼은 '화면 밖'이라 찾을 수 없음)
  - 그 창의 화면에 보이는 버튼 중 이름이 '재생'/'Play' 인 것만
  - 누르기는 버튼의 기본 동작(Invoke)으로. 그게 없으면 그 버튼 한가운데를 클릭
못 찾으면 아무것도 안 누른다. 페이지가 뜨는 동안 몇 번 다시 찾는다 (pa/autoopen.py 에서 부름).
Windows·WSL 에서만 (리눅스·Mac 은 건너뜀).
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


def press_play(title, dry=False):
    """'invoked' · 'clicked' · 'none' · 'skip'(Windows 아님). dry=True 면 찾기만 ('found')."""
    if not (osutil.IS_WSL or osutil.IS_WINDOWS):
        return "skip"
    script = SCRIPT.replace("__TITLE__", _key(title)).replace("__NAMES__", ", ".join(f"'{n}'" for n in NAMES)).replace("__DRY__", "true" if dry else "false")
    out = _ps(script)
    return out[-1] if out else "none"


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


if __name__ == "__main__":  # python -m pa.autoplay [--find] <강의 제목>
    import sys
    dry = "--find" in sys.argv
    print(press_play(" ".join(a for a in sys.argv[1:] if a != "--find"), dry=dry))
