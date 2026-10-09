<#
.SYNOPSIS
  Reports what works on this PC: hardware, tools, models, services, and a per-feature verdict.

.PARAMETER InstallRoot  Where Sovereign was installed by setup-laptop.ps1 (default C:\Sovereign).
#>
[CmdletBinding()]
param([string]$InstallRoot = 'C:\Sovereign')

$ErrorActionPreference = 'Continue'
$Repo = Join-Path $InstallRoot 'sovereign-creative-studio'

# Paths come from the settings block that setup-laptop.ps1 wrote (so an existing ComfyUI elsewhere is honoured).
function Get-EnvValue([string]$Key, [string]$Default) {
  $file = Join-Path $Repo 'backend\.env'
  if (Test-Path $file) {
    $line = Get-Content $file | Where-Object { $_ -match ('^' + [regex]::Escape($Key) + '=') } | Select-Object -Last 1
    if ($line) { return ($line -split '=', 2)[1].Trim() }
  }
  return $Default
}
$Comfy = Get-EnvValue 'MUSIC_COMFYUI_DIR' (Join-Path $InstallRoot 'ComfyUI')
$ComfyPy = Get-EnvValue 'MUSIC_COMFYUI_PYTHON' (Join-Path $Comfy '.venv\Scripts\python.exe')
$StemsPy = Get-EnvValue 'MUSIC_STEMS_PYTHON' (Join-Path $InstallRoot 'stems\venv\Scripts\python.exe')
$LyricsModel = Get-EnvValue 'MUSIC_LYRICS_MODEL' 'gemma4:e4b'
$BackendPy = Join-Path $Repo 'backend\.venv\Scripts\python.exe'

$results = New-Object System.Collections.Generic.List[object]
function Add-Result([string]$Area, [string]$Verdict, [string]$Detail) { $results.Add([pscustomobject]@{ Area = $Area; Verdict = $Verdict; Detail = $Detail }) }
function Port-Open([int]$Port) {
  try { $c = New-Object System.Net.Sockets.TcpClient; $r = $c.BeginConnect('127.0.0.1', $Port, $null, $null); $ok = $r.AsyncWaitHandle.WaitOne(400); if ($ok) { $c.EndConnect($r) }; $c.Close(); return $ok } catch { return $false }
}
function Try-Run([string]$Exe, [string[]]$Arguments) {
  try { return ((& $Exe @Arguments 2>$null) | Out-String).Trim() } catch { return '' }
}

# ---- Hardware --------------------------------------------------------------------------------------------
$gpuName = ''; $vramGB = 0; $driver = ''
$smi = Try-Run 'nvidia-smi' @('--query-gpu=name,memory.total,driver_version', '--format=csv,noheader,nounits')
if ($smi) { $parts = $smi.Split(',') | ForEach-Object { $_.Trim() }; $gpuName = $parts[0]; $vramGB = [math]::Round([double]$parts[1] / 1024, 1); $driver = $parts[2] }
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 0)
$freeGB = [math]::Round((Get-PSDrive -Name ($InstallRoot.Substring(0, 1))).Free / 1GB, 0)
Write-Host ''
Write-Host "GPU:  $(if ($gpuName) { "$gpuName, $vramGB GB graphics memory, driver $driver" } else { 'no NVIDIA GPU found (nvidia-smi missing)' })"
Write-Host "RAM:  $ramGB GB     Free disk on $($InstallRoot.Substring(0,2)) $freeGB GB"

# ---- Tools -------------------------------------------------------------------------------------------------
$tools = [ordered]@{ python = 'python'; node = 'node'; git = 'git'; ffmpeg = 'ffmpeg'; ollama = 'ollama' }
foreach ($k in $tools.Keys) {
  $cmd = Get-Command $tools[$k] -ErrorAction SilentlyContinue
  if ($cmd) { Add-Result "Tool: $k" 'OK' $cmd.Source } else { Add-Result "Tool: $k" 'MISSING' 'not on PATH (open a new terminal after installing)' }
}

# ---- Installed pieces ------------------------------------------------------------------------------------------
$yue = Get-ChildItem -Path (Join-Path $Comfy 'models') -Recurse -Filter 'yue2*.safetensors' -ErrorAction SilentlyContinue | Select-Object -First 1
$sheet = Get-ChildItem -Path (Join-Path $Comfy 'models') -Recurse -Filter 'sheetsage*.safetensors' -ErrorAction SilentlyContinue | Select-Object -First 1
$modelsOk = [bool]$yue -and [bool]$sheet
Add-Result 'Music models (YuE2, SheetSage)' $(if ($modelsOk) { 'OK' } else { 'MISSING' }) $(if ($modelsOk) { "found in $Comfy\models" } else { "YuE2 and SheetSage files are not under $Comfy\models (checkpoints / audio_encoders)" })
$comfyTorch = ''
if (Test-Path $ComfyPy) { $comfyTorch = Try-Run $ComfyPy @('-c', 'import torch;print(torch.__version__, torch.cuda.is_available())') }
$cudaOk = $comfyTorch -match 'True$'
Add-Result 'Music engine Python (torch + CUDA)' $(if ($cudaOk) { 'OK' } elseif ($comfyTorch) { 'NO GPU' } else { 'MISSING' }) $(if ($comfyTorch) { $comfyTorch } else { "not built: $ComfyPy" })
$stems = ''
if (Test-Path $StemsPy) { $stems = Try-Run $StemsPy @('-c', 'import demucs, torch; print(demucs.__version__, torch.cuda.is_available())') }
Add-Result 'Vocal splitter (Demucs)' $(if ($stems) { 'OK' } else { 'MISSING' }) $(if ($stems) { $stems } else { 'stems venv not built' })
$backendImports = ''
if (Test-Path $BackendPy) { $backendImports = Try-Run $BackendPy @('-c', "import fastapi, faster_whisper, piper, numpy, PIL; print('ok')") }
Add-Result 'Backend packages' $(if ($backendImports -eq 'ok') { 'OK' } else { 'MISSING' }) $(if ($backendImports -eq 'ok') { 'fastapi, whisper, piper, numpy, pillow' } else { 'backend venv not built or incomplete' })
$build = Join-Path $Repo 'frontend\.next-cinematic-fixed\BUILD_ID'
Add-Result 'Frontend build' $(if (Test-Path $build) { 'OK' } else { 'MISSING' }) $build
$voice = Join-Path $Repo 'backend\storage\models\piper\en_US-lessac-low.onnx'
Add-Result 'Piper voice' $(if (Test-Path $voice) { 'OK' } else { 'MISSING' }) $voice
$ollamaList = Try-Run 'ollama' @('list')
foreach ($m in @($LyricsModel)) {
  Add-Result "Ollama model $m" $(if ($ollamaList -match [regex]::Escape($m)) { 'OK' } else { 'MISSING' }) $(if ($ollamaList) { 'listed by ollama' } else { 'ollama not running or not installed' })
}

# ---- Services ------------------------------------------------------------------------------------------------------------
foreach ($svc in @(@(11434, 'Ollama'), @(8002, 'Sovereign backend'), @(3000, 'Sovereign frontend'), @(8199, 'Music engine (starts on demand)'), @(8001, 'Main ComfyUI (image/video/avatar)'))) {
  $up = Port-Open $svc[0]
  Add-Result "Service: $($svc[1]) :$($svc[0])" $(if ($up) { 'RUNNING' } else { 'stopped' }) ''
}
$musicStatus = $null
if (Port-Open 8002) { try { $musicStatus = Invoke-RestMethod 'http://127.0.0.1:8002/api/music/status' -TimeoutSec 10 } catch { } }

# ---- Per-feature verdicts --------------------------------------------------------------------------------------------------
$verdicts = New-Object System.Collections.Generic.List[object]
function Verdict([string]$Feature, [string]$Rating, [string]$Why) { $verdicts.Add([pscustomobject]@{ Feature = $Feature; Rating = $Rating; Why = $Why }) }
$musicParts = $modelsOk -and $cudaOk
if (-not $gpuName) { Verdict 'Music Lab (songs, covers)' 'NO' 'needs an NVIDIA GPU' }
elseif (-not $musicParts) { Verdict 'Music Lab (songs, covers)' 'NOT READY' 'finish setup (models or engine Python missing)' }
elseif ($vramGB -ge 12) { Verdict 'Music Lab (songs, covers)' 'GOOD' "about 6 GB needed, $vramGB GB available" }
elseif ($vramGB -ge 7) { Verdict 'Music Lab (songs, covers)' 'OK, TIGHT' "about 6 GB needed of $vramGB GB; close other GPU programs while generating" }
else { Verdict 'Music Lab (songs, covers)' 'NO' "only $vramGB GB graphics memory" }
$lyricsOk = $ollamaList -match [regex]::Escape($LyricsModel)
if ($lyricsOk) { Verdict 'Lyric writer (idea to lyrics)' $(if ($vramGB -ge 12) { 'GOOD' } else { 'SLOWER' }) $(if ($vramGB -ge 12) { "$LyricsModel fits in graphics memory" } else { "$LyricsModel may spill into RAM on this GPU; a smaller model (for example qwen3:4b) is faster: set MUSIC_LYRICS_MODEL in backend\.env" }) }
else { Verdict 'Lyric writer (idea to lyrics)' 'NOT READY' "ollama model $LyricsModel missing (ollama pull $LyricsModel)" }
Verdict 'Dub plates (cuts, FX, version side)' $(if ($stems -and (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { 'GOOD' } else { 'NOT READY' }) 'needs ffmpeg and the Demucs splitter (about 3 GB graphics memory)'
Verdict 'Voice (spoken specials, narration)' $(if ((Test-Path $voice) -and $backendImports -eq 'ok') { 'GOOD' } else { 'NOT READY' }) 'Piper runs on the CPU'
Verdict 'Playback, visualizer, pages, Jarvis tools' $(if ($backendImports -eq 'ok' -and (Test-Path $build)) { 'GOOD' } else { 'NOT READY' }) 'no GPU needed'
if (Port-Open 8001) { Verdict 'Director, images, avatars (needs main ComfyUI)' $(if ($vramGB -ge 15) { 'POSSIBLE' } else { 'NOT RECOMMENDED' }) "video models need about 16 GB; this PC has $vramGB GB, so expect very slow or failed shots" }
else { Verdict 'Director, images, avatars (needs main ComfyUI)' 'OFF' 'the main ComfyUI and its video/image models are not installed here (see START_HERE.md section 10)' }

Write-Host ''; Write-Host 'Installed pieces and services' -ForegroundColor Cyan
$results | Format-Table -AutoSize -Wrap | Out-String -Width 200 | Write-Host
Write-Host 'What this PC can do' -ForegroundColor Cyan
$verdicts | Format-Table -AutoSize -Wrap | Out-String -Width 200 | Write-Host
if ($musicStatus) { Write-Host "Backend says the music engine is: $($musicStatus.engine.detail) (online: $($musicStatus.engine.online))" }
