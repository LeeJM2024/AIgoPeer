[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path (Split-Path -Parent $PSScriptRoot) ".env.test.local")
)

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Missing $ConfigPath. Copy .env.test.local.example to .env.test.local and set TEST_DATABASE_URL."
}

$testDatabaseUrl = $null
foreach ($line in Get-Content -LiteralPath $ConfigPath) {
    $trimmed = $line.Trim()
    if ($trimmed -match '^(#|$)') {
        continue
    }
    if ($trimmed -match '^TEST_DATABASE_URL=(.+)$') {
        $testDatabaseUrl = $Matches[1].Trim()
        break
    }
}

if ([string]::IsNullOrWhiteSpace($testDatabaseUrl)) {
    throw "TEST_DATABASE_URL is not set in $ConfigPath."
}

try {
    $uri = [System.Uri]$testDatabaseUrl
}
catch {
    throw "TEST_DATABASE_URL is not a valid PostgreSQL connection URL."
}

if ($uri.Host -notin @("127.0.0.1", "localhost") -or $uri.Port -ne 55432 -or $uri.AbsolutePath.TrimStart("/") -ne "algopeer_test") {
    throw "For safety, TEST_DATABASE_URL must target the local algopeer_test database on port 55432."
}

if (-not (Test-NetConnection -ComputerName $uri.Host -Port $uri.Port -InformationLevel Quiet)) {
    throw "PostgreSQL is not reachable at $($uri.Host):$($uri.Port). Run .\\scripts\\start-test-db.ps1 first."
}

$env:TEST_DATABASE_URL = $testDatabaseUrl
Write-Host "TEST_DATABASE_URL is set for this PowerShell session (local algopeer_test on port 55432)."
