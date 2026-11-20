@echo off
rem Starts SnackScout and a free Cloudflare tunnel so teammates can open it from anywhere.
rem The public link (https://....trycloudflare.com) appears in the "SnackScout tunnel" window
rem and changes every time you start this. Visitors need the TEAM_PASSWORD from .env.
cd /d "%~dp0"
if not exist .venv (
  echo First run: setting up...
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
findstr /b "TEAM_PASSWORD=" .env >nul 2>&1 || (
  echo.
  echo Add a line TEAM_PASSWORD=yourpassword to the .env file first, so strangers can't get in.
  pause
  exit /b 1
)
set CF="%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
if not exist %CF% set CF="%ProgramFiles%\cloudflared\cloudflared.exe"
if not exist %CF% (
  echo cloudflared is not installed. Run:  winget install --id Cloudflare.cloudflared
  pause
  exit /b 1
)
start "SnackScout server" .venv\Scripts\python app.py
timeout /t 5 /nobreak >nul
echo.
echo  Look for the line with  https://....trycloudflare.com  below - that's the link to share.
echo  Keep this window and the "SnackScout server" window open. Close both to stop.
echo.
%CF% tunnel --no-autoupdate --url http://localhost:5000
