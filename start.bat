@echo off
title Scott's Finance
cd /d "%~dp0"
if not exist .venv (
  echo Setting up Python environment, first run only...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
if not exist .env (
  copy .env.example .env >nul
  echo.
  echo Created .env. Add your Plaid keys to it, then run start.bat again.
  notepad .env
  exit /b
)
if not exist frontend\dist\index.html (
  pushd frontend
  call npm install
  call npm run build
  popd
)
echo Starting at http://127.0.0.1:8765  (close this window to stop)
python backend\app.py
pause
