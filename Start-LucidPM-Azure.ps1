<#
    Start-LucidPM-Azure.ps1  -  run LucidPM locally against Azure SQL.

    Counterpart to Start-LucidPM.ps1 (which uses local SQL Express). This one
    sets the H58 env vars for the Azure serverless DBs as PROCESS env vars in
    this shell only - nothing is written to .env, so your normal local dev loop
    (Start-LucidPM.ps1, ports 3000/8000) is unaffected.

    Used for Cycle 2.2 / Gate 2 validation. Ports 3002 / 8002.

    Prompts for the lucidpm_app SQL password (contained user created via
    db/azure_app_user.sql). The password is never stored.

    LUCIDPM_FERNET_KEY is read from .env (the new key from the H63 rotation).
    If Communications throws InvalidToken, the Azure EmailConfig/AIConfig rows
    are still under the OLD key - either re-save those secrets in Admin Settings
    while connected, or prepend the old key:  $env:LUCIDPM_FERNET_KEY = "<new>,<old>"
#>
$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$reflexExe   = Join-Path $projectRoot ".venv\Scripts\reflex.exe"
Set-Location $projectRoot

if (-not (Test-Path -LiteralPath $reflexExe)) {
    throw "Virtual environment not found. Expected: $reflexExe"
}

# --- Azure SQL connection (H58) ------------------------------------------------
$env:LUCIDPM_SQL_SERVER     = "lucidpm-sql-24899.database.windows.net"
$env:LUCIDPM_SQL_AUTH       = "sql"
$env:LUCIDPM_SQL_USER       = "lucidpm_app"
$env:LUCIDPM_PROD_DB        = "TenantCRM"
$env:LUCIDPM_TEST_DB        = "TenantCRM_Test"
$env:LUCIDPM_SQL_ENCRYPT    = "yes"
$env:LUCIDPM_SQL_TRUST_CERT = "no"      # Azure presents a valid public cert - validate it
$env:LUCIDPM_ENV            = "cloud"   # inert marker today; correct value

# --- Cold-resume retry tuning (H60) - bumped for Cycle 2.2 measurement --------
# Committed defaults are 2 / 3 (about 9s budget), which did NOT bridge a real resume.
# 8 / 4  ->  waits 4+8+12+16+20+24+28+32 = 144s across 9 attempts.
$env:LUCIDPM_SQL_CONNECT_RETRIES = "8"
$env:LUCIDPM_SQL_RETRY_BACKOFF   = "4"
$env:LUCIDPM_SQL_LOGIN_TIMEOUT   = "30" # fast-fail per attempt; raise to 60 if attempts hang

# --- password (never stored) -------------------------------------------------
$sec = Read-Host "lucidpm_app SQL password" -AsSecureString
$env:LUCIDPM_SQL_PASSWORD = [System.Net.NetworkCredential]::new('', $sec).Password
if ([string]::IsNullOrWhiteSpace($env:LUCIDPM_SQL_PASSWORD)) {
    throw "No password entered."
}

Write-Host ""
Write-Host "LucidPM -> Azure SQL ($($env:LUCIDPM_SQL_SERVER))" -ForegroundColor Cyan
Write-Host "Retry budget: $($env:LUCIDPM_SQL_CONNECT_RETRIES) retries x backoff $($env:LUCIDPM_SQL_RETRY_BACKOFF) (about 144s)"
Write-Host "Open http://localhost:3002/  -- watch this console for [state.get_conn] retry lines."
Write-Host "Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

& $reflexExe run --frontend-port 3002 --backend-port 8002
