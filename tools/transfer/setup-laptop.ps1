<#
.SYNOPSIS
  Rebuilds Sovereign Creative Studio on this PC from the transfer kit.

.DESCRIPTION
  Run from the kit folder:  powershell -ExecutionPolicy Bypass -File tools\setup-laptop.ps1 -InstallPrereqs
  It verifies the kit, installs missing tools (with -InstallPrereqs), copies the code and data, rewrites
  paths for this PC, builds the Python environments and the web front end, makes launchers, runs the tests
  and finishes with a readiness report.

  It reuses what is already installed here: an existing Ollama (and its models), and an existing ComfyUI
  that already has the YuE2 model (found automatically, or give -ComfyDir and -ComfyPython).
  It is safe to run again: finished work is reused, and an existing database is backed up first.
  It needs internet for packages (PyPI, npm, PyTorch when it builds the music engine) and a small Demucs weights file.

.PARAMETER InstallRoot       Where to install (default C:\Sovereign).
.PARAMETER InstallPrereqs    Use winget to install Python 3.13, Node LTS, Git and ffmpeg when missing (Ollama is only needed for lyric writing).
.PARAMETER ComfyDir          An existing ComfyUI folder (the one with main.py) that has the YuE2 model.
.PARAMETER ComfyPython       The python.exe that runs that ComfyUI.
.PARAMETER LyricsModel       Ollama model used to write lyrics and plan stories (default: gemma4:e4b if present, else a small installed model).
.PARAMETER SkipVerify        Do not re-check the kit's hashes.
.PARAMETER SkipFrontendBuild Do not build the web front end.
.PARAMETER SkipTests         Do not run the test suite at the end.
.PARAMETER NoShortcut        Do not create the desktop shortcut.
.PARAMETER TorchCuda         cu130, cu128 or cu126 (only when building a music engine). Default: chosen from the NVIDIA driver.
.PARAMETER DryRun            Print what was detected; change nothing.
#>
[CmdletBinding()]
param(
  [string]$InstallRoot = 'C:\Sovereign',
  [switch]$InstallPrereqs,
  [string]$ComfyDir = '',
  [string]$ComfyPython = '',
  [string]$LyricsModel = '',
  [switch]$SkipVerify,
  [switch]$SkipFrontendBuild,
  [switch]$SkipTests,
  [switch]$NoShortcut,
  [string]$TorchCuda = '',
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$Kit = Split-Path -Parent $ScriptDir
$Repo = Join-Path $InstallRoot 'sovereign-creative-studio'
$Backend = Join-Path $Repo 'backend'
$Frontend = Join-Path $Repo 'frontend'
$Stems = Join-Path $InstallRoot 'stems\venv'
$YueName = 'yue2_3b_int8_convrot.safetensors'
$Warnings = New-Object System.Collections.Generic.List[string]

function Say([string]$Text, [string]$Color = 'Gray') { Write-Host $Text -ForegroundColor $Color }
function Phase([string]$Text) { Write-Host ''; Write-Host "=== $Text" -ForegroundColor Cyan }
function Warn([string]$Text) { $Warnings.Add($Text); Say "  WARNING: $Text" 'Yellow' }
function Test-Tool([string]$Name) { return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

function Refresh-Path {
  $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
  $user = [Environment]::GetEnvironmentVariable('Path', 'User')
  $env:Path = "$machine;$user"
}

function Run([string]$Exe, [string[]]$Arguments, [string]$WorkDir = '', [switch]$AllowFail) {
  $shown = "$Exe $($Arguments -join ' ')"
  Say "  > $shown" 'DarkGray'
  if ($WorkDir) { Push-Location $WorkDir }
  try { & $Exe @Arguments | Out-Host; $code = $LASTEXITCODE } finally { if ($WorkDir) { Pop-Location } }
  if ($code -ne 0 -and -not $AllowFail) { throw "Command failed ($code): $shown" }
  return $code
}

function Copy-Tree([string]$From, [string]$To) {
  if (-not (Test-Path $From)) { Warn "missing in kit: $From"; return }
  New-Item -ItemType Directory -Force -Path $To | Out-Null
  & robocopy $From $To /E /R:1 /W:1 /MT:8 /NFL /NDL /NJH /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "Copy failed ($LASTEXITCODE): $From" }
}

function Find-Python {
  foreach ($candidate in @(@('py', '-3.13'), @('py', '-3.12'), @('python'), @('python3'))) {
    $exe = $candidate[0]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $extra = @(); if ($candidate.Count -gt 1) { $extra = @($candidate[1]) }
    $path = (& $exe @extra -c 'import sys;print(sys.executable)' 2>$null | Out-String).Trim()
    $ver = (& $exe @extra -c "import sys;print(str(sys.version_info[0])+'.'+str(sys.version_info[1]))" 2>$null | Out-String).Trim()
    if ($path -and $ver) {
      $parts = $ver.Split('.'); if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 12) { return @{ Path = $path; Version = $ver } }
    }
  }
  return $null
}

function Get-CudaTag {
  if ($TorchCuda) { return $TorchCuda }
  $out = (& nvidia-smi 2>$null | Out-String)
  if ($out -match 'CUDA Version:\s*(\d+)\.(\d+)') {
    $major = [int]$Matches[1]; $minor = [int]$Matches[2]
    if ($major -ge 13) { return 'cu130' }
    if ($major -eq 12 -and $minor -ge 8) { return 'cu128' }
    return 'cu126'
  }
  return ''
}

# An existing ComfyUI that can run the YuE2 music engine: has main.py, the YuE2 nodes, and a python that runs it.
function Find-PythonFor([string]$Dir) {
  $parent = Split-Path -Parent $Dir
  foreach ($c in @((Join-Path $Dir '.venv\Scripts\python.exe'), (Join-Path $parent '.venv\Scripts\python.exe'), (Join-Path $parent 'python_embeded\python.exe'),
                   (Join-Path $env:USERPROFILE 'Documents\ComfyUI\.venv\Scripts\python.exe'))) { if (Test-Path $c) { return $c } }
  return ''
}
function Find-ExistingComfy {
  $roots = @($env:USERPROFILE, (Join-Path $env:USERPROFILE 'Documents'), 'C:\', 'D:\', (Join-Path $env:LOCALAPPDATA 'Programs'), 'C:\Program Files') | Where-Object { $_ -and (Test-Path $_) }
  $dirs = New-Object System.Collections.Generic.List[string]
  foreach ($r in $roots) {
    foreach ($sub in @('ComfyUI', 'ComfyUI\ComfyUI', 'ComfyUI_windows_portable\ComfyUI', 'ComfyUI-Installs\ComfyUI\ComfyUI', 'ComfyUI\resources\ComfyUI', 'ComfyUI-Shared')) {
      $d = Join-Path $r $sub
      if ((Test-Path (Join-Path $d 'main.py')) -and (Test-Path (Join-Path $d 'comfy'))) { $dirs.Add($d) }
    }
  }
  foreach ($d in $dirs) {
    if (Test-Path (Join-Path $d 'comfy_extras\nodes_yue2.py')) { return $d }
  }
  return ''
}

# ---- Detect ---------------------------------------------------------------------------------------------------------------
Phase 'Kit check and what is already on this PC'
foreach ($need in @('code.tar', 'data.tar', 'locks')) {
  if (-not (Test-Path (Join-Path $Kit $need))) { throw "This does not look like the transfer kit: missing $need (looking in $Kit)" }
}
Say "Kit:     $Kit"
Say "Install: $InstallRoot"
Refresh-Path
$py = Find-Python
Say ("Python:  {0}" -f $(if ($py) { "$($py.Version) at $($py.Path)" } else { 'not found' }))
foreach ($t in @('node', 'git', 'ffmpeg', 'ollama', 'nvidia-smi', 'winget')) { Say ("{0,-11}{1}" -f "${t}:", $(if (Test-Tool $t) { 'found' } else { 'not found' })) }

$useExistingComfy = $false
if (-not $ComfyDir) { $ComfyDir = Find-ExistingComfy }
if ($ComfyDir -and (Test-Path (Join-Path $ComfyDir 'main.py'))) {
  if (-not $ComfyPython) { $ComfyPython = Find-PythonFor $ComfyDir }
  $hasNodes = Test-Path (Join-Path $ComfyDir 'comfy_extras\nodes_yue2.py')
  Say "ComfyUI: existing at $ComfyDir (YuE2 nodes: $hasNodes; python: $(if ($ComfyPython) { $ComfyPython } else { 'not found' }))"
  if ($hasNodes -and $ComfyPython) { $useExistingComfy = $true } else { Say '  That ComfyUI cannot be used for songs (needs YuE2 nodes, ComfyUI 0.37+, and its python). A new one will be built from the kit.' 'Yellow' }
} else { Say 'ComfyUI: none found with YuE2 nodes; one will be built from the kit.' }
if ($useExistingComfy) {
  $Comfy = $ComfyDir
  $yuePath = Get-ChildItem -Path (Join-Path $Comfy 'models') -Recurse -Filter 'yue2*.safetensors' -ErrorAction SilentlyContinue | Select-Object -First 1
  Say ("YuE2 model: {0}" -f $(if ($yuePath) { $yuePath.FullName } else { 'not in that ComfyUI\models (will copy from the kit if the kit has it)' }))
} else { $Comfy = Join-Path $InstallRoot 'ComfyUI'; $ComfyPython = Join-Path $Comfy '.venv\Scripts\python.exe' }

$ollamaModels = @()
if (Test-Tool 'ollama') { $ollamaModels = @((& ollama list 2>$null) | Select-Object -Skip 1 | ForEach-Object { ($_ -split '\s+')[0] } | Where-Object { $_ }) }
Say ("Ollama models here: {0}" -f $(if ($ollamaModels.Count) { $ollamaModels -join ', ' } else { 'none listed (Ollama not running or no models)' }))

if ($DryRun) { Say ''; Say 'Dry run: nothing was changed.' 'Green'; return }

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
Start-Transcript -Path (Join-Path $InstallRoot 'setup.log') -Append | Out-Null
try {

# ---- 1. Verify -------------------------------------------------------------------------------------------------------------------
Phase '1/10 Verify the kit'
if ($SkipVerify) { Say '  skipped' }
else { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ScriptDir 'verify-transfer.ps1') -Root $Kit; if ($LASTEXITCODE -ne 0) { throw 'The kit is damaged. Copy it again from the original PC, then re-run.' } }

# ---- 2. Tools ---------------------------------------------------------------------------------------------------------------------------
Phase '2/10 Tools'
$wanted = @(
  @{ Name = 'python'; Id = 'Python.Python.3.13'; Present = [bool]$py },
  @{ Name = 'node';   Id = 'OpenJS.NodeJS.LTS';  Present = (Test-Tool 'node') },
  @{ Name = 'git';    Id = 'Git.Git';            Present = (Test-Tool 'git') },
  @{ Name = 'ffmpeg'; Id = 'Gyan.FFmpeg';        Present = (Test-Tool 'ffmpeg') }
)
$missing = @($wanted | Where-Object { -not $_.Present })
if ($missing.Count -gt 0) {
  if ($InstallPrereqs -and (Test-Tool 'winget')) {
    foreach ($m in $missing) { Run 'winget' @('install', '-e', '--id', $m.Id, '--accept-package-agreements', '--accept-source-agreements', '--silent') -AllowFail | Out-Null }
    Refresh-Path
    $py = Find-Python
  } else {
    Say '  Missing tools. Install them, open a NEW terminal, and run this script again (or add -InstallPrereqs):' 'Yellow'
    foreach ($m in $missing) { Say "    winget install -e --id $($m.Id)" 'Yellow' }
    throw 'Required tools are missing.'
  }
}
if (-not $py) { throw 'Python 3.12 or newer was not found even after installing. Open a new terminal and run again.' }
foreach ($t in @('node', 'git', 'ffmpeg')) { if (-not (Test-Tool $t)) { throw "$t is still not on PATH. Open a new terminal and run again." } }
if (-not (Test-Tool 'nvidia-smi')) { Warn 'nvidia-smi was not found. Install the NVIDIA driver; songs need the GPU.' }
if (-not (Test-Tool 'ollama')) { Warn 'Ollama is not installed. Lyric writing and some AI text features need it (winget install -e --id Ollama.Ollama).' }
$ffmpegExe = (Get-Command ffmpeg).Source
Say "  Python $($py.Version), Node $((& node --version)), ffmpeg at $ffmpegExe" 'Green'

# ---- 3. Copy -------------------------------------------------------------------------------------------------------------------------------
Phase '3/10 Copy files from the kit'
function Expand-Kit([string]$TarName, [string]$Into) {
  $file = Join-Path $Kit $TarName
  if (-not (Test-Path $file)) { throw "Kit file missing: $file" }
  New-Item -ItemType Directory -Force -Path $Into | Out-Null
  Say "  unpacking $TarName ..."
  & tar.exe -xf $file -C $Into
  if ($LASTEXITCODE -ne 0) { throw "Could not unpack $TarName" }
}
Expand-Kit 'code.tar' $InstallRoot
$dbTarget = Join-Path $Backend 'sovereign.db'
if (Test-Path $dbTarget) { $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'; Copy-Item $dbTarget "$dbTarget.bak-$stamp"; Say "  existing database backed up as sovereign.db.bak-$stamp" }
$unpack = Join-Path $InstallRoot '_kit_unpack'
if (Test-Path $unpack) { Remove-Item $unpack -Recurse -Force }
Expand-Kit 'data.tar' $unpack
Copy-Item (Join-Path $unpack 'data\sovereign.db') $dbTarget -Force
Copy-Item (Join-Path $unpack 'data\config\.env') (Join-Path $Backend '.env') -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $unpack 'data\config\.env.local') (Join-Path $Frontend '.env.local') -Force -ErrorAction SilentlyContinue
Copy-Tree (Join-Path $unpack 'data\backend-storage') (Join-Path $Backend 'storage')
Remove-Item $unpack -Recurse -Force
if (Test-Path (Join-Path $Kit 'secrets\backend-storage-secrets')) { Copy-Tree (Join-Path $Kit 'secrets\backend-storage-secrets') (Join-Path $Backend 'storage\secrets') }
if (-not $useExistingComfy) { Expand-Kit 'comfyui.tar' $InstallRoot }
$kitModels = Join-Path $Kit 'models\music\ComfyUI\models'
if (Test-Path $kitModels) {
  $haveYue = [bool](Get-ChildItem -Path (Join-Path $Comfy 'models') -Recurse -Filter 'yue2*.safetensors' -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($haveYue) { Say '  YuE2 model already present here; the kit''s copy is not needed.' } else { Copy-Tree $kitModels (Join-Path $Comfy 'models'); Say '  YuE2 and SheetSage models copied from the kit.' }
} elseif (-not (Get-ChildItem -Path (Join-Path $Comfy 'models') -Recurse -Filter 'yue2*.safetensors' -ErrorAction SilentlyContinue | Select-Object -First 1)) {
  Warn "The YuE2 model ($YueName) is not in $Comfy\models\checkpoints and the kit does not contain it. Put it there (and sheetsage2_bf16.safetensors in models\audio_encoders)."
}
Say '  files copied' 'Green'

# ---- 4. Settings ------------------------------------------------------------------------------------------------------------------------------------
Phase '4/10 Write settings for this PC'
if (Test-Tool 'ollama') { $ollamaModels = @((& ollama list 2>$null) | Select-Object -Skip 1 | ForEach-Object { ($_ -split '\s+')[0] } | Where-Object { $_ }) }
if (-not $LyricsModel) {
  foreach ($pref in @('gemma4:e4b', 'qwen3:4b', 'llama3.2:3b', 'llama3.1:8b', 'llama3.2:latest', 'llama3:latest')) { if ($ollamaModels -contains $pref) { $LyricsModel = $pref; break } }
  if (-not $LyricsModel -and $ollamaModels.Count) { $LyricsModel = $ollamaModels[0] }
  if (-not $LyricsModel) { $LyricsModel = 'gemma4:e4b'; Warn 'No Ollama model found. Run: ollama pull gemma4:e4b   (about 9.6 GB) or: ollama pull qwen3:4b   (about 2.5 GB, faster on 8 GB graphics memory)' }
}
Say "  lyric and story model: $LyricsModel"
$envFile = Join-Path $Backend '.env'
$overrideKeys = @('FFMPEG_PATH', 'MUSIC_COMFYUI_DIR', 'MUSIC_COMFYUI_PYTHON', 'MUSIC_STEMS_PYTHON', 'MUSIC_LYRICS_MODEL', 'VIDEO_AGENT_OLLAMA_BASE_URL', 'VIDEO_AGENT_MODEL', 'DIRECTOR_FAST_PLANNER_MODEL')
$marker = '# --- settings written by setup-laptop.ps1 (safe to edit below this line) ---'
$existing = @(); if (Test-Path $envFile) { $existing = Get-Content $envFile }
$kept = New-Object System.Collections.Generic.List[string]
foreach ($line in $existing) {
  if ($line -eq $marker) { break }
  $key = ($line -split '=', 2)[0].Trim()
  if ($overrideKeys -contains $key) { continue }
  $kept.Add($line)
}
$block = @(
  $marker,
  "FFMPEG_PATH=$ffmpegExe",
  "MUSIC_COMFYUI_DIR=$Comfy",
  "MUSIC_COMFYUI_PYTHON=$ComfyPython",
  "MUSIC_STEMS_PYTHON=$Stems\Scripts\python.exe",
  "MUSIC_LYRICS_MODEL=$LyricsModel",
  'VIDEO_AGENT_OLLAMA_BASE_URL=http://127.0.0.1:11434',
  "VIDEO_AGENT_MODEL=$LyricsModel",
  "DIRECTOR_FAST_PLANNER_MODEL=$LyricsModel"
)
# UTF-8 without a byte-order mark: python-dotenv would otherwise glue the mark onto the first setting's name.
[System.IO.File]::WriteAllLines($envFile, [string[]]($kept + $block), (New-Object System.Text.UTF8Encoding $false))
Say "  wrote $envFile" 'Green'

# ---- 5. Backend Python ------------------------------------------------------------------------------------------------------------------------------------
Phase '5/10 Backend Python environment'
$backendPy = Join-Path $Backend '.venv\Scripts\python.exe'
if (-not (Test-Path $backendPy)) { Run $py.Path @('-m', 'venv', (Join-Path $Backend '.venv')) }
Run $backendPy @('-m', 'pip', 'install', '--upgrade', 'pip') -AllowFail | Out-Null
$lock = Join-Path $Kit 'locks\backend-freeze.txt'
$code = 1
if (Test-Path $lock) { $code = Run $backendPy @('-m', 'pip', 'install', '-r', $lock) -AllowFail }
if ($code -ne 0) { Warn 'The exact package list failed; falling back to requirements.txt (versions may differ).'; Run $backendPy @('-m', 'pip', 'install', '-r', (Join-Path $Backend 'requirements.txt')) }

# ---- 6. Front end -----------------------------------------------------------------------------------------------------------------------------------------------
Phase '6/10 Web front end'
if ($SkipFrontendBuild) { Say '  skipped' }
else {
  if (Test-Path (Join-Path $Frontend 'package-lock.json')) { Run 'npm.cmd' @('ci', '--no-audit', '--no-fund') $Frontend } else { Run 'npm.cmd' @('install', '--no-audit', '--no-fund') $Frontend }
  $env:NEXT_DIST_DIR = '.next-cinematic-fixed'; $env:BACKEND_ORIGIN = 'http://127.0.0.1:8002'
  Run 'npm.cmd' @('run', 'build') $Frontend
}

# ---- 7. Music engine Python ------------------------------------------------------------------------------------------------------------------------------------------
Phase '7/10 Music engine Python'
if ($useExistingComfy) {
  Say "  using the existing ComfyUI python: $ComfyPython"
  & $ComfyPython -c "import torch;print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
} else {
  if (-not (Test-Path $ComfyPython)) { Run $py.Path @('-m', 'venv', (Join-Path $Comfy '.venv')) }
  Run $ComfyPython @('-m', 'pip', 'install', '--upgrade', 'pip') -AllowFail | Out-Null
  $tag = Get-CudaTag
  if (-not $tag) { Warn 'No NVIDIA driver found; installing CPU PyTorch (songs will not work without a GPU).'; $index = 'https://download.pytorch.org/whl/cpu' } else { $index = "https://download.pytorch.org/whl/$tag" }
  Say "  PyTorch from $index (several GB)"
  $code = Run $ComfyPython @('-m', 'pip', 'install', 'torch==2.10.0', 'torchaudio==2.10.0', '--index-url', $index) -AllowFail
  if ($code -ne 0) { Warn 'The pinned PyTorch 2.10.0 was not available for this CUDA build; installing the newest matching one.'; Run $ComfyPython @('-m', 'pip', 'install', 'torch', 'torchaudio', '--index-url', $index) }
  $comfyLock = Join-Path $Kit 'locks\comfyui-freeze-without-torch.txt'
  $code = 1
  if (Test-Path $comfyLock) { $code = Run $ComfyPython @('-m', 'pip', 'install', '-r', $comfyLock) -AllowFail }
  if ($code -ne 0) { Warn 'The exact ComfyUI package list failed; using ComfyUI''s own requirements.txt.'; Run $ComfyPython @('-m', 'pip', 'install', '-r', (Join-Path $Comfy 'requirements.txt')) }
  & $ComfyPython -c "import torch;print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
}

# ---- 8. Vocal splitter -----------------------------------------------------------------------------------------------------------------------------------------------------
Phase '8/10 Vocal splitter (Demucs)'
$stemsPy = Join-Path $Stems 'Scripts\python.exe'
# The splitter borrows the music engine's PyTorch, and PyTorch only loads on the Python version it was built for.
# So the splitter's environment must be made from the SAME base Python as the music engine's.
$ownTorch = $false
if (-not (Test-Path $stemsPy)) {
  $basePrefix = (& $ComfyPython -c 'import sys;print(sys.base_prefix)' 2>$null | Out-String).Trim()
  $stemsBase = if ($basePrefix) { Join-Path $basePrefix 'python.exe' } else { '' }
  $made = 1
  if ($stemsBase -and (Test-Path $stemsBase)) { $made = Run $stemsBase @('-m', 'venv', $Stems) -AllowFail }
  if ($made -ne 0) {
    Warn 'Could not make the splitter environment from the music engine''s Python; using the system Python and giving it its own PyTorch (a large download).'
    Run $py.Path @('-m', 'venv', $Stems)
    $ownTorch = $true
  }
}
if ($ownTorch) {
  $tag = Get-CudaTag
  $index = if ($tag) { "https://download.pytorch.org/whl/$tag" } else { 'https://download.pytorch.org/whl/cpu' }
  Run $stemsPy @('-m', 'pip', 'install', 'torch', 'torchaudio', '--index-url', $index)
} else {
  $comfySite = (& $ComfyPython -c 'import site;print(site.getsitepackages()[-1])' 2>$null | Out-String).Trim()
  if ($comfySite -and (Test-Path $comfySite)) {
    $sp = Join-Path $Stems 'Lib\site-packages'
    Set-Content -Path (Join-Path $sp 'comfy_torch.pth') -Value $comfySite -Encoding ASCII  # shares the music engine's torch
  } else { Warn 'Could not find the music engine''s packages folder; Demucs needs its own PyTorch (pip install torch in stems\venv).' }
}
Run $stemsPy @('-m', 'pip', 'install', '--upgrade', 'pip') -AllowFail | Out-Null
Run $stemsPy @('-m', 'pip', 'install', 'demucs')
Say '  fetching the small Demucs model file (about 80 MB, once)...'
$check = Run $stemsPy @('-c', "import demucs, torch; print('demucs', demucs.__version__, 'torch', torch.__version__, 'cuda', torch.cuda.is_available())") -AllowFail
if ($check -ne 0) { Warn 'Demucs could not import PyTorch. Dub plate version sides and sung specials will not work until the splitter environment is fixed (see START_HERE.md section 12).' }
else { Run $stemsPy @('-c', "from demucs.pretrained import get_model; get_model('htdemucs'); print('demucs model ready')") -AllowFail | Out-Null }

# ---- 9. Launchers ----------------------------------------------------------------------------------------------------------------------------------------------------------------------
Phase '9/10 Launchers'
$startBat = @"
@echo off
rem Starts Sovereign Creative Studio (backend, web page and, when needed, the music engine).
setlocal
set "ROOT=$InstallRoot"
set "NEXT_DIST_DIR=.next-cinematic-fixed"
set "BACKEND_ORIGIN=http://127.0.0.1:8002"
where ollama >nul 2>nul && (tasklist /FI "IMAGENAME eq ollama.exe" | find /I "ollama.exe" >nul || start "" /min ollama serve)
"%ROOT%\sovereign-creative-studio\backend\.venv\Scripts\python.exe" "%ROOT%\sovereign-creative-studio\tools\local_launcher.py" start --skip-comfy --open-browser
echo.
echo Sovereign is running at http://localhost:3000  (Music Lab: http://localhost:3000/music-lab)
pause
"@
$stopBat = @"
@echo off
"$InstallRoot\sovereign-creative-studio\backend\.venv\Scripts\python.exe" "$InstallRoot\sovereign-creative-studio\tools\local_launcher.py" stop
pause
"@
$checkBat = @"
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "$InstallRoot\tools\check-readiness.ps1" -InstallRoot "$InstallRoot"
pause
"@
Set-Content -Path (Join-Path $InstallRoot 'Start-Sovereign.bat') -Value $startBat -Encoding ASCII
Set-Content -Path (Join-Path $InstallRoot 'Stop-Sovereign.bat') -Value $stopBat -Encoding ASCII
Set-Content -Path (Join-Path $InstallRoot 'Check-Readiness.bat') -Value $checkBat -Encoding ASCII
Copy-Tree $ScriptDir (Join-Path $InstallRoot 'tools')
if (Test-Path (Join-Path $Kit 'extras')) { Copy-Tree (Join-Path $Kit 'extras') (Join-Path $InstallRoot 'extras') }
if (-not $NoShortcut) { try {
  $shell = New-Object -ComObject WScript.Shell
  $lnk = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Sovereign Creative Studio.lnk'))
  $lnk.TargetPath = Join-Path $InstallRoot 'Start-Sovereign.bat'
  $lnk.WorkingDirectory = $InstallRoot
  $lnk.Save()
  Say '  desktop shortcut created' 'Green'
} catch { Warn 'Could not create the desktop shortcut; use Start-Sovereign.bat.' } }

# ---- 10. Tests and readiness -----------------------------------------------------------------------------------------------------------------------------------------------------------
Phase '10/10 Tests and readiness'
if ($SkipTests) { Say '  tests skipped' }
else {
  $tests = @('tests/test_music.py', 'tests/test_music_playback.py', 'tests/test_dubplate.py', 'tests/test_director.py', 'tests/test_cinematic_planner.py')
  $code = Run $backendPy (@('-m', 'pytest') + $tests + @('-q')) $Backend -AllowFail
  if ($code -ne 0) { Warn 'Some tests failed. See the output above; START_HERE.md section 8 explains what each failure usually means.' } else { Say '  tests passed' 'Green' }
}
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallRoot 'tools\check-readiness.ps1') -InstallRoot $InstallRoot

Phase 'Finished'
if ($Warnings.Count -gt 0) { Say "$($Warnings.Count) warning(s):" 'Yellow'; $Warnings | ForEach-Object { Say "  - $_" 'Yellow' } }
Say "Start it with: $InstallRoot\Start-Sovereign.bat  (or the desktop shortcut)" 'Green'
Say 'Then open http://localhost:3000/music-lab and make a 60 second song to confirm everything works.' 'Green'

} finally { Stop-Transcript | Out-Null }
