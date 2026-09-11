<#
.SYNOPSIS
  Point the LucidPM Azure SQL firewall at wherever this laptop currently is.

.DESCRIPTION
  Detects the machine's current public IP and updates a single firewall rule on
  the Azure SQL server to match it. Run this whenever SSMS (or the app pointed at
  Azure SQL) can't connect after moving between home and office.

  Requires the Azure CLI, logged in to the Lucido-Apps subscription (az login).

.EXAMPLE
  .\Update-AzureSqlFirewall.ps1
  Updates the "Mark-Laptop" rule to the current public IP.
#>
[CmdletBinding()]
param(
    [string]$RuleName      = "Mark-Laptop",
    [string]$ResourceGroup = "Lucido-Apps-RG",
    [string]$ServerName    = "lucidpm-sql-24899"
)

$ErrorActionPreference = "Stop"

# --- current public IP -------------------------------------------------------
$ip = $null
foreach ($svc in @("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com")) {
    try {
        $candidate = (Invoke-RestMethod -Uri $svc -TimeoutSec 5).ToString().Trim()
        if ($candidate -match '^\d{1,3}(\.\d{1,3}){3}$') { $ip = $candidate; break }
    }
    catch { }
}
if (-not $ip) { throw "Could not determine the current public IP address." }
Write-Host "Current public IP: $ip"

# --- Azure CLI present and logged in ---------------------------------------
try { $null = az account show 2>$null | ConvertFrom-Json }
catch { throw "Azure CLI not available or not logged in. Run 'az login' first." }
if ($LASTEXITCODE -ne 0) { throw "Azure CLI not logged in. Run 'az login' first." }

# --- existing rules --------------------------------------------------------
$rules = az sql server firewall-rule list --resource-group $ResourceGroup --server $ServerName | ConvertFrom-Json

$covered = $rules | Where-Object { $_.startIpAddress -eq $ip -and $_.endIpAddress -eq $ip }
if ($covered) {
    Write-Host "Already whitelisted by rule '$($covered.name)'. Nothing to do."
    return
}

$existing = $rules | Where-Object { $_.name -eq $RuleName }
if ($existing) {
    Write-Host "Updating rule '$RuleName': $($existing.startIpAddress) -> $ip"
    az sql server firewall-rule update `
        --resource-group $ResourceGroup --server $ServerName --name $RuleName `
        --start-ip-address $ip --end-ip-address $ip --output table
}
else {
    Write-Host "Creating rule '$RuleName' for $ip"
    az sql server firewall-rule create `
        --resource-group $ResourceGroup --server $ServerName --name $RuleName `
        --start-ip-address $ip --end-ip-address $ip --output table
}

Write-Host ""
Write-Host "Done. SSMS should connect within a minute."
