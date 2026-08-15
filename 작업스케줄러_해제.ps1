# 자동 실행을 중단합니다. 프로그램이나 설정은 지우지 않습니다.
# 다시 켜려면 작업스케줄러_등록.ps1 을 실행하세요.

$TaskName = "직무공고알림"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "'$TaskName' 자동 실행을 해제했습니다." -ForegroundColor Green
} else {
    Write-Host "'$TaskName' 이 등록되어 있지 않습니다." -ForegroundColor Yellow
}

Read-Host "엔터를 누르면 종료합니다"
