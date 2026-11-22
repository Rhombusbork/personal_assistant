# WSL(Ubuntu)을 통째로 다른 PC 로 복사 - 보내는 PC 에서 관리자 PowerShell 로 실행 (USB 없이, 같은 와이파이)
#   powershell -ExecutionPolicy Bypass -File C:\pa-transfer\wsl-send.ps1
# 1) 비서 작업 스케줄러를 잠시 멈추고 WSL 을 끈 뒤 wsl --export
# 2) 비서를 다시 켜고, 비밀 주소(무작위 글자)로 같은 와이파이에만 내려받기 서버를 연다
# 3) 받는 PC 가 다 받으면(또는 Ctrl+C) 서버·방화벽 규칙을 닫고 복사본을 지운다
# 같은 폴더에 wsl-receive.ps1 이 있어야 한다. 이 스크립트는 WSL 밖(C:\ 등)에 두고 실행한다.
param([string]$Distro = "Ubuntu", [int]$Port = 8770, [string]$OutDir = "$env:USERPROFILE\pa-transfer")
$ErrorActionPreference = "Stop"
$env:WSL_UTF8 = "1"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Write-Host "관리자 권한 PowerShell 에서 실행해 주세요 (시작 → PowerShell → 관리자 권한으로 실행)" -ForegroundColor Red; exit 1 }
if ($PSScriptRoot -like "\\wsl*") { Write-Host "이 스크립트를 C:\ 아래로 복사한 뒤 실행해 주세요 (WSL 을 끄면 WSL 안의 파일은 사라집니다)" -ForegroundColor Red; exit 1 }
$receive = Join-Path $PSScriptRoot "wsl-receive.ps1"
if (-not (Test-Path $receive)) { Write-Host "같은 폴더에 wsl-receive.ps1 이 없습니다" -ForegroundColor Red; exit 1 }

Write-Host "VSCode 를 모두 닫았는지 확인하세요. WSL($Distro)을 끄고 복사본을 만듭니다 (10~30분)."
Read-Host "계속하려면 Enter" | Out-Null

New-Item -ItemType Directory -Force $OutDir | Out-Null
$tar = Join-Path $OutDir "wsl.tar"
$tasks = @(Get-ScheduledTask -TaskName "PersonalAssistant-*" -ErrorAction SilentlyContinue | Where-Object { $_.State -ne "Disabled" })
try {
    foreach ($t in $tasks) { Stop-ScheduledTask -TaskName $t.TaskName; Disable-ScheduledTask -TaskName $t.TaskName | Out-Null }
    wsl --shutdown
    for ($i = 0; $i -lt 30 -and ((wsl -l --running -q) -contains $Distro); $i++) { Start-Sleep 2 }
    Write-Host "복사본 만드는 중 → $tar"
    wsl --export $Distro $tar
    if ($LASTEXITCODE -ne 0) { throw "wsl --export 실패" }
} finally {
    foreach ($t in $tasks) { Enable-ScheduledTask -TaskName $t.TaskName | Out-Null }
    $engine = $tasks | Where-Object { $_.TaskName -eq "PersonalAssistant-Engine" }
    if ($engine) { Start-ScheduledTask -TaskName "PersonalAssistant-Engine"; Write-Host "비서 엔진을 다시 켰습니다" }
}
$size = (Get-Item $tar).Length
Write-Host ("복사본 완성: {0:N1} GB" -f ($size / 1GB))

$token = -join ((48..57) + (97..122) | Get-Random -Count 10 | ForEach-Object { [char]$_ })
$ip = (Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" } | Select-Object -First 1).IPv4Address.IPAddress
$base = "http://${ip}:$Port/$token"
$rule = "WSL copy ($Port)"
New-NetFirewallRule -DisplayName $rule -Direction Inbound -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet -Action Allow -Profile Any | Out-Null
$http = New-Object System.Net.HttpListener
$http.Prefixes.Add("http://+:$Port/$token/")
$http.Start()
$done = $false
try {
    Write-Host ""
    Write-Host "받는 PC 의 관리자 PowerShell 에 아래 한 줄을 그대로 입력하세요 (이 창은 끝날 때까지 열어 두기):" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  curl.exe -o `$env:TEMP\wsl-receive.ps1 $base/receive.ps1; powershell -ExecutionPolicy Bypass -File `$env:TEMP\wsl-receive.ps1 $base" -ForegroundColor Green
    Write-Host ""
    while (-not $done) {
        $ctx = $http.GetContext()
        $name = $ctx.Request.Url.AbsolutePath.Substring($token.Length + 2)
        Write-Host ("[{0:HH:mm:ss}] {1} 요청: {2}" -f (Get-Date), $ctx.Request.RemoteEndPoint.Address, $name)
        $res = $ctx.Response
        try {
            if ($name -eq "receive.ps1" -or $name -eq "wsl.tar") {
                $path = if ($name -eq "wsl.tar") { $tar } else { $receive }
                $fs = [IO.File]::OpenRead($path)
                try { $res.ContentLength64 = $fs.Length; $res.ContentType = "application/octet-stream"; $fs.CopyTo($res.OutputStream, 4MB) } finally { $fs.Close() }
                if ($name -eq "wsl.tar") { Write-Host "보내기 끝 - 받는 PC 가 들여오는 중입니다" }
            } elseif ($name -eq "done") {
                $done = $true
            } else { $res.StatusCode = 404 }
        } catch { Write-Host "  (연결 끊김: $($_.Exception.Message))" -ForegroundColor DarkYellow }
        try { $res.Close() } catch {}
    }
} finally {
    $http.Stop()
    Remove-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
    if ($done) {
        Remove-Item $tar
        Write-Host "받는 PC 가 다 받았습니다. 서버·방화벽 규칙을 닫고 복사본을 지웠습니다." -ForegroundColor Green
    } else {
        Write-Host "서버를 닫았습니다. 복사본은 남아 있습니다 (비밀번호·토큰이 들어 있음): $tar" -ForegroundColor Yellow
        Write-Host "다시 보내려면 이 스크립트를 다시 실행, 필요 없으면: del `"$tar`""
    }
}
