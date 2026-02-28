# KMFlowAgent-Detection-Registry.ps1
# Alternative SCCM detection script using registry check.
#
# Checks for the DeviceId registry value which is created on first run.
# This is a more reliable detection than file-based for environments
# where the install path might vary.

$RegPath = 'HKLM:\SOFTWARE\KMFlowAgent'

if (Test-Path $RegPath) {
    $deviceId = (Get-ItemProperty -Path $RegPath -Name 'DeviceId' -ErrorAction SilentlyContinue).DeviceId
    if ($deviceId) {
        Write-Host "Installed (DeviceId: $deviceId)"
    }
}
