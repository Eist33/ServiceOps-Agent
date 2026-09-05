@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "COLD_START=0"
set "VERIFY_MODEL=0"
set "EVALUATE_FULL_MODEL=0"

:parse
if "%~1"=="" goto :parsed
if /I "%~1"=="--cold-start" set "COLD_START=1"& shift& goto :parse
if /I "%~1"=="--verify-model" set "VERIFY_MODEL=1"& shift& goto :parse
if /I "%~1"=="--evaluate-full-model" set "EVALUATE_FULL_MODEL=1"& shift& goto :parse
echo Unknown option: %~1
exit /b 2

:parsed
if "%EVALUATE_FULL_MODEL%"=="1" if not "%VERIFY_MODEL%"=="1" (
    echo --evaluate-full-model requires --verify-model.
    exit /b 2
)

docker compose config --quiet
if errorlevel 1 exit /b 1

if "%COLD_START%"=="1" (
    docker compose stop
    if errorlevel 1 exit /b 1
)

docker compose up -d --build --wait
if errorlevel 1 exit /b 1

docker compose exec -T api alembic current | findstr /c:"(head)" >nul
if errorlevel 1 (
    echo Database migration is not at head.
    exit /b 1
)

docker compose exec -T api python -m serviceops.cli evaluate-knowledge
if errorlevel 1 exit /b 1

docker compose exec -T api python -m serviceops.cli evaluate-agent
if errorlevel 1 exit /b 1

for %%U in (
    http://127.0.0.1:3000/
    http://127.0.0.1:3000/staff/agent
    http://127.0.0.1:3000/staff/knowledge
    http://127.0.0.1:3000/staff/operations
    http://127.0.0.1:8000/health
) do (
    curl.exe -fsS %%U >nul
    if errorlevel 1 (
        echo HTTP check failed: %%U
        exit /b 1
    )
)

call scripts\verify.cmd
if errorlevel 1 exit /b 1

if "%VERIFY_MODEL%"=="1" (
    .venv\Scripts\python.exe scripts\verify_model_provider.py --reset-after
    if errorlevel 1 exit /b 1
)

if "%EVALUATE_FULL_MODEL%"=="1" (
    docker compose exec -T api python -m serviceops.cli evaluate-agent --runtime model
    if errorlevel 1 exit /b 1
)

curl.exe -fsS -X POST -H X-Demo-Session:demo-linmu-session http://127.0.0.1:8000/api/demo/reset >nul
if errorlevel 1 exit /b 1

echo Release verification passed.
exit /b 0
