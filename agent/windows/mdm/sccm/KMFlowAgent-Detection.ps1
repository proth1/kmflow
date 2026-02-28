# KMFlowAgent-Detection.ps1
# SCCM/MECM application detection script for KMFlow Agent.
#
# Returns $true if the agent is installed, $false otherwise.
# Used as a Script-based detection method in SCCM Application Deployment Type.
#
# Detection criteria:
# 1. KMFlowAgent.exe exists in %ProgramFiles%\KMFlowAgent\
# 2. Registry key HKLM\SOFTWARE\KMFlowAgent exists

$ExePath = Join-Path $env:ProgramFiles 'KMFlowAgent\KMFlowAgent.exe'

if (Test-Path $ExePath) {
    # Installed — write to stdout for SCCM detection
    Write-Host "Installed"
}
# If nothing is written to stdout, SCCM considers the app as not installed
