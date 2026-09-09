[CmdletBinding()]
param(
    [string]$ReleaseTag,
    [switch]$NoPullPostgres
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceComposePath = Join-Path $repoRoot "docker-compose.production.yml"
$postgresImage = "pgvector/pgvector:pg16"

function Invoke-Docker {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$Quiet
    )

    if ($Quiet) {
        & docker @Arguments | Out-Null
    } else {
        & docker @Arguments
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed with exit code ${LASTEXITCODE}: docker $($Arguments -join ' ')"
    }
}

function Get-ExistingReleaseNumbers {
    param([string]$DatePrefix)

    $numbers = [System.Collections.Generic.List[int]]::new()
    $tagPattern = "^$([regex]::Escape($DatePrefix))-r(\d+)$"

    foreach ($repository in @("serviceops-api", "serviceops-web", "serviceops-gateway")) {
        $tags = @(& docker image ls $repository --format "{{.Tag}}")
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to list local Docker images for $repository"
        }
        foreach ($tag in $tags) {
            $match = [regex]::Match([string]$tag, $tagPattern)
            if ($match.Success) {
                $numbers.Add([int]$match.Groups[1].Value)
            }
        }
    }

    $packagePattern = "serviceops-production-package-$([regex]::Escape($DatePrefix))-r*"
    foreach ($directory in @(Get-ChildItem -Path $repoRoot -Directory -Filter $packagePattern -ErrorAction SilentlyContinue)) {
        $match = [regex]::Match($directory.Name, "^serviceops-production-package-$([regex]::Escape($DatePrefix))-r(\d+)$")
        if ($match.Success) {
            $numbers.Add([int]$match.Groups[1].Value)
        }
    }

    return $numbers
}

if (-not (Test-Path -LiteralPath $sourceComposePath)) {
    throw "Production Compose file not found: $sourceComposePath"
}

$datePrefix = Get-Date -Format "yyyyMMdd"
if ([string]::IsNullOrWhiteSpace($ReleaseTag)) {
    $existingNumbers = @(Get-ExistingReleaseNumbers -DatePrefix $datePrefix)
    $nextNumber = if ($existingNumbers.Count -eq 0) { 1 } else { (($existingNumbers | Measure-Object -Maximum).Maximum + 1) }
    $ReleaseTag = "$datePrefix-r$nextNumber"
} elseif ($ReleaseTag -notmatch '^\d{8}-r\d+$') {
    throw "ReleaseTag must use the incrementing format YYYYMMDD-rN, for example 20260909-r1"
}

$apiImage = "serviceops-api:$ReleaseTag"
$webImage = "serviceops-web:$ReleaseTag"
$gatewayImage = "serviceops-gateway:$ReleaseTag"
$packageDirectory = Join-Path $repoRoot "serviceops-production-package-$ReleaseTag"
if (Test-Path -LiteralPath $packageDirectory) {
    throw "Package directory already exists: $packageDirectory"
}

Write-Host "Production release tag: $ReleaseTag"
Write-Host "Building $apiImage"
Invoke-Docker @(
    "build",
    "--tag", $apiImage,
    "--file", (Join-Path $repoRoot "apps/api/Dockerfile"),
    (Join-Path $repoRoot "apps/api")
)

Write-Host "Building $webImage with relative API URL and external authentication mode"
Invoke-Docker @(
    "build",
    "--tag", $webImage,
    "--build-arg", "NEXT_PUBLIC_API_URL=",
    "--build-arg", "NEXT_PUBLIC_AUTH_MODE=external",
    "--file", (Join-Path $repoRoot "demo/Dockerfile"),
    (Join-Path $repoRoot "demo")
)

Write-Host "Building $gatewayImage"
Invoke-Docker @(
    "build",
    "--tag", $gatewayImage,
    "--file", (Join-Path $repoRoot "deploy/gateway/Dockerfile"),
    (Join-Path $repoRoot "deploy")
)

if (-not $NoPullPostgres) {
    Write-Host "Ensuring $postgresImage is available locally"
    Invoke-Docker @("pull", $postgresImage)
} else {
    Write-Host "Skipping PostgreSQL image pull because -NoPullPostgres was specified"
}
Invoke-Docker @("image", "inspect", $postgresImage) -Quiet

$composeText = Get-Content -LiteralPath $sourceComposePath -Raw
$composeText = $composeText.Replace("serviceops-api:production", $apiImage)
$composeText = $composeText.Replace("serviceops-web:production", $webImage)
$composeText = $composeText.Replace("serviceops-gateway:production", $gatewayImage)
if ($composeText.Contains("serviceops-api:production") -or $composeText.Contains("serviceops-web:production") -or $composeText.Contains("serviceops-gateway:production")) {
    throw "Generated production Compose still contains an untagged production image"
}

$previousValues = @{}
$validationValues = @{
    POSTGRES_DB = "serviceops"
    POSTGRES_USER = "serviceops_app"
    POSTGRES_PASSWORD = "validation-only-random-password"
    DATABASE_URL = "postgresql+psycopg://serviceops_app:validation-only-random-password@postgres:5432/serviceops"
    PUBLIC_ORIGIN = "https://support.example.invalid"
    TLS_CERT_PATH = "/tmp/serviceops-fullchain.pem"
    TLS_KEY_PATH = "/tmp/serviceops-privkey.pem"
}
foreach ($name in $validationValues.Keys) {
    $previousValues[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    Set-Item -Path "Env:$name" -Value $validationValues[$name]
}

$packageComposePath = Join-Path $packageDirectory "docker-compose.production.yml"
$manifestPath = Join-Path $packageDirectory "MANIFEST.txt"
$bundlePath = Join-Path $packageDirectory "serviceops-production-images-$ReleaseTag.tar"

try {
    New-Item -ItemType Directory -Path $packageDirectory -Force | Out-Null
    Set-Content -LiteralPath $packageComposePath -Value $composeText -NoNewline -Encoding utf8

    Write-Host "Validating generated production Compose"
    Invoke-Docker @("compose", "-f", $packageComposePath, "config") -Quiet

    Write-Host "Saving API, Web, gateway, and PostgreSQL images to $bundlePath"
    Invoke-Docker @(
        "save",
        "--output", $bundlePath,
        $apiImage,
        $webImage,
        $gatewayImage,
        $postgresImage
    )
} finally {
    foreach ($name in $validationValues.Keys) {
        if ($null -eq $previousValues[$name]) {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        } else {
            Set-Item -Path "Env:$name" -Value $previousValues[$name]
        }
    }
}

$apiImageId = (& docker image inspect $apiImage --format "{{.Id}}")
$webImageId = (& docker image inspect $webImage --format "{{.Id}}")
$gatewayImageId = (& docker image inspect $gatewayImage --format "{{.Id}}")
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($apiImageId) -or [string]::IsNullOrWhiteSpace($webImageId) -or [string]::IsNullOrWhiteSpace($gatewayImageId)) {
    throw "Built image inspection failed"
}

$bundleHash = (Get-FileHash -LiteralPath $bundlePath -Algorithm SHA256).Hash
$manifest = @(
    "release_tag=$ReleaseTag",
    "mode=production",
    "api_image=$apiImage",
    "web_image=$webImage",
    "gateway_image=$gatewayImage",
    "postgres_image=$postgresImage",
    "api_image_id=$apiImageId",
    "web_image_id=$webImageId",
    "gateway_image_id=$gatewayImageId",
    "frontend_api_url=relative:/api",
    "frontend_auth_mode=external",
    "public_ports=80,443",
    "bundle_sha256=$bundleHash",
    "compose_file=docker-compose.production.yml",
    "compose_api_image=$apiImage",
    "compose_web_image=$webImage",
    "compose_gateway_image=$gatewayImage"
)
Set-Content -LiteralPath $manifestPath -Value $manifest -Encoding utf8

Write-Host ""
Write-Host "Production package completed: $packageDirectory"
Write-Host "Upload this image bundle to Portainer: $bundlePath"
Write-Host "Use this Compose file in Portainer Web editor: $packageComposePath"
Write-Host "Bundle SHA256: $bundleHash"
