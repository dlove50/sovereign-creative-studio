$ErrorActionPreference = "Stop"

$appRoot = "C:\Users\David\Documents\Codex\sovereign-creative-studio"
$containerName = "baidu-unlimited-ocr"
$ocrHealth = "http://127.0.0.1:8010/v1/models"
$studioUrl = "http://127.0.0.1:3000/ocr-studio"
$dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"

function Test-Url([string]$Url, [int]$TimeoutSeconds = 3) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSeconds
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Show-LauncherError([string]$Message) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        $Message,
        "Unlimited OCR could not start",
        [System.Windows.MessageBoxButton]::OK,
        [System.Windows.MessageBoxImage]::Error
    ) | Out-Null
}

try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker is not installed or is not available in your PATH."
    }

    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        if (-not (Test-Path -LiteralPath $dockerDesktop)) {
            throw "Docker Desktop is not installed in its expected location."
        }
        Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
        $dockerReady = $false
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 2
            docker info *> $null
            if ($LASTEXITCODE -eq 0) { $dockerReady = $true; break }
        }
        if (-not $dockerReady) { throw "Docker Desktop did not become ready within two minutes." }
    }

    docker start $containerName *> $null
    if ($LASTEXITCODE -ne 0) { throw "The Baidu Unlimited-OCR container could not be started." }

    if (-not (Test-Url $studioUrl)) {
        $frontendScript = Join-Path $appRoot "start-frontend.ps1"
        Start-Process -FilePath "powershell.exe" `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $frontendScript) `
            -WorkingDirectory $appRoot `
            -WindowStyle Hidden
    }

    $ocrReady = $false
    $studioReady = $false
    for ($i = 0; $i -lt 90; $i++) {
        if (-not $ocrReady) { $ocrReady = Test-Url $ocrHealth }
        if (-not $studioReady) { $studioReady = Test-Url $studioUrl }
        if ($ocrReady -and $studioReady) { break }
        Start-Sleep -Seconds 2
    }

    if (-not $ocrReady) { throw "The Baidu model is still not ready. Check that your NVIDIA GPU is available to Docker." }
    if (-not $studioReady) { throw "The OCR interface did not become ready on port 3000." }

    Start-Process $studioUrl
} catch {
    Show-LauncherError $_.Exception.Message
    exit 1
}
