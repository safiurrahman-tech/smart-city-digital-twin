@echo off
cd /d "%~dp0"
echo === CitySync setup for Windows ===
where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python launcher not found. Install Python 3.11+ with the launcher first.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env - edit TOMTOM_API_KEY, ADMIN_PASSWORD, and SECRET_KEY.
) else (
  echo Existing .env kept unchanged.
)
echo Setup complete. Now configure .env and run START_WINDOWS.bat.
pause
exit /b 0
:failed
echo Setup failed. Check the output above.
pause
exit /b 1
