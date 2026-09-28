# Optional local launcher. Docker Desktop must be running.
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host '已创建 .env，请在演示前修改 POSTGRES_PASSWORD 和 JWT_SECRET。'
}
docker compose up --build
