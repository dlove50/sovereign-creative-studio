param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{32}$')][string]$JobId)
$ErrorActionPreference='Stop'
$root='C:\Users\Plex\SovereignWorker'
$job=Join-Path $root "jobs\$JobId"
$request=Get-Content (Join-Path $job 'request.json') -Raw | ConvertFrom-Json
$mutex=New-Object Threading.Mutex($false,'Global\SovereignMediaWorker')
$locked=$false
if ((Test-Path (Join-Path $job 'result.mp4')) -and (Test-Path (Join-Path $job 'encode.log'))) {
    $log=Get-Content (Join-Path $job 'encode.log') -Raw
    if ($log.Contains('Intel(R) Arc(TM) B580') -and $log.Contains('muxing overhead')) { Write-Output 'recovered-completed'; exit 0 }
}
try {
    $locked=$mutex.WaitOne(0)
    if (-not $locked) { exit 75 }
    if (Get-Process -Name 'Plex Transcoder' -ErrorAction SilentlyContinue) { exit 75 }
    $filters=@()
    for ($i=0;$i -lt 2;$i++) {
        $duration=[double]$request.clips[$i].duration
        $filters+="[${i}:v]setpts=PTS-STARTPTS,scale=$($request.width):$($request.height):force_original_aspect_ratio=decrease,pad=$($request.width):$($request.height):(ow-iw)/2:(oh-ih)/2,setsar=1,fps=$($request.fps),format=nv12[v$i]"
        if ($request.clips[$i].has_audio) {
            $filters+="[${i}:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration=$duration,asetpts=PTS-STARTPTS[a$i]"
        } else {
            $filters+="anullsrc=r=48000:cl=stereo,atrim=duration=$duration,asetpts=PTS-STARTPTS[a$i]"
        }
    }
    $filters+='[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]'
    $arguments=@('-hide_banner','-nostdin','-y','-loglevel','verbose','-threads','2','-init_hw_device','d3d11va=dx:1','-init_hw_device','qsv=qs@dx','-i',(Join-Path $job 'clip-0.mp4'),'-i',(Join-Path $job 'clip-1.mp4'),'-filter_complex',($filters -join ';'),'-map','[v]','-map','[a]','-c:v','h264_qsv','-global_quality','20','-pix_fmt','nv12','-c:a','aac','-movflags','+faststart',(Join-Path $job 'result.mp4'))
    $quoted=$arguments | ForEach-Object {'"'+$_+'"'}
    [Diagnostics.Process]::GetCurrentProcess().PriorityClass='BelowNormal'
    $process=Start-Process (Join-Path $root 'bin\ffmpeg.exe') -ArgumentList $quoted -WindowStyle Hidden -PassThru -RedirectStandardError (Join-Path $job 'encode.log') -RedirectStandardOutput (Join-Path $job 'stdout.log')
    $null=$process.Handle
    while (-not $process.WaitForExit(1000)) {
        if (Get-Process -Name 'Plex Transcoder' -ErrorAction SilentlyContinue) {
            $process.Kill(); $process.WaitForExit(); exit 75
        }
    }
    if ($process.ExitCode -ne 0) { throw 'FFmpeg failed; inspect encode.log' }
    if (-not (Select-String -LiteralPath (Join-Path $job 'encode.log') -SimpleMatch -Pattern 'Intel(R) Arc(TM) B580' -Quiet)) { throw 'B580 not selected' }
    Write-Output 'completed'
} finally {
    if ($locked) {$mutex.ReleaseMutex()}
    $mutex.Dispose()
}
