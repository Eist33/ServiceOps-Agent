param(
    [switch]$ColdStart,
    [switch]$EvaluateFullModel
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $root '.env'
$examplePath = Join-Path $root '.env.example'

function Set-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Lines,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $updated = $false
    $result = foreach ($line in $Lines) {
        if ($line -match "^$([regex]::Escape($Name))=") {
            $updated = $true
            "$Name=$Value"
        }
        else {
            $line
        }
    }
    if (-not $updated) {
        $result += "$Name=$Value"
    }
    return @($result)
}

Push-Location $root
$secretPointer = [IntPtr]::Zero
$apiKey = $null
try {
    & docker info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Desktop 尚未运行，请先打开 Docker Desktop 并等待引擎启动。'
    }

    $secureKey = Read-Host '请输入 DeepSeek API Key（输入内容不会显示）' -AsSecureString
    $secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer)
    if ($apiKey -notmatch '^[A-Za-z0-9._-]{16,}$') {
        throw 'API Key 格式不正确；只允许字母、数字、点、下划线和连字符。'
    }

    $lines = if (Test-Path -LiteralPath $envPath) {
        @(Get-Content -LiteralPath $envPath)
    }
    else {
        @(Get-Content -LiteralPath $examplePath)
    }
    $settings = [ordered]@{
        AGENT_MODE = 'model'
        MODEL_PROVIDER = 'deepseek'
        MODEL_API_STYLE = 'responses'
        MODEL_BASE_URL = 'https://api.deepseek.com'
        MODEL_NAME = 'deepseek-v4-flash'
        MODEL_API_KEY = $apiKey
    }
    foreach ($entry in $settings.GetEnumerator()) {
        $lines = Set-DotEnvValue -Lines $lines -Name $entry.Key -Value $entry.Value
    }
    Set-Content -LiteralPath $envPath -Value $lines -Encoding utf8
    $apiKey = $null

    $releaseScript = Join-Path $PSScriptRoot 'verify-release.ps1'
    if ($ColdStart -and $EvaluateFullModel) {
        & $releaseScript -ColdStart -VerifyModelProvider -EvaluateFullModel
    }
    elseif ($ColdStart) {
        & $releaseScript -ColdStart -VerifyModelProvider
    }
    elseif ($EvaluateFullModel) {
        & $releaseScript -VerifyModelProvider -EvaluateFullModel
    }
    else {
        & $releaseScript -VerifyModelProvider
    }
    if ($LASTEXITCODE -ne 0) {
        throw '本地 DeepSeek 部署验收未通过。'
    }

    Write-Host 'DeepSeek 模型模式已部署并通过验收：http://127.0.0.1:3000/'
}
finally {
    $apiKey = $null
    $lines = $null
    if ($null -ne $settings) {
        $settings['MODEL_API_KEY'] = $null
    }
    $settings = $null
    if ($secretPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer)
    }
    Pop-Location
}
