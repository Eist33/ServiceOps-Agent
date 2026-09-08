param(
    [switch]$NoBrowser
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
        throw "$Step failed with exit code $ExitCode. 请先确认 Docker Desktop 已启动。"
    }
}

Push-Location $root
try {
    & docker info --format '{{.ServerVersion}}' | Out-Null
    Assert-Succeeded -Step 'Docker engine check' -ExitCode $LASTEXITCODE

    & docker compose up -d --wait
    Assert-Succeeded -Step 'Product startup' -ExitCode $LASTEXITCODE

    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:18080/health'
    if ($health.status -ne 'ok') {
        throw 'API health check failed.'
    }
    $web = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:13000/'
    if ($web.StatusCode -ne 200) {
        throw "Web health check failed with status $($web.StatusCode)."
    }

    Write-Host 'Harbor Support 已启动：http://127.0.0.1:13000/'
    if (-not $NoBrowser) {
        Start-Process 'http://127.0.0.1:13000/'
    }
}
finally {
    Pop-Location
}
