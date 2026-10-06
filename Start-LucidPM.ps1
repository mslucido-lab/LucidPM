$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$reflexExe = Join-Path $projectRoot ".venv\Scripts\reflex.exe"
$frontendPort = 3000
$backendPort = 8000
$appUrl = "http://localhost:$frontendPort/"

Set-Location $projectRoot

if (-not (Test-Path -LiteralPath $reflexExe)) {
    throw "The project virtual environment was not found. Expected: $reflexExe"
}

function Test-LocalPort {
    param([int]$Port)

    return $null -ne (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Test-HttpEndpoint {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

$frontendRunning = Test-LocalPort -Port $frontendPort
$backendRunning = Test-LocalPort -Port $backendPort

if ($frontendRunning -and $backendRunning) {
    $frontendHealthy = Test-HttpEndpoint -Url $appUrl
    $backendHealthy = Test-HttpEndpoint -Url "http://localhost:$backendPort/ping"
    if ($frontendHealthy -and $backendHealthy) {
        Write-Host "LucidPM is already running at $appUrl"
        Start-Process $appUrl
        exit 0
    }

    throw "Ports $frontendPort and $backendPort are occupied by an unresponsive LucidPM instance. Close its old command window or end the stale processes, then run this launcher again."
}

if ($frontendRunning -or $backendRunning) {
    $busyPorts = @()
    if ($frontendRunning) { $busyPorts += $frontendPort }
    if ($backendRunning) { $busyPorts += $backendPort }
    throw "Cannot start LucidPM because port(s) $($busyPorts -join ', ') are already in use."
}

Write-Host "Starting LucidPM..."
Write-Host "The browser will open automatically when the app is ready."
Write-Host "Keep this window open. Press Ctrl+C to stop the app."
Write-Host ""

$browserJob = Start-Job -ScriptBlock {
    param($FrontendUrl, $BackendUrl)

    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        try {
            $frontendResponse = Invoke-WebRequest -UseBasicParsing -Uri $FrontendUrl -TimeoutSec 2
            $backendResponse = Invoke-WebRequest -UseBasicParsing -Uri $BackendUrl -TimeoutSec 2
            if (
                $frontendResponse.StatusCode -ge 200 -and $frontendResponse.StatusCode -lt 500 -and
                $backendResponse.StatusCode -ge 200 -and $backendResponse.StatusCode -lt 500
            ) {
                Start-Process $FrontendUrl
                return
            }
        }
        catch {
            # The frontend is still compiling; try again shortly.
        }

        Start-Sleep -Seconds 1
    }
} -ArgumentList $appUrl, "http://localhost:$backendPort/ping"

try {
    & $reflexExe run --frontend-port $frontendPort --backend-port $backendPort
}
finally {
    Stop-Job -Job $browserJob -ErrorAction SilentlyContinue
    Remove-Job -Job $browserJob -Force -ErrorAction SilentlyContinue
}
