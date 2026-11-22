"""PC 전원: 절전 모드(S3)에서 깨우기 시험 · 절전 들어가기 · 매직 패킷 보내기 (Windows·WSL) — `bin/pa power …`

  bin/pa power                      지금 설정: 절전 해제 타이머 허용 · 덮개 닫을 때 · 깨우기 가능 장치 · Wi-Fi 주소 · 예약된 깨우기
  bin/pa power allow-timers on|off  '절전 모드 해제 타이머 허용' (충전 중) — 예약 깨우기에 필요
  bin/pa power test-wake [분] [--no-sleep] [--battery]
                                    시험 A: N분(기본 3) 뒤 깨우는 작업을 만들고 20초 뒤 절전 → 깨면 시각을 기록
  bin/pa power results              최근 절전·깨어남 (언제 자서 · 언제 · 무엇이 깨웠나) + 시험 기록
  bin/pa power sleep                지금 절전
  bin/pa power wol <MAC> [--to IP]  매직 패킷 보내기 (다른 노트북에서 이 PC 깨우기 시험)

'절전 모드' = 화면·CPU 가 멈추고 메모리만 유지 (배터리 절약 모드와 다름). 이 PC 의 결과는 docs/week-grid-plan.md 3-5.
"""
import re
import sys
import time

from pa import osutil

TASK = "PA-WakeTest"
LOG = r"$env:LOCALAPPDATA\pa-wake-test.log"
RTC = "SUB_SLEEP RTCWAKE"
VALUES = {0: "사용 안 함", 1: "사용", 2: "중요 타이머만"}


def _ps(script):
    if not (osutil.IS_WINDOWS or osutil.IS_WSL):
        sys.exit("Windows(또는 WSL)에서만 됩니다")
    return osutil._ps(script)


def _setting(sub_setting):
    """현재 전원 구성의 (충전 중, 배터리) 값."""
    _, out = _ps(f"powercfg /q SCHEME_CURRENT {sub_setting}")
    vals = re.findall(r"0x([0-9a-fA-F]+)\s*$", out, re.M)
    return tuple(int(v, 16) for v in vals[-2:]) if len(vals) >= 2 else (None, None)


def status():
    ac, dc = _setting(RTC)
    print(f"절전 모드 해제 타이머 허용: 충전 중 = {VALUES.get(ac, ac)} · 배터리 = {VALUES.get(dc, dc)}"
          + ("  ← 예약 깨우기는 '사용'이어야 함 (bin/pa power allow-timers on)" if ac != 1 else ""))
    lac, ldc = _setting("SUB_BUTTONS LIDACTION")
    lid = {0: "아무것도 안 함", 1: "절전", 2: "최대 절전", 3: "종료"}
    print(f"덮개를 닫으면: 충전 중 = {lid.get(lac, lac)} · 배터리 = {lid.get(ldc, ldc)}" if lac is not None
          else "덮개를 닫으면: 이 PC 는 Windows 에 설정이 안 보임 (보통 절전) → 덮개 시험으로 확인")
    _, out = _ps("powercfg /devicequery wake_programmable")
    print("깨울 수 있게 설정된 장치: " + ", ".join(x.strip() for x in out.splitlines() if x.strip()))
    _, out = _ps("$a = Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -match 'Wireless|Wi-Fi|WLAN' } | Select-Object -First 1;"
                 "if ($a) { $ip = (Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 | Select-Object -First 1);"
                 "'{0}|{1}|{2}|{3}' -f $a.Name, $a.MacAddress, $ip.IPAddress, $ip.PrefixLength }")
    if "|" in out:
        name, mac, ip, prefix = out.splitlines()[-1].split("|")
        print(f"Wi-Fi ({name}): 주소(MAC) {mac} · IP {ip} · 같은 Wi-Fi 브로드캐스트 {broadcast(ip, int(prefix or 24))}")
    _, out = _ps(f"$i = Get-ScheduledTask -TaskName '{TASK}' -ErrorAction SilentlyContinue | Get-ScheduledTaskInfo;"
                 "if ($i -and $i.NextRunTime) { $i.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss') }")
    print("시험 깨우기 예약: " + (out.splitlines()[-1] if out else "없음"))


def broadcast(ip, prefix):
    n = sum(int(p) << (24 - 8 * i) for i, p in enumerate(ip.split(".")))
    n |= (1 << (32 - prefix)) - 1
    return ".".join(str(n >> s & 255) for s in (24, 16, 8, 0))


def allow_timers(on):
    v = 1 if on else 2  # 끄면 원래 값(중요 타이머만)으로
    ok, out = _ps(f"powercfg /setacvalueindex SCHEME_CURRENT {RTC} {v}; powercfg /setactive SCHEME_CURRENT")
    if not ok:
        sys.exit("바꾸지 못함: " + out)
    print(f"절전 모드 해제 타이머 허용 (충전 중) → {VALUES[v]}")


def sleep_now():
    """절전 모드 (최대 절전 아님 — rundll32 SetSuspendState 는 최대 절전이 켜져 있으면 최대 절전으로 가므로 쓰지 않음)."""
    _ps("Add-Type -AssemblyName System.Windows.Forms; "
        "[System.Windows.Forms.Application]::SetSuspendState([System.Windows.Forms.PowerState]::Suspend, $false, $false) | Out-Null")


def test_wake(minutes=3, sleep=True, battery=False):
    stamp = "Add-Content -Encoding UTF8 -Path " + LOG + " -Value ('깨어남 ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))"
    ok, out = _ps(
        f"$at = (Get-Date).AddMinutes({minutes});"
        f"$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument \"-NoProfile -WindowStyle Hidden -Command {stamp.replace(chr(34), '')}\";"
        "$t = New-ScheduledTaskTrigger -Once -At $at;"
        "$s = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable;"
        f"Register-ScheduledTask -TaskName '{TASK}' -Action $a -Trigger $t -Settings $s -Force | Out-Null;"
        f"Add-Content -Encoding UTF8 -Path {LOG} -Value ('예약 ' + $at.ToString('yyyy-MM-dd HH:mm:ss') + ' (절전 시작 ' + (Get-Date -Format 'HH:mm:ss') + ')');"
        "$at.ToString('HH:mm:ss')")
    if not ok:
        sys.exit("깨우기 작업을 만들지 못함: " + out)
    print(f"깨우기 예약: {out.splitlines()[-1]} (작업 이름 {TASK})")
    ac, _ = _setting(RTC)
    if ac != 1:
        print("⚠️ '절전 모드 해제 타이머 허용'이 충전 중 '사용'이 아님 → 안 깰 수 있음 (bin/pa power allow-timers on)")
    if battery:
        print("배터리 시험: 충전기를 뽑아 두세요 (배터리 쪽 설정은 '사용 안 함'일 수 있음)")
    if not sleep:
        print("직접 절전하세요: 시작 → 전원 → 절전 (덮개를 닫아도 됨)")
        return
    for s in range(20, 0, -5):
        print(f"  {s}초 뒤 절전 — 덮개 시험이면 지금 닫으세요 (취소: Ctrl+C)", flush=True)
        time.sleep(5)
    sleep_now()
    time.sleep(5)  # 깨어난 뒤
    print("깨어남 — bin/pa power results 로 무엇이 깨웠는지 확인")


def results(n=6):
    from datetime import datetime
    from pa.model import KST
    ok, out = _ps(
        "Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Power-Troubleshooter'; Id=1} "
        f"-MaxEvents {n} -ErrorAction SilentlyContinue | ForEach-Object {{ $_.Message; '@@' }}")
    print("최근 절전 → 깨어남 (새것 먼저, 한국 시각):")
    shown = 0
    for msg in (out.replace("\u200e", "").split("@@") if ok else []):
        when = [datetime.fromisoformat(x[:19]).replace(tzinfo=__import__("datetime").timezone.utc).astimezone(KST)
                for x in re.findall(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", msg)]
        src = re.search(r"(?:원본|Source)\s*:\s*(.+)", msg)
        if len(when) >= 2:
            mins = int((when[1] - when[0]).total_seconds() // 60)
            print(f"  · {when[0]:%m/%d %H:%M} 잠 → {when[1]:%m/%d %H:%M} 깸 ({mins}분) · 깨운 것: {src.group(1).strip() if src else '?'}")
            shown += 1
    if not shown:
        print("  (기록 없음)")
    _, out = _ps(f"if (Test-Path {LOG}) {{ Get-Content {LOG} -Tail 8 -Encoding UTF8 }}")
    print("시험 기록 (예약 → 깨어남):\n  " + ("\n  ".join(out.splitlines()) or "(없음)"))
    print("  '깨운 것'이 Unknown 이거나 키보드·USB 면 사람이 깨운 것일 수 있음 — 시험 땐 손대지 말고 기다리기")


def wol(mac, to="255.255.255.255"):
    """매직 패킷 (Windows 쪽에서 보냄 — WSL 안에서 보내면 집 Wi-Fi 로 나가지 않음)."""
    m = re.sub(r"[^0-9A-Fa-f]", "", mac)
    if len(m) != 12:
        sys.exit("MAC 주소 형식: AA-BB-CC-DD-EE-FF")
    ok, out = _ps(f"$m = [byte[]](0..5 | ForEach-Object {{ [Convert]::ToByte('{m}'.Substring($_ * 2, 2), 16) }});"
                  "$p = [byte[]](,0xFF * 6) + ($m * 16);"
                  "$u = New-Object System.Net.Sockets.UdpClient; $u.EnableBroadcast = $true;"
                  f"foreach ($port in 9, 7) {{ [void]$u.Send($p, $p.Length, '{to}', $port) }}; $u.Close(); 'sent'")
    print(f"매직 패킷 보냄 → {mac} ({to}, 포트 9·7)" if ok else "보내지 못함: " + out)


def main(argv):
    a = argv[0] if argv else "status"
    if a == "status":
        status()
    elif a == "allow-timers" and len(argv) > 1 and argv[1] in ("on", "off"):
        allow_timers(argv[1] == "on")
    elif a == "test-wake":
        mins = next((int(x) for x in argv[1:] if x.isdigit()), 3)
        test_wake(mins, sleep="--no-sleep" not in argv, battery="--battery" in argv)
    elif a == "results":
        results()
    elif a == "sleep":
        sleep_now()
    elif a == "wol" and len(argv) > 1:
        wol(argv[1], argv[argv.index("--to") + 1] if "--to" in argv else "255.255.255.255")
    else:
        print(__doc__)
