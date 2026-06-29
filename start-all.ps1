# Start backend and frontend in separate windows.
# Usage:  powershell -ExecutionPolicy Bypass -File start-all.ps1
$ErrorActionPreference = "Stop"

Start-Process powershell -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "start-backend.ps1")
)
Start-Process powershell -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "start-frontend.ps1")
)

Write-Host "Launched backend (:8000) and frontend (:3000) in separate windows." -ForegroundColor Green
