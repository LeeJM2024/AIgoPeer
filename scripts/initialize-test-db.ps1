[CmdletBinding()]
param(
    [string]$PsqlPath = "C:\Program Files\PostgreSQL\16\bin\psql.exe"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$localConfigPath = Join-Path $repositoryRoot ".env.test.local"

if (-not (Test-Path -LiteralPath $PsqlPath -PathType Leaf)) {
    throw "psql.exe was not found at $PsqlPath. Install PostgreSQL 16 Command Line Tools first."
}

$adminSecret = Read-Host "PostgreSQL postgres administrator password" -AsSecureString
$runnerSecret = Read-Host "New algopeer_test_runner password" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($adminSecret)
$adminPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($runnerSecret)
$runnerPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

$previousPgPassword = $env:PGPASSWORD
try {
    $env:PGPASSWORD = $adminPassword
    $escapedRunnerPassword = $runnerPassword.Replace("'", "''")
    $roleSql = @'
DO $bootstrap$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'algopeer_test_runner') THEN
        ALTER ROLE algopeer_test_runner LOGIN PASSWORD '__RUNNER_PASSWORD__';
    ELSE
        CREATE ROLE algopeer_test_runner LOGIN PASSWORD '__RUNNER_PASSWORD__';
    END IF;
END
$bootstrap$;
'@.Replace("__RUNNER_PASSWORD__", $escapedRunnerPassword)

    $roleSql | & $PsqlPath -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -p 55432 -U postgres -d postgres
    if ($LASTEXITCODE -ne 0) {
        throw "Creating the isolated test role failed. Check the administrator password."
    }

    $databaseExists = & $PsqlPath -X -h 127.0.0.1 -p 55432 -U postgres -d postgres -tAc "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'algopeer_test')"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not check whether algopeer_test exists."
    }
    if ($databaseExists -ne "t") {
        & $PsqlPath -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -p 55432 -U postgres -d postgres -c "CREATE DATABASE algopeer_test OWNER algopeer_test_runner"
        if ($LASTEXITCODE -ne 0) {
            throw "Creating the isolated test database failed."
        }
    }

    & $PsqlPath -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -p 55432 -U postgres -d postgres -c "ALTER DATABASE algopeer_test OWNER TO algopeer_test_runner"
    if ($LASTEXITCODE -ne 0) {
        throw "Assigning the isolated test database owner failed."
    }

    $encodedPassword = [System.Uri]::EscapeDataString($runnerPassword)
    $connectionUrl = "postgresql+psycopg://algopeer_test_runner:$encodedPassword@127.0.0.1:55432/algopeer_test"
    Set-Content -LiteralPath $localConfigPath -Value "TEST_DATABASE_URL=$connectionUrl" -Encoding utf8 -NoNewline
    Write-Host "Created algopeer_test and wrote its local connection setting to .env.test.local."
}
finally {
    if ($null -eq $previousPgPassword) {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
    else {
        $env:PGPASSWORD = $previousPgPassword
    }
    $adminPassword = $null
    $runnerPassword = $null
}
