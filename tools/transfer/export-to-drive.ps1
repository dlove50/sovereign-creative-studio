<#
.SYNOPSIS
  Builds the Sovereign transfer kit on a drive (default G:\Sovereign-Transfer).

.DESCRIPTION
  Copies everything needed to rebuild Sovereign Creative Studio on another Windows PC:
  the code, the database and settings, your stored data, the music engine (ComfyUI code and
  the YuE2 models), the local Ollama models Sovereign uses, package lock files, the setup and
  check scripts, and a full handoff (START_HERE.md) for an AI assistant. It finishes by
  writing MANIFEST.json (size and SHA256 of every file) so the copy can be verified.

  It never deletes anything outside the destination folder, and it only writes inside -Dest.

.PARAMETER DryRun            Show what would be copied and how big it is; copy nothing.
.PARAMETER IncludeVideoModels Also copy the main ComfyUI models (image, video, avatar). Needs a big drive.
.PARAMETER IncludeBackups    Also copy backend\storage\backups (about 29 GB of old snapshots).
.PARAMETER IncludeVideos     Also copy the generated videos (storage\videos, avatar_videos, captioned, director). Off by default: the video features are kept, the old videos are left behind.
.PARAMETER IncludeOllama     Also copy the Ollama models (about 11 GB). Off by default: the laptop already has Ollama.
.PARAMETER IncludeMusicModels Also copy the YuE2 and SheetSage models (about 5 GB). Off by default: the laptop already has YuE2.
.PARAMETER SkipHashes        Skip the SHA256 manifest (not recommended).
.PARAMETER ManifestOnly       Only (re)write MANIFEST.json for the existing kit in -Dest.
#>
[CmdletBinding()]
param(
  [string]$Dest = 'G:\Sovereign-Transfer',
  [switch]$DryRun,
  [switch]$IncludeVideoModels,
  [switch]$IncludeBackups,
  [switch]$IncludeVideos,
  [switch]$IncludeOllama,
  [switch]$IncludeMusicModels,
  [string]$AgentToolsDir = 'C:\Users\David\my-agent\tools\music',
  [string]$HarnessMusicPatch = 'C:\Users\David\Documents\Codex\deepseek-harness\.local\sovereign-music\sovereign-music.patch.yml',
  [switch]$SkipHashes,
  [switch]$ManifestOnly,
  [string[]]$OllamaModels = @('gemma4:e4b', 'qwen3:4b'),
  [string]$RepoRoot = '',
  [string]$ComfyDir = 'C:\Users\David\ComfyUI-Installs\ComfyUI\ComfyUI',
  [string]$ComfyVenv = 'C:\Users\David\Documents\ComfyUI\.venv',
  [string]$StemsVenv = 'C:\Users\David\Documents\Codex\sovereign-stems\venv',
  [string]$MainComfyBase = 'C:\Users\David\Documents\ComfyUI'
)

$ErrorActionPreference = 'Stop'
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path }
$script:Problems = New-Object System.Collections.Generic.List[string]

function Say([string]$Text, [string]$Color = 'Gray') { Write-Host $Text -ForegroundColor $Color }
function Step([string]$Text) { Write-Host ''; Write-Host "== $Text" -ForegroundColor Cyan }
function GB([double]$Bytes) { [math]::Round($Bytes / 1GB, 2) }

function Get-FolderBytes([string]$Path, [string[]]$ExcludeDirs = @()) {
  if (-not (Test-Path $Path)) { return 0 }
  $total = 0
  $stack = New-Object System.Collections.Generic.Stack[string]
  $stack.Push($Path)
  while ($stack.Count -gt 0) {
    $dir = $stack.Pop()
    try {
      foreach ($f in [System.IO.Directory]::EnumerateFiles($dir)) { $total += (New-Object System.IO.FileInfo $f).Length }
      foreach ($d in [System.IO.Directory]::EnumerateDirectories($dir)) {
        $name = Split-Path $d -Leaf
        $skip = $false
        foreach ($pattern in $ExcludeDirs) { if ($name -like $pattern -or $d -like $pattern) { $skip = $true; break } }
        if (-not $skip) { $stack.Push($d) }
      }
    } catch { }
  }
  return $total
}

function Invoke-Robo([string]$From, [string]$To, [string[]]$ExcludeDirs = @(), [string[]]$ExcludeFiles = @()) {
  New-Item -ItemType Directory -Force -Path $To | Out-Null
  $roboArgs = @($From, $To, '/E', '/R:1', '/W:1', '/MT:8', '/NFL', '/NDL', '/NJH', '/NP', '/COPY:DAT', '/DCOPY:DAT')
  if ($ExcludeDirs.Count) { $roboArgs += '/XD'; $roboArgs += $ExcludeDirs }
  if ($ExcludeFiles.Count) { $roboArgs += '/XF'; $roboArgs += $ExcludeFiles }
  & robocopy @roboArgs | Out-Null
  if ($LASTEXITCODE -ge 8) { $script:Problems.Add("robocopy failed ($LASTEXITCODE): $From") ; Say "  PROBLEM copying $From (robocopy code $LASTEXITCODE)" 'Red' }
}

function Write-Manifest([string]$Root) {
  Say '  hashing every file (this takes a few minutes)...'
  $rootFull = (Resolve-Path $Root).Path.TrimEnd('\')
  $entries = New-Object System.Collections.Generic.List[object]
  $bytes = [int64]0
  Get-ChildItem $Root -Recurse -File -Force | Where-Object { $_.Name -notin @('MANIFEST.json', 'export.log') } | ForEach-Object {
    $rel = $_.FullName.Substring($rootFull.Length + 1)
    $entries.Add([pscustomobject]@{ p = $rel; s = $_.Length; h = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash })
    $bytes += $_.Length
  }
  [pscustomobject]@{ created = (Get-Date).ToString('s'); files = $entries.Count; bytes = $bytes; entries = $entries } |
    ConvertTo-Json -Depth 4 -Compress | Set-Content -Path (Join-Path $Root 'MANIFEST.json') -Encoding UTF8
  Say "  MANIFEST.json written ($($entries.Count) files, $(GB $bytes) GB)"
}

function Copy-One([string]$From, [string]$ToDir) {
  if (-not (Test-Path $From)) { $script:Problems.Add("missing: $From"); Say "  missing: $From" 'Yellow'; return }
  New-Item -ItemType Directory -Force -Path $ToDir | Out-Null
  Copy-Item -LiteralPath $From -Destination $ToDir -Force
}

# ---- What gets left out of the code copy (rebuilt on the laptop, or just clutter) -----------------
$CodeExcludeDirs = @(
  'node_modules', '.venv', '.next', '.next-*', '__pycache__', '.pytest_cache', '.pytest-*', '.pytest_*', '.tmp*',
  'UsersDavid*', 'test-results', 'playwright-report', (Join-Path $RepoRoot 'backend\storage'),
  (Join-Path $RepoRoot '.git\refs\codex')  # editor checkpoint refs with extremely long names; not part of the history that matters
)
$CodeExcludeFiles = @('*.log', '*.err', '.codex-*', '*.pyc', '.tmp-*', '*.tsbuildinfo')

if ($ManifestOnly) { Write-Manifest $Dest; return }

$StorageRoot = Join-Path $RepoRoot 'backend\storage'
$StorageExcludeDirs = @('tmp', '_test_*', 'trash', 'secrets')
if (-not $IncludeBackups) { $StorageExcludeDirs += 'backups' }
if (-not $IncludeVideos) { $StorageExcludeDirs += @('videos', 'avatar_videos', 'captioned', 'director') }

$music = @(
  @{ From = Join-Path $ComfyDir 'models\checkpoints\yue2_3b_int8_convrot.safetensors'; To = 'models\music\ComfyUI\models\checkpoints' },
  @{ From = Join-Path $ComfyDir 'models\audio_encoders\sheetsage2_bf16.safetensors';   To = 'models\music\ComfyUI\models\audio_encoders' }
)

# ---- Plan and sizes -------------------------------------------------------------------------------------
Step 'Checking what will be copied'
$sizes = [ordered]@{}
$sizes['Code (Sovereign repo, no venv/node_modules/builds)'] = Get-FolderBytes $RepoRoot $CodeExcludeDirs
$sizes['Stored data (backend\storage)'] = Get-FolderBytes $StorageRoot $StorageExcludeDirs
$sizes['Music engine code (ComfyUI, no big models)'] = Get-FolderBytes $ComfyDir @('models', 'input', 'output', 'temp', 'user', '__pycache__')
if ($IncludeMusicModels) { $sizes['Music models (YuE2 + SheetSage)'] = ($music | ForEach-Object { if (Test-Path $_.From) { (Get-Item $_.From).Length } else { 0 } } | Measure-Object -Sum).Sum }
$sizes['Database + settings'] = (Get-Item (Join-Path $RepoRoot 'backend\sovereign.db') -ErrorAction SilentlyContinue).Length

function Get-OllamaStore {
  if ($env:OLLAMA_MODELS) { return $env:OLLAMA_MODELS }
  return (Join-Path $env:USERPROFILE '.ollama\models')
}
function Get-OllamaFiles([string]$Model) {
  $store = Get-OllamaStore
  $name, $tag = $Model.Split(':'); if (-not $tag) { $tag = 'latest' }
  $manifest = Join-Path $store "manifests\registry.ollama.ai\library\$name\$tag"
  if (-not (Test-Path $manifest)) { return $null }
  $json = Get-Content $manifest -Raw | ConvertFrom-Json
  $digests = @($json.config.digest) + @($json.layers | ForEach-Object { $_.digest })
  $blobs = $digests | ForEach-Object { Join-Path $store ('blobs\' + ($_ -replace ':', '-')) }
  return @{ Manifest = $manifest; Blobs = $blobs; Store = $store }
}
$ollamaBytes = 0
if ($IncludeOllama) {
  foreach ($m in $OllamaModels) {
    $files = Get-OllamaFiles $m
    if ($files) { foreach ($b in $files.Blobs) { if (Test-Path $b) { $ollamaBytes += (Get-Item $b).Length } } }
    else { Say "  Ollama model not found here: $m" 'Yellow' }
  }
  $sizes[('Ollama models (' + ($OllamaModels -join ', ') + ')')] = $ollamaBytes
}
if ($IncludeVideoModels) { $sizes['Main ComfyUI models (image/video/avatar)'] = Get-FolderBytes (Join-Path $MainComfyBase 'models') }

$totalBytes = 0
foreach ($k in $sizes.Keys) { $v = [double]$sizes[$k]; $totalBytes += $v; '{0,-62} {1,8} GB' -f $k, (GB $v) | Write-Host }
'{0,-62} {1,8} GB' -f 'TOTAL', (GB $totalBytes) | Write-Host -ForegroundColor White

$driveLetter = ([System.IO.Path]::GetPathRoot($Dest)).TrimEnd('\')
$drive = Get-PSDrive -Name $driveLetter.TrimEnd(':') -ErrorAction SilentlyContinue
if ($drive) {
  $free = $drive.Free
  Say ("Free space on {0}: {1} GB" -f $driveLetter, (GB $free))
  if ($free -lt ($totalBytes * 1.03 + 1GB)) { throw "Not enough free space on $driveLetter for this kit. Use -SkipOllama, a bigger drive, or fewer options." }
}
if ($DryRun) { Say ''; Say 'Dry run: nothing was copied.' 'Green'; return }

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Start-Transcript -Path (Join-Path $Dest 'export.log') -Force | Out-Null
try {

# USB sticks write small files very slowly (often under 1 MB/s) but big files at full speed. So everything
# is first staged on this PC's fast disk and then written to the drive as a few large tar archives.
$Stage = Join-Path $env:TEMP 'sovereign-kit-staging'
if (Test-Path $Stage) { cmd /c rd /s /q `"$Stage`" }  # cmd copes with the very long paths inside .git
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
$tar = (Get-Command tar.exe -ErrorAction Stop).Source

function Write-Tar([string]$StageDir, [string]$RootName, [string]$TarFile) {
  Say "  writing $(Split-Path $TarFile -Leaf) to the drive..."
  $out = Join-Path $Dest $TarFile
  if (Test-Path $out) { Remove-Item $out -Force }
  & $tar -cf $out -C $StageDir $RootName
  if ($LASTEXITCODE -ne 0) { $script:Problems.Add("tar failed for $TarFile"); Say "  PROBLEM: tar failed for $TarFile" 'Red' }
  else { Say ("  {0}: {1} GB" -f $TarFile, (GB (Get-Item $out).Length)) }
}

# ---- 1. Code ------------------------------------------------------------------------------------------------
Step '1/8 Code'
Invoke-Robo $RepoRoot (Join-Path $Stage 'code\sovereign-creative-studio') $CodeExcludeDirs $CodeExcludeFiles
Write-Tar (Join-Path $Stage 'code') 'sovereign-creative-studio' 'code.tar'

# ---- 2. Database, settings and data -----------------------------------------------------------------------------
Step '2/8 Database, settings and stored data'
$dataStage = Join-Path $Stage 'data-root\data'
New-Item -ItemType Directory -Force -Path (Join-Path $dataStage 'config') | Out-Null
$py = Join-Path $RepoRoot 'backend\.venv\Scripts\python.exe'
$dbSrc = Join-Path $RepoRoot 'backend\sovereign.db'
$dbDst = Join-Path $dataStage 'sovereign.db'
if (Test-Path $dbSrc) {
  # A consistent snapshot even while the backend is running (SQLite's own backup API).
  $code = 'import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()'
  & $py -c $code $dbSrc $dbDst
  if ($LASTEXITCODE -ne 0) { $script:Problems.Add('database snapshot failed'); Say '  database snapshot failed' 'Red' } else { Say "  database snapshot ok ($([math]::Round((Get-Item $dbDst).Length / 1MB, 1)) MB)" }
}
Copy-One (Join-Path $RepoRoot 'backend\.env') (Join-Path $dataStage 'config')
Copy-One (Join-Path $RepoRoot 'frontend\.env.local') (Join-Path $dataStage 'config')
Invoke-Robo $StorageRoot (Join-Path $dataStage 'backend-storage') $StorageExcludeDirs @()
Write-Tar (Join-Path $Stage 'data-root') 'data' 'data.tar'

# ---- 3. Secrets (kept apart so they can be deleted on their own) ---------------------------------------------------
Step '3/8 Secrets (kept in their own folder)'
$secretsSrc = Join-Path $StorageRoot 'secrets'
if (Test-Path $secretsSrc) { Invoke-Robo $secretsSrc (Join-Path $Dest 'secrets\backend-storage-secrets') @() @() }
Say '  The secrets folder holds your session secret and integration keys. Keep the drive safe (BitLocker To Go is advised).'

# ---- 4. Music engine (ComfyUI code, optional models) -------------------------------------------------------------------------
Step '4/8 Music engine'
# Code plus the empty model folders and small config files; the big model files are copied on purpose below.
Invoke-Robo $ComfyDir (Join-Path $Stage 'comfy\ComfyUI') @('input', 'output', 'temp', 'user', '__pycache__', '.git') @('*.pyc', '*.safetensors', '*.ckpt', '*.pt', '*.pth', '*.bin', '*.onnx', '*.gguf', '*.sft')
Write-Tar (Join-Path $Stage 'comfy') 'ComfyUI' 'comfyui.tar'
if ($IncludeMusicModels) { foreach ($m in $music) { Copy-One $m.From (Join-Path $Dest $m.To) } } else { Say '  models not included (the laptop already has YuE2); use -IncludeMusicModels to add them' }

# ---- 5. Ollama models ------------------------------------------------------------------------------------------------------
Step '5/8 Ollama models'
if (-not $IncludeOllama) { Say '  not included (the laptop already has Ollama); use -IncludeOllama to add the models' }
else {
  foreach ($m in $OllamaModels) {
    $files = Get-OllamaFiles $m
    if (-not $files) { continue }
    $dstStore = Join-Path $Dest 'ollama\models'
    $rel = $files.Manifest.Substring($files.Store.Length).TrimStart('\')
    Copy-One $files.Manifest (Split-Path (Join-Path $dstStore $rel) -Parent)
    foreach ($b in $files.Blobs) { Copy-One $b (Join-Path $dstStore 'blobs') }
    Say "  copied $m"
  }
}

# ---- 6. Optional video/image models + inventory ------------------------------------------------------------------------
Step '6/8 Model inventory'
$inv = New-Object System.Text.StringBuilder
[void]$inv.AppendLine('# Models on the original PC (what is and is not in this kit)')
[void]$inv.AppendLine('')
[void]$inv.AppendLine('Always included: Piper voices (inside data\backend-storage\models). Optional: YuE2 int8 checkpoint and SheetSage2 audio encoder (-IncludeMusicModels: ' + $IncludeMusicModels + '), Ollama models ' + ($OllamaModels -join ', ') + ' (-IncludeOllama: ' + $IncludeOllama + ').')
[void]$inv.AppendLine('')
[void]$inv.AppendLine('| Folder | File | Size (GB) |')
[void]$inv.AppendLine('|---|---|---|')
$mainModels = Join-Path $MainComfyBase 'models'
if (Test-Path $mainModels) {
  Get-ChildItem $mainModels -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Length -gt 50MB } | Sort-Object Length -Descending | ForEach-Object {
    [void]$inv.AppendLine(('| {0} | {1} | {2} |' -f $_.Directory.Name, $_.Name, (GB $_.Length)))
  }
}
New-Item -ItemType Directory -Force -Path (Join-Path $Dest 'models') | Out-Null
Set-Content -Path (Join-Path $Dest 'models\MODEL_INVENTORY.md') -Value $inv.ToString() -Encoding UTF8
if ($IncludeVideoModels -and (Test-Path $mainModels)) {
  Say '  copying the main ComfyUI models (large)...'
  Invoke-Robo $mainModels (Join-Path $Dest 'models\comfy-main\models') @() @()
}

# ---- 7. Lock files and versions -----------------------------------------------------------------------------------------------
Step '7/8 Package lock files and versions'
$locks = Join-Path $Dest 'locks'
New-Item -ItemType Directory -Force -Path $locks | Out-Null
function Save-Freeze([string]$VenvDir, [string]$File, [switch]$DropTorch) {
  $python = Join-Path $VenvDir 'Scripts\python.exe'
  if (-not (Test-Path $python)) { Say "  no venv at $VenvDir" 'Yellow'; return }
  $lines = & $python -m pip freeze 2>$null
  if ($DropTorch) { $lines = $lines | Where-Object { $_ -notmatch '^(torch|torchaudio|torchvision)==' } }
  $lines | Set-Content -Path (Join-Path $locks $File) -Encoding ASCII
  Say "  $File ($(@($lines).Count) packages)"
}
Save-Freeze (Join-Path $RepoRoot 'backend\.venv') 'backend-freeze.txt'
Save-Freeze $ComfyVenv 'comfyui-freeze-without-torch.txt' -DropTorch
Save-Freeze $StemsVenv 'stems-freeze.txt'
$versions = [ordered]@{
  created       = (Get-Date).ToString('s')
  source_pc     = $env:COMPUTERNAME
  backend_python = ((& $py --version) 2>&1 | Out-String).Trim()
  comfy_python   = ((& (Join-Path $ComfyVenv 'Scripts\python.exe') --version) 2>&1 | Out-String).Trim()
  node           = ((& node --version) 2>&1 | Out-String).Trim()
  comfyui        = (Select-String -Path (Join-Path $ComfyDir 'comfyui_version.py') -Pattern '__version__\s*=\s*"([^"]+)"' | ForEach-Object { $_.Matches[0].Groups[1].Value })
  torch          = ((& (Join-Path $ComfyVenv 'Scripts\python.exe') -c 'import torch;print(torch.__version__)') 2>&1 | Out-String).Trim()
  gpu            = ((& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader) 2>&1 | Out-String).Trim()
  ollama_models  = $OllamaModels
}
$versions | ConvertTo-Json | Set-Content -Path (Join-Path $locks 'versions.json') -Encoding UTF8

# ---- 8. Tools, handoff, manifest -----------------------------------------------------------------------------------------------------
Step '8/8 Scripts, handoff and manifest'
Invoke-Robo $ScriptDir (Join-Path $Dest 'tools') @() @()
# Agent tools: the music tool server for Jarvis / the DeepSeek harness and how the harness loads it.
New-Item -ItemType Directory -Force -Path (Join-Path $Dest 'extras\agent-music-tools') | Out-Null
Copy-One (Join-Path $AgentToolsDir 'server.py') (Join-Path $Dest 'extras\agent-music-tools')
Copy-One $HarnessMusicPatch (Join-Path $Dest 'extras\agent-music-tools')
$handoffBody = Join-Path $RepoRoot 'docs\LAPTOP_TRANSFER_HANDOFF.md'
$header = @"
# START HERE: Sovereign Creative Studio transfer kit

Created: $((Get-Date).ToString('yyyy-MM-dd HH:mm')) on $env:COMPUTERNAME.
Kit size: $(GB $totalBytes) GB. Video models included: $IncludeVideoModels. Backups included: $IncludeBackups. Generated videos included: $IncludeVideos. Ollama models included: $IncludeOllama. YuE2/SheetSage models included: $IncludeMusicModels.

"@
if (Test-Path $handoffBody) { Set-Content -Path (Join-Path $Dest 'START_HERE.md') -Value ($header + (Get-Content $handoffBody -Raw)) -Encoding UTF8 }
else { $script:Problems.Add('docs\LAPTOP_TRANSFER_HANDOFF.md is missing'); Say '  handoff document is missing' 'Red' }

if ($SkipHashes) { Say '  hashes skipped' 'Yellow' } else { Write-Manifest $Dest }

if (Test-Path $Stage) { cmd /c rd /s /q `"$Stage`" }
Step 'Done'
if ($script:Problems.Count -gt 0) {
  Say "Finished with $($script:Problems.Count) problem(s):" 'Yellow'
  $script:Problems | ForEach-Object { Say "  - $_" 'Yellow' }
} else { Say 'Finished with no problems.' 'Green' }
Say "Kit folder: $Dest"
Say 'On the laptop, open START_HERE.md and give it to the AI, or run tools\setup-laptop.ps1.'

} finally { Stop-Transcript | Out-Null }
