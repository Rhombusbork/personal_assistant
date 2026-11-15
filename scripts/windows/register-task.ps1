# 개인 비서: VSCode 를 열지 않아도 Canvas 확인·자료 다운로드·계획·캘린더를 자동으로 돌린다.
#   언제: Windows 로그인할 때 + 매일 07:00, 13:00, 19:00 (컴퓨터가 꺼져 있어 놓치면 켜졌을 때 바로)
#   무엇: bin/pa run --full  (VSCode 안의 엔진과 겹쳐도 한 번에 하나만 실행됨)
#         비서가 WSL 안에 있으면 run-hidden.vbs 로 WSL 을 깨워 실행, Windows 폴더에 있으면 .venv 의 pythonw 로 바로 (둘 다 창 없음)
#   기록: 비서 폴더의 data\pa.log
#
# 실행 (한 번만): Windows 의 PowerShell 에서 비서 폴더의 이 파일을
#   WSL:     powershell -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\<리눅스 사용자>\personal_assistant\scripts\windows\register-task.ps1"
#   Windows: powershell -ExecutionPolicy Bypass -File "<비서 폴더>\scripts\windows\register-task.ps1"
# 지우기: 같은 폴더의 unregister-task.ps1

$Name = "PersonalAssistant-Sync"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).ProviderPath
if ($Root -like "\\wsl*") {
    $Dir = Join-Path $env:LOCALAPPDATA "PersonalAssistant"
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    Copy-Item -Force (Join-Path $PSScriptRoot "run-hidden.vbs") (Join-Path $Dir "run-hidden.vbs")
    $action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$Dir\run-hidden.vbs`""
    $Where = "WSL"
} else {
    $Pyw = Join-Path $Root ".venv\Scripts\pythonw.exe"
    if (-not (Test-Path $Pyw)) { Write-Host "먼저 bin\setup.cmd 를 실행하세요 ($Pyw 없음)"; exit 1 }
    $action = New-ScheduledTaskAction -Execute $Pyw -Argument "-X utf8 -m pa run --full" -WorkingDirectory $Root
    $Where = "Windows"
}
$triggers = @(
    (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME),
    (New-ScheduledTaskTrigger -Daily -At 7:00),
    (New-ScheduledTaskTrigger -Daily -At 13:00),
    (New-ScheduledTaskTrigger -Daily -At 19:00)
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $Name -Action $action -Trigger $triggers -Settings $settings `
    -Description "개인 비서: Canvas 확인, 자료, 학습 계획, Google Calendar ($Where bin/pa run --full)" -Force | Out-Null

Write-Host "등록 완료: 작업 스케줄러 > '$Name'"
Write-Host "지금 한 번 시험:  Start-ScheduledTask -TaskName $Name"
