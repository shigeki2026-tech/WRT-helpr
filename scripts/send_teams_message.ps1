param(
    [Parameter(Mandatory = $true)]
    [string]$ChatId,

    [Parameter(Mandatory = $true)]
    [string]$MessageFile
)

$ErrorActionPreference = "Stop"

$script:TeamsDebugStartedAt = Get-Date

function Write-TeamsDebugLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Phase,

        [string]$Result = "",

        [string]$Note = ""
    )

    try {
        $debugLogPath = $env:WRT_TEAMS_DEBUG_LOG_PATH
        if ([string]::IsNullOrWhiteSpace($debugLogPath)) {
            return
        }

        $elapsedMs = [int][Math]::Max(0, ((Get-Date) - $script:TeamsDebugStartedAt).TotalMilliseconds)
        $parentDir = Split-Path -Parent $debugLogPath
        if (-not [string]::IsNullOrWhiteSpace($parentDir) -and -not (Test-Path -LiteralPath $parentDir)) {
            New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
        }

        $destinationKey = ""
        if ($null -ne $env:WRT_TEAMS_DEBUG_DESTINATION_KEY) {
            $destinationKey = $env:WRT_TEAMS_DEBUG_DESTINATION_KEY
        }
        $destinationLabel = ""
        if ($null -ne $env:WRT_TEAMS_DEBUG_DESTINATION_LABEL) {
            $destinationLabel = $env:WRT_TEAMS_DEBUG_DESTINATION_LABEL
        }
        $safeNote = ""
        if ($null -ne $Note) {
            $safeNote = $Note -replace "[\r\n]+", " "
            $safeNote = $safeNote.Substring(0, [Math]::Min($safeNote.Length, 120))
        }

        $row = [PSCustomObject]@{
            timestamp = (Get-Date).ToString("yyyy/MM/dd HH:mm:ss")
            destination_key = $destinationKey
            destination_label = $destinationLabel
            phase = $Phase
            elapsed_ms = $elapsedMs
            result = $Result
            note = $safeNote
        }

        if (Test-Path -LiteralPath $debugLogPath) {
            $row | Export-Csv -LiteralPath $debugLogPath -NoTypeInformation -Encoding UTF8 -Append
        }
        else {
            $row | Export-Csv -LiteralPath $debugLogPath -NoTypeInformation -Encoding UTF8
        }
    }
    catch {
        # Diagnostic logging must never affect Teams sending or SUCCESS/ERROR output.
    }
}

Write-TeamsDebugLog -Phase "ps_script_start" -Result "start"

try {
    if (-not (Test-Path -LiteralPath $MessageFile)) {
        throw "MessageFile not found: $MessageFile"
    }

    Write-TeamsDebugLog -Phase "module_import_start" -Result "start"
    Import-Module Microsoft.Graph.Authentication -ErrorAction Stop
    Import-Module Microsoft.Graph.Teams -ErrorAction Stop
    Write-TeamsDebugLog -Phase "module_import_end" -Result "success"

    Write-TeamsDebugLog -Phase "graph_context_check_start" -Result "start"
    $context = Get-MgContext -ErrorAction SilentlyContinue
    Write-TeamsDebugLog -Phase "graph_context_check_end" -Result "success"
    if (-not $context) {
        Write-TeamsDebugLog -Phase "graph_connect_start" -Result "start"
        Connect-MgGraph -Scopes "ChatMessage.Send"
        Write-TeamsDebugLog -Phase "graph_connect_end" -Result "success"
    }

    $messageBody = Get-Content -LiteralPath $MessageFile -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($messageBody)) {
        throw "Message body is empty"
    }

    $bodyParameter = @{
        body = @{
            contentType = "html"
            content = $messageBody
        }
    }

    Write-TeamsDebugLog -Phase "graph_send_start" -Result "start"
    $message = New-MgChatMessage -ChatId $ChatId -BodyParameter $bodyParameter
    Write-TeamsDebugLog -Phase "graph_send_end" -Result "success"
    Write-TeamsDebugLog -Phase "ps_script_end" -Result "success"
    Write-Output ("SUCCESS " + $message.Id)
    exit 0
}
catch {
    Write-TeamsDebugLog -Phase "ps_script_end" -Result "failure"
    Write-Output ("ERROR " + $_.Exception.Message)
    exit 1
}
