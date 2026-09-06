@echo off
setlocal EnableExtensions

for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"
cd /d "%PROJECT_DIR%"
if errorlevel 1 (
    echo [ServiceOps] ERROR / 错误: Cannot enter the project directory.
    exit /b 1
)

docker info --format "{{.ServerVersion}}" >nul 2>&1
if errorlevel 1 (
    echo [ServiceOps] ERROR / 错误: Docker Engine is unavailable. Start Docker Desktop and retry.
    exit /b 1
)

docker compose stop
if errorlevel 1 (
    echo [ServiceOps] ERROR / 错误: Could not stop the ServiceOps containers.
    echo [ServiceOps] NEXT / 下一步: docker compose ps
    echo [ServiceOps] NEXT / 下一步: docker compose logs --tail=100 postgres api web
    exit /b 1
)

echo [ServiceOps] STOPPED / 已停止主 Compose 服务。
echo [ServiceOps] The serviceops-postgres volume was preserved / 数据卷已保留。
exit /b 0
