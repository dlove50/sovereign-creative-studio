@echo off
setlocal EnableExtensions
title Stop Sovereign Creative Studio

set "APP_ROOT=C:\Users\David\Documents\Codex\sovereign-creative-studio"
set "PY=%APP_ROOT%\backend\.venv\Scripts\python.exe"

echo.
echo Stopping Sovereign Creative Studio local services...
echo.

if not exist "%PY%" (
  echo [ERROR] Backend Python venv not found: "%PY%"
  pause
  exit /b 1
)

"%PY%" "%APP_ROOT%\tools\local_launcher.py" stop
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Stop request complete.
pause
exit /b %EXIT_CODE%
