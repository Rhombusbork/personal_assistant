# register-task.ps1 로 등록한 자동 실행(엔진·하루 3번 최신화)을 지운다. 켜져 있는 엔진은 그대로 (다음 로그인부터 안 켜짐).
foreach ($n in "PersonalAssistant-Engine", "PersonalAssistant-Sync") {
    Unregister-ScheduledTask -TaskName $n -Confirm:$false -ErrorAction SilentlyContinue
}
Remove-Item -Recurse -Force (Join-Path $env:LOCALAPPDATA "PersonalAssistant") -ErrorAction SilentlyContinue
Write-Host "삭제 완료"
