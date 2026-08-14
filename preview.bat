@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo config.yaml 조건에 맞는 공고를 찾습니다. (디스코드로 보내지 않습니다)
echo.
".venv\Scripts\python.exe" -m src.main --dry-run
echo.
pause
