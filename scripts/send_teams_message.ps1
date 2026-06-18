param(
    [Parameter(Mandatory = $true)]
    [string]$ChatId,

    [Parameter(Mandatory = $true)]
    [string]$MessageFile
)

$ErrorActionPreference = "Stop"

$script:TeamsDebugStartedAt = Get-Date
$script:TeamsPerfStartedAt = Get-Date
$script:TeamsPerfCurrentPhase = ""
$script:TeamsPerfCurrentStartedAt = $null

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

function Write-TeamsPerfLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Phase,

        [string]$Result = "",

        [string]$ErrorMessage = "",

        [Nullable[datetime]]$PhaseStartedAt = $null
    )

    try {
        $perfLogPath = $env:WRT_TEAMS_PERF_LOG_PATH
        if ([string]::IsNullOrWhiteSpace($perfLogPath)) {
            return
        }

        $now = Get-Date
        $elapsedMs = 0
        if ($null -ne $PhaseStartedAt) {
            $elapsedMs = [int][Math]::Max(0, ($now - $PhaseStartedAt).TotalMilliseconds)
        }
        $cumulativeMs = [int][Math]::Max(0, ($now - $script:TeamsPerfStartedAt).TotalMilliseconds)
        $parentDir = Split-Path -Parent $perfLogPath
        if (-not [string]::IsNullOrWhiteSpace($parentDir) -and -not (Test-Path -LiteralPath $parentDir)) {
            New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
        }

        $safeError = ""
        if ($null -ne $ErrorMessage) {
            $safeError = $ErrorMessage -replace "[\r\n]+", " "
            $safeError = $safeError.Substring(0, [Math]::Min($safeError.Length, 200))
        }

        $row = [PSCustomObject]@{
            timestamp = $now.ToString("yyyy/MM/dd HH:mm:ss")
            phase = $Phase
            elapsed_ms = $elapsedMs
            cumulative_ms = $cumulativeMs
            result = $Result
            error_message = $safeError
        }

        if (Test-Path -LiteralPath $perfLogPath) {
            $row | Export-Csv -LiteralPath $perfLogPath -NoTypeInformation -Encoding UTF8 -Append
        }
        else {
            $row | Export-Csv -LiteralPath $perfLogPath -NoTypeInformation -Encoding UTF8
        }
    }
    catch {
        # Performance logging must never affect Teams sending or SUCCESS/ERROR output.
    }
}

function Start-TeamsPerfPhase {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Phase
    )

    $script:TeamsPerfCurrentPhase = $Phase
    $script:TeamsPerfCurrentStartedAt = Get-Date
    Write-TeamsPerfLog -Phase $Phase -Result "start"
}

function End-TeamsPerfPhase {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Phase,

        [string]$Result = "success"
    )

    $phaseStartedAt = $script:TeamsPerfCurrentStartedAt
    if ($script:TeamsPerfCurrentPhase -ne $Phase) {
        $phaseStartedAt = $null
    }
    Write-TeamsPerfLog -Phase $Phase -Result $Result -PhaseStartedAt $phaseStartedAt
    $script:TeamsPerfCurrentPhase = ""
    $script:TeamsPerfCurrentStartedAt = $null
}

Write-TeamsDebugLog -Phase "ps_script_start" -Result "start"
Write-TeamsPerfLog -Phase "ps_script_start" -Result "start"

try {
    if (-not (Test-Path -LiteralPath $MessageFile)) {
        throw "MessageFile not found: $MessageFile"
    }

    Start-TeamsPerfPhase -Phase "config_read"
    End-TeamsPerfPhase -Phase "config_read" -Result "skipped"

    Write-TeamsDebugLog -Phase "module_import_start" -Result "start"
    $moduleImportTotalStartedAt = Get-Date
    Write-TeamsPerfLog -Phase "module_import_total" -Result "start"
    Start-TeamsPerfPhase -Phase "module_import_auth"
    Import-Module Microsoft.Graph.Authentication -ErrorAction Stop
    End-TeamsPerfPhase -Phase "module_import_auth"
    Start-TeamsPerfPhase -Phase "module_import_teams"
    Import-Module Microsoft.Graph.Teams -ErrorAction Stop
    End-TeamsPerfPhase -Phase "module_import_teams"
    Write-TeamsPerfLog -Phase "module_import_total" -Result "success" -PhaseStartedAt $moduleImportTotalStartedAt
    Write-TeamsDebugLog -Phase "module_import_end" -Result "success"

    Write-TeamsDebugLog -Phase "graph_context_check_start" -Result "start"
    Start-TeamsPerfPhase -Phase "graph_context_check"
    $context = Get-MgContext -ErrorAction SilentlyContinue
    End-TeamsPerfPhase -Phase "graph_context_check"
    Write-TeamsDebugLog -Phase "graph_context_check_end" -Result "success"
    if (-not $context) {
        Write-TeamsDebugLog -Phase "graph_connect_start" -Result "start"
        Start-TeamsPerfPhase -Phase "graph_connect"
        Connect-MgGraph -Scopes "ChatMessage.Send"
        End-TeamsPerfPhase -Phase "graph_connect"
        Write-TeamsDebugLog -Phase "graph_connect_end" -Result "success"
    }

    Start-TeamsPerfPhase -Phase "message_file_read"
    $messageBody = Get-Content -LiteralPath $MessageFile -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($messageBody)) {
        throw "Message body is empty"
    }
    End-TeamsPerfPhase -Phase "message_file_read"

    $bodyParameter = @{
        body = @{
            contentType = "html"
            content = $messageBody
        }
    }

    Write-TeamsDebugLog -Phase "graph_send_start" -Result "start"
    Start-TeamsPerfPhase -Phase "graph_send"
    $message = New-MgChatMessage -ChatId $ChatId -BodyParameter $bodyParameter
    End-TeamsPerfPhase -Phase "graph_send"
    Write-TeamsDebugLog -Phase "graph_send_end" -Result "success"
    Write-TeamsDebugLog -Phase "ps_script_end" -Result "success"
    Write-TeamsPerfLog -Phase "ps_script_end" -Result "success" -PhaseStartedAt $script:TeamsPerfStartedAt
    Write-Output ("SUCCESS " + $message.Id)
    exit 0
}
catch {
    if (-not [string]::IsNullOrWhiteSpace($script:TeamsPerfCurrentPhase)) {
        Write-TeamsPerfLog -Phase $script:TeamsPerfCurrentPhase -Result "failure" -ErrorMessage $_.Exception.Message -PhaseStartedAt $script:TeamsPerfCurrentStartedAt
    }
    Write-TeamsDebugLog -Phase "ps_script_end" -Result "failure"
    Write-TeamsPerfLog -Phase "ps_script_end" -Result "failure" -ErrorMessage $_.Exception.Message -PhaseStartedAt $script:TeamsPerfStartedAt
    Write-Output ("ERROR " + $_.Exception.Message)
    exit 1
}
