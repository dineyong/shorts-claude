@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3가 없습니다. https://www.python.org/downloads/ 에서 설치하세요 ^(설치 화면에서 "Add python.exe to PATH" 체크^).
  pause
  exit /b 1
)
if not exist .venv (
  echo 처음 실행: 필요한 부품을 설치합니다 ^(1~2분^)...
  python -m venv .venv
  .venv\Scripts\pip install -q -r requirements.txt
)
.venv\Scripts\python app.py
pause
