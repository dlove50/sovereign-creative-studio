@echo off
setlocal EnableExtensions
set "LAUNCHER=C:\Users\David\Documents\Codex\sovereign-creative-studio\tools\Start-Unlimited-OCR.ps1"

if not exist "%LAUNCHER%" (
  echo Unlimited OCR launcher was not found:
  echo %LAUNCHER%
  pause
  exit /b 1
)

start "Unlimited OCR" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%LAUNCHER%"
exit /b 0
