param([string]$Root = 'C:\Users\Plex\SovereignWorker')
$ErrorActionPreference = 'Stop'
[Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'BelowNormal'
$results = @()
$statePath = Join-Path $Root 'proxy-audio-audit.json'
$jobs = Get-Content (Join-Path $Root 'proxy-audit-input.json') -Raw | ConvertFrom-Json
foreach ($entry in $jobs.PSObject.Properties) {
    $job = Join-Path $Root ('jobs\' + $entry.Value.job_id)
    $pair = @{}
    foreach ($kind in @('source','result')) {
        $path = Join-Path $job ($kind + '.mp4')
        $raw = & (Join-Path $Root 'bin\ffprobe.exe') -v error -show_format -show_streams -of json $path
        if ($LASTEXITCODE -ne 0) { throw "Probe failed: $path" }
        $probe = $raw | ConvertFrom-Json
        $audio = @($probe.streams | Where-Object codec_type -eq 'audio')
        $log = Join-Path $job ($kind + '-audio-audit.log')
        $decodePassed = $true
        if ($audio.Count -gt 0) {
            # Single-threaded CPU audio decoding; no GPU or video decode, originals untouched.
            & (Join-Path $Root 'bin\ffmpeg.exe') -nostdin -v error -xerror -threads 1 -i $path -map '0:a' -vn -threads 1 -f null - 2> $log
            $decodePassed = $LASTEXITCODE -eq 0
        }
        $pair[$kind] = @{
            duration = [double]$probe.format.duration
            bytes = (Get-Item -LiteralPath $path).Length
            audio = @($audio | Select-Object codec_name,channels,sample_rate,duration,start_time)
            audioDecodePassed = $decodePassed
        }
    }
    $issues = @()
    if ($pair.source.audio.Count -ne $pair.result.audio.Count) { $issues += 'Audio stream count changed' }
    if ([Math]::Abs($pair.source.duration - $pair.result.duration) -gt 0.15) { $issues += 'Container duration drift exceeds 150ms' }
    for ($i=0; $i -lt [Math]::Min($pair.source.audio.Count,$pair.result.audio.Count); $i++) {
        if ($pair.source.audio[$i].channels -ne $pair.result.audio[$i].channels) { $issues += "Audio channels changed on stream $i" }
        if ([Math]::Abs([double]$pair.source.audio[$i].duration - [double]$pair.result.audio[$i].duration) -gt 0.15) { $issues += "Audio duration drift exceeds 150ms on stream $i" }
    }
    if (-not $pair.source.audioDecodePassed -or -not $pair.result.audioDecodePassed) { $issues += 'Audio decoding failed' }
    $results += @{ importId=$entry.Name; jobId=$entry.Value.job_id; source=$pair.source; proxy=$pair.result; issues=$issues; passed=($issues.Count -eq 0) }
    @{ machine=$env:COMPUTERNAME; status='running'; completed=$results.Count; total=$jobs.PSObject.Properties.Count; results=$results; updatedUtc=[DateTime]::UtcNow.ToString('o') } | ConvertTo-Json -Depth 12 | Set-Content $statePath -Encoding UTF8
    Write-Output ('Audited ' + $entry.Name + ': ' + ($issues.Count -eq 0))
}
@{ machine=$env:COMPUTERNAME; status='completed'; completed=$results.Count; results=$results; updatedUtc=[DateTime]::UtcNow.ToString('o'); scope='Audio decode, stream count, channel count and duration preservation; does not certify perceptual audio quality.' } | ConvertTo-Json -Depth 12 | Set-Content $statePath -Encoding UTF8
