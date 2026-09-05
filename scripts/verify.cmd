@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist ".venv\Scripts\ruff.exe" (
    echo Missing backend test environment: .venv
    exit /b 1
)
if not exist "demo\node_modules\.bin\oxlint.CMD" (
    echo Missing frontend dependencies: demo\node_modules
    exit /b 1
)

.venv\Scripts\ruff.exe check apps\api
if errorlevel 1 exit /b 1

.venv\Scripts\pytest.exe apps\api\tests
if errorlevel 1 exit /b 1

.venv\Scripts\pytest.exe tests
if errorlevel 1 exit /b 1

pushd demo
set "CI=true"
call node_modules\.bin\oxlint.CMD .
if errorlevel 1 (
    popd
    exit /b 1
)
call node_modules\.bin\vinext.CMD build
if errorlevel 1 (
    popd
    exit /b 1
)
popd

call scripts\verify-e2e.cmd
if errorlevel 1 exit /b 1

echo Full automated verification passed.
exit /b 0
