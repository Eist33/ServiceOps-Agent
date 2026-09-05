@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "RESULT=0"

docker compose -f docker-compose.e2e.yml up -d --build --wait
if errorlevel 1 (
    set "RESULT=1"
    goto :cleanup
)

set "E2E_EXTERNAL_SERVER=true"
pushd demo
call node_modules\.bin\playwright.CMD test
set "RESULT=%ERRORLEVEL%"
popd

:cleanup
docker compose -f docker-compose.e2e.yml down -v
if errorlevel 1 set "RESULT=1"
exit /b %RESULT%
