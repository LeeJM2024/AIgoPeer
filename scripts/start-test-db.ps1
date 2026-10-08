[CmdletBinding()]
param(
    [string]$ServiceName = "postgresql-x64-16"
)

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($null -eq $service) {
    throw "Windows service '$ServiceName' was not found. Install PostgreSQL 16 first."
}

if ($service.Status -ne "Running") {
    try {
        Start-Service -Name $ServiceName -ErrorAction Stop
    }
    catch {
        throw "Could not start '$ServiceName'. Run this script from an elevated PowerShell session or start the service from Services."
    }
}

$service.WaitForStatus("Running", [TimeSpan]::FromSeconds(20))
Write-Host "PostgreSQL test service '$ServiceName' is running."
