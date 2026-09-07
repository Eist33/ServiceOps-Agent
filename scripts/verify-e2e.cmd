@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "RESULT=0"

docker info --format "{{.ServerVersion}}" >nul 2>&1
if errorlevel 1 (
    echo [ServiceOps] ERROR / 错误: Docker Engine is unavailable. Start Docker Desktop and retry.
    exit /b 1
)

docker compose -f docker-compose.e2e.yml config --quiet
if errorlevel 1 exit /b 1

docker compose -f docker-compose.e2e.yml up -d --build --wait postgres api web
if errorlevel 1 (
    set "RESULT=1"
    goto :cleanup
)

docker compose -f docker-compose.e2e.yml run --rm --no-deps e2e pnpm test:e2e
set "RESULT=%ERRORLEVEL%"

:cleanup
docker compose -f docker-compose.e2e.yml down -v
if errorlevel 1 set "RESULT=1"
exit /b %RESULT%
