@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."

if not exist "docker-compose.yml" (
    echo [ServiceOps] ERROR / 错误: docker-compose.yml was not found.
    exit /b 1
)

docker info --format "{{.ServerVersion}}" >nul 2>&1
if errorlevel 1 (
    echo [ServiceOps] ERROR / 错误: Docker Engine is unavailable. Start Docker Desktop and retry.
    exit /b 1
)

docker compose -f docker-compose.yml -f docker-compose.stage3.yml config --quiet >nul 2>&1
if errorlevel 1 (
    echo [ServiceOps] ERROR / 错误: Docker Compose configuration is invalid.
    exit /b 1
)

echo [ServiceOps] Running backend tests inside Docker...
docker compose -f docker-compose.yml -f docker-compose.stage3.yml run --rm api-test
if errorlevel 1 goto :failure

echo [ServiceOps] Running repository contract tests inside Docker...
docker compose -f docker-compose.yml -f docker-compose.stage3.yml run --rm -v "%CD%:/workspace:ro" api-test python -m pytest /workspace/tests
if errorlevel 1 goto :failure

echo [ServiceOps] Validating frontend lint and build inside Docker...
docker compose -f docker-compose.e2e.yml config --quiet >nul 2>&1
if errorlevel 1 goto :failure
docker compose -f docker-compose.e2e.yml run --rm --no-deps e2e pnpm lint
if errorlevel 1 goto :failure
docker compose -f docker-compose.e2e.yml run --rm --no-deps e2e pnpm run build
if errorlevel 1 goto :failure

call scripts\verify-e2e.cmd
if errorlevel 1 goto :failure

echo [ServiceOps] Full Docker verification passed / Docker 全量验收通过。
exit /b 0

:failure
echo [ServiceOps] ERROR / 错误: Docker verification failed.
echo [ServiceOps] NEXT / 下一步: docker compose ps
echo [ServiceOps] NEXT / 下一步: docker compose logs --tail=100 postgres api web
exit /b 1
