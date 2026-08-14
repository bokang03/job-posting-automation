@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo 공고를 수집해 디스코드로 보냅니다.
echo (.env 파일에 DISCORD_WEBHOOK_URL 이 있어야 합니다)
echo.
".venv\Scripts\python.exe" -m src.main
echo.
pause
