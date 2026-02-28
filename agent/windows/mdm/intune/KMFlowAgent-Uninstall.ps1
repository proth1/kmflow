# KMFlowAgent-Uninstall.ps1
# Intune Win32 app uninstallation script for KMFlow Agent.
#
# Finds the installed product by name and removes it silently.

$ErrorActionPreference = 'Stop'

# Find installed product via registry (avoid Win32_Product which is extremely slow)
$UninstallPaths = @(
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$Product = Get-ItemProperty $UninstallPaths -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -eq 'KMFlow Task Mining Agent' } |
    Select-Object -First 1

if ($Product -and $Product.UninstallString) {
    # Extract product code from uninstall string (e.g., MsiExec.exe /X{GUID})
    if ($Product.UninstallString -match '\{[A-F0-9-]+\}') {
        $ProductCode = $Matches[0]
        $process = Start-Process -FilePath 'msiexec.exe' -ArgumentList @(
            '/x', $ProductCode
            '/qn'
            '/norestart'
            '/l*v', "$env:TEMP\KMFlowAgent-Uninstall.log"
        ) -Wait -PassThru
        exit $process.ExitCode
    }
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
