$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$ruff = Join-Path $root '.venv\Scripts\ruff.exe'
$pytest = Join-Path $root '.venv\Scripts\pytest.exe'
$frontendBin = Join-Path $root 'demo\node_modules\.bin'
$oxlint = Join-Path $frontendBin 'oxlint.CMD'
$vinext = Join-Path $frontendBin 'vinext.CMD'
$playwright = Join-Path $frontendBin 'playwright.CMD'

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
    & $oxlint .
    Assert-Succeeded -Step 'Frontend lint' -ExitCode $LASTEXITCODE
    & $vinext build
    Assert-Succeeded -Step 'Frontend build' -ExitCode $LASTEXITCODE
    & $playwright test
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
