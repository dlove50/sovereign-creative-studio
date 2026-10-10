@echo off
setlocal EnableExtensions
title Start Sovereign Creative Studio

set "APP_ROOT=C:\Users\David\Documents\Codex\sovereign-creative-studio"
set "PY=%APP_ROOT%\backend\.venv\Scripts\python.exe"
set "NEXT_DIST_DIR=.next-ui-final"
set "BACKEND_ORIGIN=http://127.0.0.1:8002"

echo.
echo Starting Sovereign Creative Studio...
echo.

where docker >nul 2>nul
if not errorlevel 1 (
  echo Starting Baidu Unlimited-OCR...
  docker start baidu-unlimited-ocr >nul 2>nul
  if errorlevel 1 echo [WARNING] OCR model could not start. Make sure Docker Desktop is running.
)

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
