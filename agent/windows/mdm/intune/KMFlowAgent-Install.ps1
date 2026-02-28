# KMFlowAgent-Install.ps1
# Intune Win32 app installation script for KMFlow Agent.
#
# Usage by Intune:
#   powershell.exe -ExecutionPolicy Bypass -File KMFlowAgent-Install.ps1
#
# Optional parameters via Intune command line:
#   -EngagementId "ENG-001" -BackendUrl "https://api.kmflow.example.com"

[CmdletBinding()]
param(
    [string]$EngagementId,
    [string]$BackendUrl
)

$ErrorActionPreference = 'Stop'

# Find the MSI in the same directory as this script
$MsiPath = Join-Path $PSScriptRoot 'KMFlowAgent.msi'

if (-not (Test-Path $MsiPath)) {
    Write-Error "MSI not found: $MsiPath"
    exit 1
}

# Build msiexec arguments
$MsiArgs = @(
    '/i', "`"$MsiPath`""
    '/qn'           # Silent install
    '/norestart'
    '/l*v', "`"$env:TEMP\KMFlowAgent-Install.log`""
)

if ($EngagementId) {
    $MsiArgs += "ENGAGEMENTID=`"$EngagementId`""
}

if ($BackendUrl) {
    $MsiArgs += "BACKENDURL=`"$BackendUrl`""
}

# Run the installer
$process = Start-Process -FilePath 'msiexec.exe' -ArgumentList $MsiArgs -Wait -PassThru
exit $process.ExitCode
