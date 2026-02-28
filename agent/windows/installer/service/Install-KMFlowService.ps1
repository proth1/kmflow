# Install-KMFlowService.ps1
# Installs the KMFlow Agent as a Windows Service for enterprise mode.
# Must be run as Administrator.
#
# Usage:
#   .\Install-KMFlowService.ps1 [-Uninstall]

[CmdletBinding()]
param(
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$ServiceName = 'KMFlowAgent'
$DisplayName = 'KMFlow Task Mining Agent'
$Description = 'KMFlow desktop activity capture agent for process intelligence.'
$ExePath = Join-Path $env:ProgramFiles 'KMFlowAgent\KMFlowAgent.exe'

# Verify elevation
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error 'This script must be run as Administrator.'
    exit 1
}

if ($Uninstall) {
    Write-Host "Stopping service '$ServiceName'..."
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue

    Write-Host "Removing service '$ServiceName'..."
    sc.exe delete $ServiceName | Out-Null

    Write-Host "Service '$ServiceName' removed."
    exit 0
}

# Check if already installed
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Warning "Service '$ServiceName' already exists (Status: $($existing.Status)). Use -Uninstall first."
    exit 1
}

# Verify executable exists
if (-not (Test-Path $ExePath)) {
    Write-Error "Executable not found: $ExePath. Install KMFlowAgent first."
    exit 1
}

Write-Host "Creating service '$ServiceName'..."
$binPath = "`"$ExePath`" --service"
sc.exe create $ServiceName binPath= $binPath start= delayed-auto obj= "NT AUTHORITY\LocalService" DisplayName= $DisplayName | Out-Null

Write-Host "Setting description..."
sc.exe description $ServiceName $Description | Out-Null

Write-Host "Configuring failure recovery..."
sc.exe failure $ServiceName reset= 86400 actions= restart/60000/restart/120000/restart/300000 | Out-Null

Write-Host "Starting service..."
Start-Service -Name $ServiceName

$svc = Get-Service -Name $ServiceName
Write-Host "Service '$ServiceName' installed and running (Status: $($svc.Status))."
