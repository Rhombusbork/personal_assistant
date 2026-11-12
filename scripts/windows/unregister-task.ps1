# register-task.ps1 로 등록한 자동 실행을 지운다.
Unregister-ScheduledTask -TaskName "PersonalAssistant-Sync" -Confirm:$false
Remove-Item -Recurse -Force (Join-Path $env:LOCALAPPDATA "PersonalAssistant") -ErrorAction SilentlyContinue
Write-Host "삭제 완료"
