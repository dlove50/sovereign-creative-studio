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
    $request = Get-Content -LiteralPath (Join-Path $job 'request.json') -Raw | ConvertFrom-Json
    $count = [int]$request.clip_count
    if ($count -lt 2 -or $count -gt 64) { throw 'Invalid clip count' }
    $arguments = @('-hide_banner','-nostdin','-y','-loglevel','verbose','-threads','2',
        '-init_hw_device','d3d11va=dx:1','-init_hw_device','qsv=qs@dx')
    $streams = ''
    for ($i=0; $i -lt $count; $i++) {
        $clip = Join-Path $job "clip-$i.mp4"
        if (-not (Test-Path -LiteralPath $clip -PathType Leaf)) { throw 'Missing clip' }
        $arguments += @('-i', $clip)
        $streams += "[${i}:v][${i}:a]"
    }
    $arguments += @('-filter_complex',"${streams}concat=n=${count}:v=1:a=1[v][a]",'-map','[v]','-map','[a]',
        '-c:v','h264_qsv','-global_quality','20','-pix_fmt','nv12','-c:a','aac','-movflags','+faststart',
        (Join-Path $job 'result.mp4'))
    # Launch only our encoder at below-normal priority. Plex processes are untouched.
    $quoted = $arguments | ForEach-Object { '"' + $_ + '"' }
    [Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'BelowNormal'
    $process = Start-Process -FilePath (Join-Path $root 'bin\ffmpeg.exe') -ArgumentList $quoted -WindowStyle Hidden -PassThru -RedirectStandardError (Join-Path $job 'encode.log') -RedirectStandardOutput (Join-Path $job 'stdout.log')
    # Retain the process handle so Windows PowerShell preserves its exit code.
    $null = $process.Handle
    while (-not $process.WaitForExit(1000)) {
        if (Get-Process -Name 'Plex Transcoder' -ErrorAction SilentlyContinue) {
            # Stop only our process; Sovereign falls back to local assembly.
            $process.Kill()
            $process.WaitForExit()
            exit 75
        }
    }
    if ($process.ExitCode -ne 0) { throw 'FFmpeg encoding failed; inspect encode.log' }
    if (-not (Select-String -LiteralPath (Join-Path $job 'encode.log') -SimpleMatch 'Intel(R) Arc(TM) B580' -Quiet)) { throw 'Expected B580 was not selected' }
    Write-Output 'completed'
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}

