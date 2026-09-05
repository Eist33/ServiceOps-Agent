@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "OPEN_BROWSER=1"
if /I "%~1"=="--no-browser" set "OPEN_BROWSER=0"

docker info --format "{{.ServerVersion}}" >nul 2>&1
if errorlevel 1 (
    echo Docker Desktop is not ready. Start Docker Desktop and try again.
    exit /b 1
)

docker compose up -d --wait
if errorlevel 1 exit /b 1

curl.exe -fsS http://127.0.0.1:8000/health >nul
if errorlevel 1 (
    echo API health check failed.
    exit /b 1
)

curl.exe -fsS http://127.0.0.1:3000/ >nul
if errorlevel 1 (
    echo Web health check failed.
    exit /b 1
)

echo Harbor Support is running at http://127.0.0.1:3000/
if "%OPEN_BROWSER%"=="1" start "" http://127.0.0.1:3000/
exit /b 0
