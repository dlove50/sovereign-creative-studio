# Start the Sovereign Creative Studio backend (http://localhost:8000).
# Usage:  powershell -ExecutionPolicy Bypass -File start-backend.ps1
$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "backend"
Set-Location $backend

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
}

$py = Join-Path $backend ".venv\Scripts\python.exe"
Write-Host "Installing backend dependencies..." -ForegroundColor Cyan
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r requirements.txt

Write-Host "Starting backend on http://localhost:8000 (Ctrl+C to stop)..." -ForegroundColor Green
& $py -m uvicorn app.main:app --reload --port 8000
