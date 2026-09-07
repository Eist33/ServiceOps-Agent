@echo off
setlocal EnableExtensions EnableDelayedExpansion

for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"
cd /d "%PROJECT_DIR%"
if errorlevel 1 goto :project_error

if not exist "%PROJECT_DIR%\docker-compose.yml" goto :compose_file_error

set "OPEN_BROWSER=1"
if /I "%~1"=="--no-browser" set "OPEN_BROWSER=0"

docker info --format "{{.ServerVersion}}" >nul 2>&1
if errorlevel 1 goto :docker_error

docker compose config --quiet >nul 2>&1
if errorlevel 1 goto :compose_config_error

echo Harbor Support is starting PostgreSQL, API, and web containers...
docker compose up -d --build --wait
if errorlevel 1 goto :startup_error

docker compose ps
if errorlevel 1 goto :ps_error

set "SERVICE_STATE_FAILED=0"
for %%S in (postgres api web) do (
    docker compose ps --status running --services | findstr /x /c:"%%S" >nul
    if errorlevel 1 set "SERVICE_STATE_FAILED=1"
)
if "%SERVICE_STATE_FAILED%"=="1" goto :service_state_error

set "SERVICE_HEALTH_FAILED=0"
for %%S in (postgres api web) do (
    docker compose ps --format "{{.Service}} {{.Health}}" | findstr /r /x /c:"%%S healthy" >nul
    if errorlevel 1 set "SERVICE_HEALTH_FAILED=1"
)
if "%SERVICE_HEALTH_FAILED%"=="1" goto :service_health_error

echo Harbor Support is running at http://127.0.0.1:3000/
if "%OPEN_BROWSER%"=="1" start "" http://127.0.0.1:3000/
exit /b 0

:project_error
echo [ServiceOps] ERROR / 错误: Cannot enter the project directory.
goto :failure_hint

:compose_file_error
echo [ServiceOps] ERROR / 错误: docker-compose.yml was not found.
goto :failure_hint

:docker_error
echo [ServiceOps] ERROR / 错误: Docker Engine is unavailable. Start Docker Desktop and retry.
goto :failure_hint

:compose_config_error
echo [ServiceOps] ERROR / 错误: Docker Compose configuration is invalid.
goto :failure_hint

:startup_error
echo [ServiceOps] ERROR / 错误: Container build or startup failed.
goto :failure_hint

:ps_error
echo [ServiceOps] ERROR / 错误: Could not read Docker Compose service state.
goto :failure_hint

:service_state_error
echo [ServiceOps] ERROR / 错误: A required service is not running.
goto :failure_hint

:service_health_error
echo [ServiceOps] ERROR / 错误: A required service is not healthy.
goto :failure_hint

:failure_hint
echo [ServiceOps] NEXT / 下一步: run these Docker commands from the project directory:
echo   docker compose ps
echo   docker compose logs --tail=100 postgres api web
exit /b 1
