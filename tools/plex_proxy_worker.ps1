param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{32}$')][string]$JobId)
$ErrorActionPreference = 'Stop'
$root = 'C:\Users\Plex\SovereignWorker'
$mutex = New-Object Threading.Mutex($false, 'Global\SovereignMediaWorker')
$locked = $false
try {
    $locked = $mutex.WaitOne(0)
    if (-not $locked) { exit 75 }
    if (Get-Process -Name 'Plex Transcoder' -ErrorAction SilentlyContinue) { exit 75 }
    $job = Join-Path $root "jobs\$JobId"
    $source = Join-Path $job 'source.mp4'
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw 'Missing input' }
    [Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'BelowNormal'
    $arguments = @('-hide_banner','-nostdin','-y','-loglevel','verbose','-threads','2',
        '-init_hw_device','d3d11va=dx:1','-init_hw_device','qsv=qs@dx',
        '-i',$source,'-map','0:v:0','-map','0:a?',
        '-vf','scale=w=min(1280\,iw):h=min(720\,ih):force_original_aspect_ratio=decrease:force_divisible_by=2',
        '-c:v','h264_qsv','-global_quality','25','-pix_fmt','nv12',
        '-c:a','aac','-b:a','128k','-movflags','+faststart',(Join-Path $job 'result.mp4'))
    $quoted = $arguments | ForEach-Object { '"' + $_ + '"' }
    $process = Start-Process -FilePath (Join-Path $root 'bin\ffmpeg.exe') -ArgumentList $quoted -WindowStyle Hidden -PassThru -RedirectStandardError (Join-Path $job 'encode.log') -RedirectStandardOutput (Join-Path $job 'stdout.log')
    while (-not $process.WaitForExit(1000)) {
        if (Get-Process -Name 'Plex Transcoder' -ErrorAction SilentlyContinue) {
            $process.Kill(); $process.WaitForExit(); exit 75
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $job 'result.mp4'))) { throw 'Missing encoder output' }
    if (-not (Select-String -LiteralPath (Join-Path $job 'encode.log') -SimpleMatch 'Intel(R) Arc(TM) B580' -Quiet)) { throw 'B580 not selected' }
    & (Join-Path $root 'bin\ffmpeg.exe') -v error -xerror -i (Join-Path $job 'result.mp4') -f null -
    if ($LASTEXITCODE -ne 0) { throw 'Output decode failed' }
    Write-Output 'completed'
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
