$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$ruff = Join-Path $root '.venv\Scripts\ruff.exe'
$pytest = Join-Path $root '.venv\Scripts\pytest.exe'
$pnpm = 'C:\Users\12494\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd'

function Assert-Succeeded {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Step,
        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    if ($ExitCode -ne 0) {
        throw "$Step failed with exit code $ExitCode."
    }
}

& $ruff check (Join-Path $root 'apps\api')
Assert-Succeeded -Step 'Backend lint' -ExitCode $LASTEXITCODE
& $pytest (Join-Path $root 'apps\api\tests')
Assert-Succeeded -Step 'Backend tests' -ExitCode $LASTEXITCODE
& $pytest (Join-Path $root 'tests')
Assert-Succeeded -Step 'Delivery document and container tests' -ExitCode $LASTEXITCODE

$previousCI = $env:CI
$env:CI = 'true'
Push-Location (Join-Path $root 'demo')
try {
    & $pnpm run lint
    Assert-Succeeded -Step 'Frontend lint' -ExitCode $LASTEXITCODE
    & $pnpm run build
    Assert-Succeeded -Step 'Frontend build' -ExitCode $LASTEXITCODE
    & $pnpm run test:e2e
    Assert-Succeeded -Step 'Frontend end-to-end tests' -ExitCode $LASTEXITCODE
}
finally {
    Pop-Location
    if ($null -eq $previousCI) {
        Remove-Item Env:CI -ErrorAction SilentlyContinue
    }
    else {
        $env:CI = $previousCI
    }
}
