param(
    [switch]$ColdStart,
    [switch]$VerifyModelProvider,
    [switch]$EvaluateFullModel
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

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

Push-Location $root
try {
    & docker compose config --quiet
    Assert-Succeeded -Step 'Docker Compose configuration' -ExitCode $LASTEXITCODE

    if ($ColdStart) {
        & docker compose stop
        Assert-Succeeded -Step 'Docker cold stop' -ExitCode $LASTEXITCODE
    }

    & docker compose up -d --build --wait
    Assert-Succeeded -Step 'Docker build and startup' -ExitCode $LASTEXITCODE

    $migration = (& docker compose exec -T api alembic current 2>&1 | Out-String)
    Assert-Succeeded -Step 'Database migration check' -ExitCode $LASTEXITCODE
    if ($migration -notmatch '\(head\)') {
        throw "Database is not at the latest migration: $migration"
    }

    & docker compose exec -T api python -m serviceops.cli evaluate-knowledge
    Assert-Succeeded -Step 'Knowledge retrieval evaluation gate' -ExitCode $LASTEXITCODE
    & docker compose exec -T api python -m serviceops.cli evaluate-agent
    Assert-Succeeded -Step 'Agent orchestration evaluation gate' -ExitCode $LASTEXITCODE

    foreach ($url in @(
        'http://127.0.0.1:3000/',
        'http://127.0.0.1:3000/agent',
        'http://127.0.0.1:3000/knowledge',
        'http://127.0.0.1:3000/operations'
    )) {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $url
        if ($response.StatusCode -ne 200) {
            throw "$url returned status $($response.StatusCode)."
        }
    }

    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health'
    if ($health.status -ne 'ok') {
        throw 'API health check failed.'
    }

    & (Join-Path $PSScriptRoot 'verify.ps1')
    Assert-Succeeded -Step 'Full automated verification' -ExitCode $LASTEXITCODE

    if ($VerifyModelProvider) {
        & (Join-Path $PSScriptRoot 'verify-model-provider.ps1') -ResetAfter
        Assert-Succeeded -Step 'Real model provider verification' -ExitCode $LASTEXITCODE
    }
    if ($EvaluateFullModel) {
        if (-not $VerifyModelProvider) {
            throw '-EvaluateFullModel requires -VerifyModelProvider.'
        }
        & docker compose exec -T api python -m serviceops.cli evaluate-agent --runtime model
        Assert-Succeeded -Step 'Full real-model orchestration evaluation' -ExitCode $LASTEXITCODE
    }

    $reset = Invoke-RestMethod `
        -Method Post `
        -Uri 'http://127.0.0.1:8000/api/demo/reset' `
        -Headers @{ 'X-Demo-Session' = 'demo-linmu-session' }
    if ($reset.status -ne 'reset') {
        throw 'Demo reset verification failed.'
    }

    Write-Host 'Release verification passed.'
}
finally {
    Pop-Location
}
