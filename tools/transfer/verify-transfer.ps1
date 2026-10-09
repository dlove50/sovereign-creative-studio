<#
.SYNOPSIS
  Checks that every file in the transfer kit is present and unchanged (size and SHA256 from MANIFEST.json).

.PARAMETER Root   The kit folder (default: the folder above this script).
.PARAMETER Quick  Compare file sizes only (fast). Without it, every file is hashed.
#>
[CmdletBinding()]
param(
  [string]$Root = '',
  [switch]$Quick
)

$ErrorActionPreference = 'Stop'
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $Root) { $Root = Split-Path -Parent $ScriptDir }
$manifestPath = Join-Path $Root 'MANIFEST.json'
if (-not (Test-Path $manifestPath)) { Write-Host "MANIFEST.json not found in $Root" -ForegroundColor Red; exit 2 }

$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$total = @($manifest.entries).Count
Write-Host ("Verifying {0} files ({1:N1} GB) in {2} {3}" -f $total, ($manifest.bytes / 1GB), $Root, $(if ($Quick) { '(sizes only)' } else { '(SHA256)' }))

$missing = New-Object System.Collections.Generic.List[string]
$wrongSize = New-Object System.Collections.Generic.List[string]
$wrongHash = New-Object System.Collections.Generic.List[string]
$i = 0
foreach ($e in $manifest.entries) {
  $i++
  if ($i % 500 -eq 0) { Write-Host ("  {0}/{1}" -f $i, $total) -ForegroundColor DarkGray }
  $path = Join-Path $Root $e.p
  if (-not (Test-Path -LiteralPath $path)) { $missing.Add($e.p); continue }
  if ((Get-Item -LiteralPath $path).Length -ne $e.s) { $wrongSize.Add($e.p); continue }
  if (-not $Quick) {
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $e.h) { $wrongHash.Add($e.p) }
  }
}

$bad = $missing.Count + $wrongSize.Count + $wrongHash.Count
if ($bad -eq 0) {
  Write-Host "All $total files are present and unchanged." -ForegroundColor Green
  exit 0
}
Write-Host "PROBLEMS: $($missing.Count) missing, $($wrongSize.Count) wrong size, $($wrongHash.Count) changed." -ForegroundColor Red
$missing | Select-Object -First 20 | ForEach-Object { Write-Host "  missing: $_" -ForegroundColor Yellow }
$wrongSize | Select-Object -First 20 | ForEach-Object { Write-Host "  wrong size: $_" -ForegroundColor Yellow }
$wrongHash | Select-Object -First 20 | ForEach-Object { Write-Host "  changed: $_" -ForegroundColor Yellow }
Write-Host 'Copy the kit from the original PC again (export-to-drive.ps1), or re-copy just those files.'
exit 1
