# KMFlowAgent-Uninstall.ps1
# Intune Win32 app uninstallation script for KMFlow Agent.
#
# Finds the installed product by name and removes it silently.

$ErrorActionPreference = 'Stop'

# Find installed product GUID
$Product = Get-WmiObject -Class Win32_Product | Where-Object { $_.Name -eq 'KMFlow Task Mining Agent' }

if ($Product) {
    $ProductCode = $Product.IdentifyingNumber
    $process = Start-Process -FilePath 'msiexec.exe' -ArgumentList @(
        '/x', $ProductCode
        '/qn'
        '/norestart'
        '/l*v', "$env:TEMP\KMFlowAgent-Uninstall.log"
    ) -Wait -PassThru
    exit $process.ExitCode
}

# Also try direct exe removal
$ExePath = Join-Path $env:ProgramFiles 'KMFlowAgent\KMFlowAgent.exe'
if (Test-Path $ExePath) {
    # Stop the service/process first
    Stop-Process -Name 'KMFlowAgent' -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2

    # Remove the installation directory
    Remove-Item -Path (Split-Path $ExePath) -Recurse -Force
    exit 0
}

# Not installed
exit 0
