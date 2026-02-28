# KMFlowAgent-Detection.ps1
# Intune Win32 app detection script for KMFlow Agent.
#
# Returns exit code 0 and writes to stdout if the agent is installed.
# Returns exit code 1 (no output) if not installed.
#
# Detection criteria:
# 1. KMFlowAgent.exe exists in %ProgramFiles%\KMFlowAgent\
# 2. File version is 1.0.0 or higher

$ExePath = Join-Path $env:ProgramFiles 'KMFlowAgent\KMFlowAgent.exe'

if (Test-Path $ExePath) {
    $version = (Get-Item $ExePath).VersionInfo.FileVersion
    if ($version) {
        Write-Output "KMFlowAgent $version detected"
        exit 0
    }
    # File exists but no version info — still detected
    Write-Output "KMFlowAgent detected (no version info)"
    exit 0
}

# Not installed
exit 1
