# 개인 비서: VSCode 를 열지 않아도 엔진이 늘 켜져 있고, 따로 하루 몇 번 최신화도 한다.
#   PersonalAssistant-Engine  Windows 로그인할 때 엔진(bin/pa watch)을 창 없이 켜 둔다 — 대시보드 서버, 자동 계획·알림,
#                             대시보드는 저절로 열지 않음 (VSCode 의 ✓ 버튼 · Ctrl+Alt+D). 꺼지면 1분 뒤 다시 켬.
#   PersonalAssistant-Sync    매일 07:00, 13:00, 19:00 (+ 로그인할 때) bin/pa run --full — 엔진이 꺼져 있을 때의 보험.
#                             엔진과 겹쳐도 한 번에 하나만 실행됨.
#   비서가 WSL 안에 있으면 wscript + .vbs 로 WSL 을 깨워 실행, Windows 폴더에 있으면 .venv 의 pythonw 로 바로 (둘 다 창 없음)
#   기록: 비서 폴더의 data\pa.log
#
# 실행 (한 번만): Windows 의 PowerShell 에서 비서 폴더의 이 파일을
#   WSL:     powershell -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\<리눅스 사용자>\personal_assistant\scripts\windows\register-task.ps1"
#   Windows: powershell -ExecutionPolicy Bypass -File "<비서 폴더>\scripts\windows\register-task.ps1"
# 지우기: 같은 폴더의 unregister-task.ps1

$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))  # ..\.. 를 풀어 둔 경로 (\\wsl.localhost\… 도)
$Dir = Join-Path $env:LOCALAPPDATA "PersonalAssistant"
New-Item -ItemType Directory -Force -Path $Dir | Out-Null

function Hidden-Wsl($name, $cmd) {
    # \\wsl.localhost\<배포판>\home\… (또는 \\wsl$\…) → 배포판 이름과 리눅스 경로로 .vbs 를 만든다
    $parts = $Root.TrimStart('\').Split('\')
    $distro = $parts[1]
    $linux = '/' + (($parts | Select-Object -Skip 2) -join '/')
    $vbs = Join-Path $Dir $name
    $line = 'CreateObject("WScript.Shell").Run "wsl.exe -d ' + $distro + ' -- bash -lc ""cd ''' + $linux + ''' && ' + $cmd + '""", 0, True'
    Set-Content -Path $vbs -Value ("' Personal assistant: run hidden from Task Scheduler (made by register-task.ps1)`r`n" + $line) -Encoding ASCII
    return (New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbs`"")
}

if ($Root -like "\\wsl*") {
    $engine = Hidden-Wsl "engine-hidden.vbs" "bin/pa watch"
    $sync = Hidden-Wsl "run-hidden.vbs" "bin/pa run --full"
    $Where = "WSL"
} else {
    $Pyw = Join-Path $Root ".venv\Scripts\pythonw.exe"
    if (-not (Test-Path $Pyw)) { Write-Host "먼저 bin\setup.cmd 를 실행하세요 ($Pyw 없음)"; exit 1 }
    $engine = New-ScheduledTaskAction -Execute $Pyw -Argument "-X utf8 -m pa watch" -WorkingDirectory $Root
    $sync = New-ScheduledTaskAction -Execute $Pyw -Argument "-X utf8 -m pa run --full" -WorkingDirectory $Root
    $Where = "Windows"
}

$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$engineSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew `
    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "PersonalAssistant-Engine" -Action $engine -Trigger $logon -Settings $engineSettings `
    -Description "개인 비서 엔진: 대시보드 서버·자동 계획·알림 ($Where bin/pa watch). 이미 켜져 있으면 바로 끝남" -Force | Out-Null

$triggers = @(
    $logon,
    (New-ScheduledTaskTrigger -Daily -At 7:00),
    (New-ScheduledTaskTrigger -Daily -At 13:00),
    (New-ScheduledTaskTrigger -Daily -At 19:00)
)
$syncSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "PersonalAssistant-Sync" -Action $sync -Trigger $triggers -Settings $syncSettings `
    -Description "개인 비서: Canvas 확인, 자료, 학습 계획, Google Calendar ($Where bin/pa run --full)" -Force | Out-Null

Write-Host "등록 완료: 작업 스케줄러 > 'PersonalAssistant-Engine' (로그인할 때 엔진), 'PersonalAssistant-Sync' (하루 3번)"
Write-Host "지금 엔진 켜기:  Start-ScheduledTask -TaskName PersonalAssistant-Engine"
