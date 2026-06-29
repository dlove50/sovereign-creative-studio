# Start the Sovereign Creative Studio frontend (http://localhost:3000).
# Usage (production, normal):  powershell -ExecutionPolicy Bypass -File start-frontend.ps1
# Usage (dev mode, rare):      powershell -ExecutionPolicy Bypass -File start-frontend.ps1 -Dev
#
# Build-directory isolation: production uses `.next`, dev uses `.next-dev`
# (next.config.mjs selects by NODE_ENV / NEXT_DIST_DIR), so dev can no longer
# corrupt the production build. Normal use of this script starts the stable
# PRODUCTION server (`npm.cmd run start`); dev mode is opt-in via -Dev.
# Still: do not run dev and production at the same time.
param(
    [switch]$Dev
)
$ErrorActionPreference = "Stop"
$frontend = Join-Path $PSScriptRoot "frontend"
Set-Location $frontend

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Cyan
    npm.cmd install
}
if (-not (Test-Path ".env.local")) {
    Copy-Item ".env.example" ".env.local"
    Write-Host "Created .env.local from .env.example." -ForegroundColor Cyan
}

if ($Dev) {
    # Guard: even with isolated build dirs, don't run dev while production is live
    # on 3000 (avoids port/back-end confusion). Dev uses .next-dev, prod uses .next.
    $prod = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
    if ($prod) {
        Write-Host "BLOCKED: production frontend is running on port 3000." -ForegroundColor Red
        Write-Host "Stop production launcher before using dev mode." -ForegroundColor Red
        Write-Host "(Stop-Sovereign-Creative-Studio.bat, or: python tools/local_launcher.py clean)" -ForegroundColor Red
        exit 1
    }
    # Dev writes to an isolated build dir (.next-dev), never the production .next.
    $env:NEXT_DIST_DIR = ".next-dev"
    Write-Host ""
    Write-Host "[DEV MODE] Starting next dev in isolated build dir .next-dev (production .next untouched)." -ForegroundColor Yellow
    Write-Host "Still do NOT run dev and production at the same time." -ForegroundColor Yellow
    Write-Host ""
    npm.cmd run dev
    return
}

# Production (default). Ensure a real production build exists before starting.
if (-not (Test-Path ".next/BUILD_ID")) {
    Write-Host "No production build found (.next/BUILD_ID missing)." -ForegroundColor Yellow
    Write-Host "Building frontend once (npm.cmd run build)..." -ForegroundColor Cyan
    npm.cmd run build
    if (-not (Test-Path ".next/BUILD_ID")) {
        Write-Host "[ERROR] Build did not produce .next/BUILD_ID." -ForegroundColor Red
        Write-Host "Run the clean recovery:  python tools/local_launcher.py clean" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Starting PRODUCTION frontend on http://localhost:3000 (Ctrl+C to stop)..." -ForegroundColor Green
npm.cmd run start
