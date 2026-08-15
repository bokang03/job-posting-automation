# =============================================================================
#  30분마다 공고를 확인하도록 Windows 작업 스케줄러에 등록합니다.
#
#  사용법: 이 파일을 마우스 오른쪽 클릭 -> "PowerShell에서 실행"
#          (관리자 권한은 필요 없습니다)
#
#  등록을 취소하려면: 작업스케줄러_해제.ps1 을 실행하세요.
# =============================================================================

$ErrorActionPreference = "Stop"

$TaskName = "직무공고알림"
$Root     = $PSScriptRoot
$Pythonw  = Join-Path $Root ".venv\Scripts\pythonw.exe"
$LogFile  = Join-Path $Root "logs\joballert.log"

Write-Host ""
Write-Host "직무 공고 알림 - 작업 스케줄러 등록" -ForegroundColor Cyan
Write-Host ("=" * 60)

# --- 사전 점검 -------------------------------------------------------------

if (-not (Test-Path $Pythonw)) {
    Write-Host ""
    Write-Host "[오류] 가상환경을 찾을 수 없습니다:" -ForegroundColor Red
    Write-Host "       $Pythonw"
    Write-Host ""
    Write-Host "setup.bat 을 먼저 실행해주세요."
    Read-Host "엔터를 누르면 종료합니다"
    exit 1
}

if (-not (Test-Path (Join-Path $Root ".env"))) {
    Write-Host ""
    Write-Host "[오류] .env 파일이 없습니다." -ForegroundColor Red
    Write-Host ""
    Write-Host "  1. .env.example 을 복사해서 이름을 .env 로 바꾸고"
    Write-Host "  2. 메모장으로 열어 디스코드 웹훅 주소를 넣어주세요."
    Write-Host ""
    Write-Host "  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/..."
    Write-Host ""
    Write-Host "  GitHub Secrets 와 달리 내 PC 에서 돌 때는 이 파일이 필요합니다."
    Read-Host "엔터를 누르면 종료합니다"
    exit 1
}

# --- 작업 정의 -------------------------------------------------------------

# pythonw.exe 는 콘솔 창을 띄우지 않습니다. 30분마다 검은 창이 깜빡이지 않습니다.
$Action = New-ScheduledTaskAction `
    -Execute $Pythonw `
    -Argument "-m src.main --log-file `"$LogFile`"" `
    -WorkingDirectory $Root

# 지금부터 30분 간격으로 반복합니다.
# 반복 기간에 [TimeSpan]::MaxValue 를 넣으면 Windows 가 "범위를 벗어났다"며 거부하므로
# 10년(3650일)으로 둡니다. 사실상 무기한입니다.
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

# -StartWhenAvailable : PC 가 꺼져 있어 놓친 실행을 켜자마자 한 번 따라잡습니다.
# -MultipleInstances IgnoreNew : 앞 실행이 안 끝났으면 새로 띄우지 않습니다.

# --- 등록 -------------------------------------------------------------------

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "기존 등록을 지우고 새로 만듭니다..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "채용 사이트에서 조건에 맞는 새 공고를 찾아 디스코드로 알립니다." | Out-Null

Write-Host ""
Write-Host "등록 완료" -ForegroundColor Green
Write-Host ""
Write-Host "  작업 이름 : $TaskName"
Write-Host "  실행 주기 : 30분마다"
Write-Host "  로그 파일 : $LogFile"
Write-Host ""

# --- 지금 한 번 실행해서 동작 확인 ------------------------------------------

Write-Host "지금 한 번 실행해 정상 동작하는지 확인합니다..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName $TaskName

Start-Sleep -Seconds 5
$state = (Get-ScheduledTask -TaskName $TaskName).State
Write-Host "  현재 상태: $state"
Write-Host ""
Write-Host "1~2분 뒤 아래 명령으로 결과를 확인할 수 있습니다."
Write-Host "  Get-Content `"$LogFile`" -Tail 20" -ForegroundColor Yellow
Write-Host ""
Write-Host "작업을 눈으로 확인하려면 시작 메뉴에서 '작업 스케줄러' 를 열고"
Write-Host "왼쪽 '작업 스케줄러 라이브러리' 에서 '$TaskName' 을 찾으세요."
Write-Host ""
Read-Host "엔터를 누르면 종료합니다"
