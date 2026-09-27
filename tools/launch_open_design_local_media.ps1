$ErrorActionPreference = 'Stop'

$studio = 'C:\Users\David\Documents\Codex\sovereign-creative-studio'
$launcher = Join-Path $studio 'tools\local_launcher.py'
$openDesign = 'C:\Users\David\AppData\Local\Programs\Open Design\Open Design.exe'
$logDir = Join-Path $studio '.local\logs'

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Test-LocalUrl([string]$Url) {
  try {
    Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2 | Out-Null
    return $true
  } catch {
    return $false
  }
}

if (-not (Test-LocalUrl 'http://127.0.0.1:8001/system_stats') -or
    -not (Test-LocalUrl 'http://127.0.0.1:8002/api/health')) {
  $python = (Get-Command python.exe -ErrorAction Stop).Source
  Start-Process -FilePath $python `
    -ArgumentList @($launcher, 'start', '--hidden') `
    -WorkingDirectory $studio `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir 'open-design-media.out.log') `
    -RedirectStandardError (Join-Path $logDir 'open-design-media.err.log')

  for ($attempt = 0; $attempt -lt 180; $attempt++) {
    if ((Test-LocalUrl 'http://127.0.0.1:8001/system_stats') -and
        (Test-LocalUrl 'http://127.0.0.1:8002/api/health')) { break }
    Start-Sleep -Seconds 1
  }
}

if (-not (Get-Process -Name 'Open Design' -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath $openDesign
}
