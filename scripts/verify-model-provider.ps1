param(
    [string]$ApiBaseUrl = 'http://127.0.0.1:18080',
    [switch]$ResetAfter
)

$ErrorActionPreference = 'Stop'
$headers = @{ 'X-Demo-Session' = 'demo-linmu-session' }

function Assert-Condition {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw $Message
    }
}

function Send-AgentMessage {
    param([string]$ConversationId, [string]$Content)
    $body = @{ content = $Content } | ConvertTo-Json -Compress
    $response = Invoke-WebRequest `
        -Method Post `
        -Uri "$ApiBaseUrl/api/conversations/$ConversationId/messages" `
        -Headers $headers `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([Text.Encoding]::UTF8.GetBytes($body))
    $responseText = if ($response.Content -is [byte[]]) {
        [Text.Encoding]::UTF8.GetString($response.Content)
    } else {
        [string]$response.Content
    }
    return @(
        $responseText -split "`n" |
            Where-Object { $_.Trim() } |
            ForEach-Object { $_ | ConvertFrom-Json }
    )
}

$runtimeJson = docker compose exec -T api python -c @'
import json
from serviceops.config import get_settings
s = get_settings()
print(json.dumps({
    "agent_mode": s.agent_mode,
    "provider": s.model_provider,
    "model": s.model_name,
    "key_configured": bool(s.model_api_key or s.deepseek_api_key or s.openai_api_key),
}))
'@
Assert-Condition ($LASTEXITCODE -eq 0) '无法读取 API 容器的模型运行配置'
$runtime = $runtimeJson | ConvertFrom-Json
Assert-Condition ($runtime.agent_mode -in @('model', 'openai')) 'API 当前不是模型模式'
Assert-Condition ([bool]$runtime.key_configured) 'API 容器尚未配置模型 API Key'

$conversation = Invoke-RestMethod `
    -Method Post `
    -Uri "$ApiBaseUrl/api/conversations" `
    -Headers $headers

$policyEvents = Send-AgentMessage `
    -ConversationId $conversation.id `
    -Content '收到商品后几天可以退货？'
$shippingEvents = Send-AgentMessage `
    -ConversationId $conversation.id `
    -Content '订单 ORD-20260828-1042 的物流到哪里了？'
$events = @($policyEvents) + @($shippingEvents)
$eventTypes = @($events | ForEach-Object { $_.type })
$toolNames = @(
    $events |
        Where-Object { $_.type -eq 'tool_completed' } |
        ForEach-Object { $_.payload.tool_name }
)

Assert-Condition (-not ($eventTypes -contains 'model_fallback')) '真实模型调用发生了降级'
Assert-Condition ($eventTypes -contains 'message_delta') '模型没有返回流式文本事件'
Assert-Condition ($eventTypes -contains 'response_completed') '模型响应没有正常完成'
Assert-Condition ($toolNames -contains 'search_knowledge_base') '模型没有完成政策检索工具调用'
Assert-Condition ($toolNames -contains 'get_order') '模型没有完成订单工具调用'
Assert-Condition ($toolNames -contains 'get_shipping_status') '模型没有完成物流工具调用'

if ($ResetAfter) {
    Invoke-RestMethod `
        -Method Post `
        -Uri "$ApiBaseUrl/api/demo/reset" `
        -Headers $headers | Out-Null
}

[ordered]@{
    passed = $true
    provider = $runtime.provider
    model = $runtime.model
    conversation_id = $conversation.id
    tool_names = $toolNames
    response_completed = $true
    reset_after = [bool]$ResetAfter
} | ConvertTo-Json -Depth 3
