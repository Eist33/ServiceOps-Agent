[CmdletBinding()]
param(
    [string]$ServerHost = "101.35.149.171",
    [int]$ApiPort = 18080,
    [int]$WebPort = 13000,
    [string]$ReleaseTag,
    [switch]$NoPullPostgres
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$composePath = Join-Path $repoRoot "docker-compose.portainer.yml"
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

    foreach ($repository in @("serviceops-api", "serviceops-web")) {
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

    $packagePattern = "portainer-package-$([regex]::Escape($DatePrefix))-r*"
    foreach ($directory in @(Get-ChildItem -Path $repoRoot -Directory -Filter $packagePattern -ErrorAction SilentlyContinue)) {
        $match = [regex]::Match($directory.Name, $tagPattern.Replace("^$DatePrefix", "^portainer-package-$DatePrefix"))
        if ($match.Success) {
            $numbers.Add([int]$match.Groups[1].Value)
        }
    }

    return $numbers
}

if (-not (Test-Path -LiteralPath $composePath)) {
    throw "Portainer Compose file not found: $composePath"
}

$datePrefix = Get-Date -Format "yyyyMMdd"
if ([string]::IsNullOrWhiteSpace($ReleaseTag)) {
    $existingNumbers = @(Get-ExistingReleaseNumbers -DatePrefix $datePrefix)
    $nextNumber = if ($existingNumbers.Count -eq 0) { 1 } else { (($existingNumbers | Measure-Object -Maximum).Maximum + 1) }
    $ReleaseTag = "$datePrefix-r$nextNumber"
} elseif ($ReleaseTag -notmatch '^\d{8}-r\d+$') {
    throw "ReleaseTag must use the incrementing format YYYYMMDD-rN, for example 20260908-r1"
}

$apiImage = "serviceops-api:$ReleaseTag"
$webImage = "serviceops-web:$ReleaseTag"
$packageDirectory = Join-Path $repoRoot "portainer-package-$ReleaseTag"
if (Test-Path -LiteralPath $packageDirectory) {
    throw "Package directory already exists: $packageDirectory"
}

Write-Host "Release tag: $ReleaseTag"
Write-Host "Building $apiImage"
Invoke-Docker @(
    "build",
    "--tag", $apiImage,
    "--file", (Join-Path $repoRoot "apps/api/Dockerfile"),
    (Join-Path $repoRoot "apps/api")
)

$publicApiUrl = "http://$ServerHost`:$ApiPort"
Write-Host "Building $webImage with NEXT_PUBLIC_API_URL=$publicApiUrl"
Invoke-Docker @(
    "build",
    "--tag", $webImage,
    "--build-arg", "NEXT_PUBLIC_API_URL=$publicApiUrl",
    "--file", (Join-Path $repoRoot "demo/Dockerfile"),
    (Join-Path $repoRoot "demo")
)

if (-not $NoPullPostgres) {
    Write-Host "Ensuring $postgresImage is available locally"
    Invoke-Docker @("pull", $postgresImage)
} else {
    Write-Host "Skipping PostgreSQL image pull because -NoPullPostgres was specified"
}
Invoke-Docker @("image", "inspect", $postgresImage) -Quiet

$composeText = Get-Content -LiteralPath $composePath -Raw
$apiImagePattern = '(?m)^(\s*image:\s*serviceops-api:)[^\s]+'
$webImagePattern = '(?m)^(\s*image:\s*serviceops-web:)[^\s]+'
$apiPortPattern = '(?m)^([ \t]*-[ \t]*)"\d+:8000"[ \t]*$'
$webPortPattern = '(?m)^([ \t]*-[ \t]*)"\d+:3000"[ \t]*$'
if (-not [regex]::IsMatch($composeText, $apiImagePattern)) {
    throw "Portainer Compose does not contain a serviceops-api image entry"
}
if (-not [regex]::IsMatch($composeText, $webImagePattern)) {
    throw "Portainer Compose does not contain a serviceops-web image entry"
}
if (-not [regex]::IsMatch($composeText, $apiPortPattern)) {
    throw "Portainer Compose does not contain an API port mapping"
}
if (-not [regex]::IsMatch($composeText, $webPortPattern)) {
    throw "Portainer Compose does not contain a Web port mapping"
}
$composeText = [regex]::Replace($composeText, $apiImagePattern, ('${1}' + $ReleaseTag))
$composeText = [regex]::Replace($composeText, $webImagePattern, ('${1}' + $ReleaseTag))
$composeText = [regex]::Replace($composeText, $apiPortPattern, ('${1}"' + $ApiPort + ':8000"'))
$composeText = [regex]::Replace($composeText, $webPortPattern, ('${1}"' + $WebPort + ':3000"'))
Set-Content -LiteralPath $composePath -Value $composeText -NoNewline -Encoding utf8

$apiComposeImage = "serviceops-api:$ReleaseTag"
$webComposeImage = "serviceops-web:$ReleaseTag"
$apiPortMapping = '"' + $ApiPort + ':8000"'
$webPortMapping = '"' + $WebPort + ':3000"'
if (-not $composeText.Contains($apiComposeImage) -or -not $composeText.Contains($webComposeImage)) {
    throw "Generated Compose does not reference both images with tag $ReleaseTag"
}
if (-not $composeText.Contains($apiPortMapping) -or -not $composeText.Contains($webPortMapping)) {
    throw "Generated Compose does not use the requested API/Web published ports"
}

$apiImageId = (& docker image inspect $apiImage --format "{{.Id}}")
$webImageId = (& docker image inspect $webImage --format "{{.Id}}")
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($apiImageId) -or [string]::IsNullOrWhiteSpace($webImageId)) {
    throw "Built image inspection failed"
}

$previousDemoPassword = [Environment]::GetEnvironmentVariable("DEMO_LOGIN_PASSWORD", "Process")
$env:DEMO_LOGIN_PASSWORD = "validation-only"
try {
    Write-Host "Validating generated Portainer Compose"
    Invoke-Docker @("compose", "-f", $composePath, "config") -Quiet
} finally {
    if ($null -eq $previousDemoPassword) {
        Remove-Item Env:DEMO_LOGIN_PASSWORD -ErrorAction SilentlyContinue
    } else {
        $env:DEMO_LOGIN_PASSWORD = $previousDemoPassword
    }
}

New-Item -ItemType Directory -Path $packageDirectory -Force | Out-Null
$bundlePath = Join-Path $packageDirectory "serviceops-images-$ReleaseTag.tar"
$packageComposePath = Join-Path $packageDirectory "docker-compose.portainer.yml"
$manifestPath = Join-Path $packageDirectory "MANIFEST.txt"

Write-Host "Saving API, Web, and PostgreSQL images to $bundlePath"
Invoke-Docker @(
    "save",
    "--output", $bundlePath,
    $apiImage,
    $webImage,
    $postgresImage
)
Copy-Item -LiteralPath $composePath -Destination $packageComposePath -Force

$bundleHash = (Get-FileHash -LiteralPath $bundlePath -Algorithm SHA256).Hash
$manifest = @(
    "release_tag=$ReleaseTag",
    "api_image=$apiImage",
    "web_image=$webImage",
    "postgres_image=$postgresImage",
    "api_image_id=$apiImageId",
    "web_image_id=$webImageId",
    "public_api_url=$publicApiUrl",
    "web_url=http://$ServerHost`:$WebPort",
    "bundle_sha256=$bundleHash",
    "compose_file=docker-compose.portainer.yml",
    "compose_api_image=$apiComposeImage",
    "compose_web_image=$webComposeImage",
    "compose_api_port=$apiPortMapping",
    "compose_web_port=$webPortMapping"
)
Set-Content -LiteralPath $manifestPath -Value $manifest -Encoding utf8

Write-Host ""
Write-Host "Package completed: $packageDirectory"
Write-Host "Upload this image bundle to Portainer: $bundlePath"
Write-Host "Use this Compose file in Portainer Web editor: $packageComposePath"
Write-Host "Bundle SHA256: $bundleHash"
