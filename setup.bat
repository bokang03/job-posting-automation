@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo [1/2] 파이썬 가상환경을 만듭니다...
python -m venv .venv
if errorlevel 1 (
    echo.
    echo 파이썬을 찾지 못했습니다. https://www.python.org 에서 설치한 뒤 다시 실행해주세요.
    echo 설치할 때 "Add python.exe to PATH" 를 반드시 체크하세요.
    pause
    exit /b 1
)

echo [2/2] 필요한 패키지를 설치합니다...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo 패키지 설치에 실패했습니다.
    pause
    exit /b 1
)

echo.
echo 설치가 끝났습니다. 이제 preview.bat 을 실행해 어떤 공고가 걸리는지 확인해보세요.
pause
