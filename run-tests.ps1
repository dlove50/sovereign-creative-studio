# Run backend tests, then frontend typecheck + production build.
# Usage:  powershell -ExecutionPolicy Bypass -File run-tests.ps1
$ErrorActionPreference = "Stop"

# --- Backend -----------------------------------------------------------------
$backend = Join-Path $PSScriptRoot "backend"
Set-Location $backend
if (-not (Test-Path ".venv")) {
    python -m venv .venv
    & ".\.venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
}
Write-Host "Running backend tests..." -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" -m pytest -q

# --- Frontend ----------------------------------------------------------------
$frontend = Join-Path $PSScriptRoot "frontend"
Set-Location $frontend
if (-not (Test-Path "node_modules")) { npm install }
Write-Host "Type-checking frontend..." -ForegroundColor Cyan
npm run typecheck
Write-Host "Building frontend..." -ForegroundColor Cyan
npm run build

Write-Host "All checks passed." -ForegroundColor Green
