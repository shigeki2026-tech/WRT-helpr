param(
    [Parameter(Mandatory = $true)]
    [string]$ChatId,

    [Parameter(Mandatory = $true)]
    [string]$MessageFile
)

$ErrorActionPreference = "Stop"

try {
    if (-not (Test-Path -LiteralPath $MessageFile)) {
        throw "MessageFile not found: $MessageFile"
    }

    Import-Module Microsoft.Graph.Authentication -ErrorAction Stop
    Import-Module Microsoft.Graph.Teams -ErrorAction Stop

    $context = Get-MgContext -ErrorAction SilentlyContinue
    if (-not $context) {
        Connect-MgGraph -Scopes "ChatMessage.Send"
    }

    $messageBody = Get-Content -LiteralPath $MessageFile -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($messageBody)) {
        throw "Message body is empty"
    }

    $bodyParameter = @{
        body = @{
            contentType = "text"
            content = $messageBody
        }
    }

    $message = New-MgChatMessage -ChatId $ChatId -BodyParameter $bodyParameter
    Write-Output ("SUCCESS " + $message.Id)
    exit 0
}
catch {
    Write-Output ("ERROR " + $_.Exception.Message)
    exit 1
}
