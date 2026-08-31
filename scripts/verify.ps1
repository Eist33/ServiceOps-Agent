$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$ruff = Join-Path $root '.venv\Scripts\ruff.exe'
$pytest = Join-Path $root '.venv\Scripts\pytest.exe'
$pnpm = 'C:\Users\12494\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd'

& $ruff check (Join-Path $root 'apps\api')
& $pytest (Join-Path $root 'apps\api\tests')
Push-Location (Join-Path $root 'demo')
try {
    & $pnpm run lint
    & $pnpm run build
    & $pnpm run test:e2e
}
finally {
    Pop-Location
}
