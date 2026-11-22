# WSL(Ubuntu) 복사본 받기 - 받는 PC 에서 관리자 PowerShell 로 (wsl-send.ps1 이 알려 주는 한 줄로 실행됨)
# 1) WSL 이 없으면 설치하고 재부팅을 부탁 (재부팅 뒤 같은 한 줄을 다시)
# 2) 보내는 PC 에서 복사본을 받아 wsl --import, 기본으로 지정
# 3) 이 PC 의 비서 .env 에 이름(PA_HOST)과 우선순위(PA_PRIORITY)를 적는다 - 두 PC 같이 쓰기(pa/peer.py)에서
#    둘 다 켜져 있으면 우선순위가 큰 PC 가 일한다. 같이 쓰기를 안 쓰면 -Priority 0 → 이 PC 는 엔진을 끈다(PA_ENGINE=off)
param([Parameter(Mandatory = $true)][string]$Url, [string]$Distro = "Ubuntu", [string]$Dir = "C:\WSL", [string]$PaDir = "personal_assistant",
      [int]$Priority = 2)
$ErrorActionPreference = "Stop"
$env:WSL_UTF8 = "1"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Write-Host "관리자 권한 PowerShell 에서 실행해 주세요 (시작 → PowerShell → 관리자 권한으로 실행)" -ForegroundColor Red; exit 1 }

$ok = $false
try { wsl --status *> $null; $ok = ($LASTEXITCODE -eq 0) } catch {}
if (-not $ok) {
    Write-Host "WSL 을 설치합니다..."
    wsl --install --no-distribution
    Write-Host "설치했습니다. 컴퓨터를 재부팅한 뒤 같은 한 줄을 다시 입력하세요." -ForegroundColor Yellow
    exit 0
}
if ((wsl -l -q) -contains $Distro) {
    Write-Host "이 PC 에 이미 '$Distro' 가 있습니다. 덮어쓰지 않고 멈춥니다 (지우는 건 되돌릴 수 없으니 먼저 확인하세요)." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force $Dir | Out-Null
$tar = Join-Path $Dir "wsl.tar"
Write-Host "복사본 받는 중 → $tar (10~30분)"
curl.exe -f -o $tar "$Url/wsl.tar"
if ($LASTEXITCODE -ne 0) { Write-Host "받기 실패 - 보내는 PC 의 창이 열려 있는지, 같은 와이파이인지 확인하세요" -ForegroundColor Red; exit 1 }

Write-Host "들여오는 중 → $Dir\$Distro"
wsl --import $Distro (Join-Path $Dir $Distro) $tar
if ($LASTEXITCODE -ne 0) { Write-Host "wsl --import 실패. 받은 파일은 남겨 둡니다: $tar" -ForegroundColor Red; exit 1 }
wsl --set-default $Distro
Remove-Item $tar

$lines = if ($Priority -gt 0) { "PA_HOST=$env:COMPUTERNAME\nPA_PRIORITY=$Priority" } else { "PA_ENGINE=off" }
wsl -d $Distro -- sh -c "test -f ~/$PaDir/.env && printf '\n$lines\n' >> ~/$PaDir/.env && echo ok"
wsl --shutdown
curl.exe -s "$Url/done" | Out-Null

Write-Host ""
if ($Priority -gt 0) {
    Write-Host "끝났습니다. 이 PC 이름은 $env:COMPUTERNAME, 우선순위 $Priority (두 PC 가 같이 켜져 있으면 큰 쪽이 일함)." -ForegroundColor Green
} else {
    Write-Host "끝났습니다. 이 PC 의 비서는 엔진을 끈 채로 둡니다 (.env 의 PA_ENGINE=off)." -ForegroundColor Green
}
Write-Host "다음: VSCode 설치 → 설정 동기화 켜기(같은 GitHub 계정) → PowerShell 에서 wsl → cd ~/$PaDir → code ."
