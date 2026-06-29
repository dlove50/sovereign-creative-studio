@echo off
setlocal EnableExtensions
title Start Sovereign Creative Studio

set "APP_ROOT=C:\Users\David\Documents\Codex\sovereign-creative-studio"
set "PY=%APP_ROOT%\backend\.venv\Scripts\python.exe"

echo.
echo Starting Sovereign Creative Studio...
echo.

if not exist "%PY%" (
  echo [ERROR] Backend Python venv not found: "%PY%"
  pause
  exit /b 1
)

"%PY%" "%APP_ROOT%\tools\local_launcher.py" start --open-browser
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
  echo Startup failed. You can run Stop-Sovereign-Creative-Studio.bat to stop partial services.
) else (
  echo Startup complete.
)
pause
exit /b %EXIT_CODE%
