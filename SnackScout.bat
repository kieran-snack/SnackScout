@echo off
cd /d "%~dp0"
if not exist .venv (
  echo First run: setting up...
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
start "" http://localhost:5000
.venv\Scripts\python app.py
