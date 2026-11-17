@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. First run SETUP_WINDOWS.bat.
  pause
  exit /b 1
)
if not exist ".env" (
  echo .env missing. Run SETUP_WINDOWS.bat and configure the file first.
  pause
  exit /b 1
)
echo Dashboard: http://127.0.0.1:5000
echo Admin: http://127.0.0.1:5000/admin
echo Automatic AI operations: http://127.0.0.1:5000/operations
echo Press Ctrl+C to stop the server.
".venv\Scripts\python.exe" serve.py
pause
