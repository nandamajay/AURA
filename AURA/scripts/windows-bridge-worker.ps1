param(
    [string]$BridgeRoot = "\\hu-nandam-hyd\workspace\AURA_V1\bridge",
    [int]$PollSeconds = 1,
    [string]$AdbPath = "C:\adb_tool\platform-tools\adb.exe",
    [string]$AdbSerial = "",
    [switch]$UseAdbShell = $true,
    [switch]$EnableAssetPush,
    [switch]$LiveTrace,
    [switch]$Once
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RequestsDir = Join-Path $BridgeRoot "requests"
$ResponsesDir = Join-Path $BridgeRoot "responses"
$DeliveredDir = Join-Path $BridgeRoot "delivered"
$LogsDir = Join-Path $BridgeRoot "logs"

New-Item -ItemType Directory -Path $RequestsDir -Force | Out-Null
New-Item -ItemType Directory -Path $ResponsesDir -Force | Out-Null
New-Item -ItemType Directory -Path $DeliveredDir -Force | Out-Null
New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null

$WorkerLog = Join-Path $LogsDir "windows_worker.log"
$ProcessedLog = Join-Path $LogsDir "windows_processed_request_ids.txt"
if (-not (Test-Path $ProcessedLog)) {
    New-Item -ItemType File -Path $ProcessedLog -Force | Out-Null
}

$AllowedCommands = @(
    "echo AURA_BRIDGE_PING",
    "getprop ro.build.fingerprint",
    "logcat -d -t 200",
    "dumpsys media.audio_flinger",
    "cat /proc/version",
    "cat /proc/asound/cards",
    "cat /proc/asound/pcm",
    "cat /proc/interrupts",
    "cat /proc/cpuinfo",
    "uname -a",
    "dmesg",
    "dmesg | tail -200",
    "lsmod",
    "tinymix",
    "amixer",
    "ls /sys/kernel/debug",
    "ls /sys/kernel/debug/asoc",
    "cat /sys/kernel/debug/asoc/*/dapm",
    "systemctl --version"
)

function Write-WorkerLog {
    param([string]$Message)
    Add-Content -Path $WorkerLog -Value ("{0} {1}" -f (Get-Date -Format o), $Message) -Encoding UTF8
}

function Get-Sha256Hex {
    param([string]$Text)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha.ComputeHash($bytes)
        return ([BitConverter]::ToString($hashBytes) -replace "-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Decode-Base64UrlUtf8 {
    param([string]$InputText)
    if ([string]::IsNullOrWhiteSpace($InputText)) {
        throw "base64url_input_empty"
    }
    $normalized = $InputText.Replace('-', '+').Replace('_', '/')
    switch ($normalized.Length % 4) {
        2 { $normalized += "==" }
        3 { $normalized += "=" }
        1 { throw "base64url_length_invalid" }
        default { }
    }
    $bytes = [Convert]::FromBase64String($normalized)
    return [System.Text.Encoding]::UTF8.GetString($bytes)
}

function Normalize-CanonicalCommand {
    param([string]$Command)
    $trimmed = ($Command | ForEach-Object { $_.Trim() })
    return (($trimmed -split "\s+" | Where-Object { $_ -ne "" }) -join " ")
}

function Test-ForbiddenCommand {
    param([string]$Command)
    $lowered = $Command.ToLowerInvariant()

    $forbiddenTokens = @(';', '&&', '||', '`', '$(', '>', '<')
    foreach ($token in $forbiddenTokens) {
        if ($Command.Contains($token)) {
            return "forbidden_token:$token"
        }
    }

    $forbiddenPrefixes = @(
        "adb ",
        "adb.exe",
        "shell ",
        "sh -c",
        "bash -c",
        "cmd /c",
        "powershell"
    )
    foreach ($prefix in $forbiddenPrefixes) {
        if ($lowered.StartsWith($prefix)) {
            return "forbidden_prefix:$prefix"
        }
    }

    if (" $lowered ".Contains(" adb ")) {
        return "nested_adb_reference"
    }

    return ""
}

function Build-RequestDigestInput {
    param(
        [string]$RequestId,
        [int]$RequestSequence,
        [int]$TimeoutSeconds,
        [string]$ExecutionMode,
        [string]$Transport,
        [string[]]$Commands
    )
    $parts = @(
        $RequestId,
        [string]$RequestSequence,
        [string]$TimeoutSeconds,
        $ExecutionMode,
        $Transport
    ) + $Commands
    return ($parts -join "`n")
}

function Build-ResponseDigestInput {
    param(
        [string]$RequestId,
        [int]$RequestSequence,
        [string]$RequestIntegrity,
        [string]$ExecutionStatus,
        [AllowEmptyString()][string]$RawOutput = "",
        [AllowEmptyString()][string]$Stderr = "",
        [string]$FinishedAt,
        [string]$Transport
    )
    $parts = @(
        $RequestId,
        [string]$RequestSequence,
        $RequestIntegrity,
        $ExecutionStatus,
        $RawOutput,
        $Stderr,
        $FinishedAt,
        $Transport
    )
    return ($parts -join "`n")
}

function Build-AdbArguments {
    param([string]$Command)
    if ([string]::IsNullOrWhiteSpace($AdbSerial)) {
        return @("shell", $Command)
    }
    return @("-s", $AdbSerial, "shell", $Command)
}

function Test-IsAssetPushCommand {
    param([string]$Command)
    return $Command -match '^AURA_ADB_PUSH\s+'
}

function Parse-AssetPushCommand {
    param([string]$Command)
    $parts = @($Command -split '\s+')
    if ($parts.Count -ne 5) {
        return @{ ok = $false; reason = "asset_push_format_invalid" }
    }
    $sourceRel = $parts[1]
    $targetPath = $parts[2]
    $expectedSha = $parts[3].ToLowerInvariant()
    $overwritePolicy = $parts[4]

    if ($sourceRel -notmatch '^[A-Za-z0-9._/-]+$' -or $sourceRel.Contains('..')) {
        return @{ ok = $false; reason = "asset_push_source_invalid" }
    }
    if ($targetPath -notmatch '^/data/local/tmp/aura/audio/[A-Za-z0-9._/-]+$') {
        return @{ ok = $false; reason = "asset_push_target_invalid" }
    }
    if ($expectedSha -notmatch '^[0-9a-f]{64}$') {
        return @{ ok = $false; reason = "asset_push_sha256_invalid" }
    }
    if ($overwritePolicy -notin @("no_overwrite", "allow_overwrite")) {
        return @{ ok = $false; reason = "asset_push_overwrite_policy_invalid" }
    }
    return @{
        ok = $true
        source_rel = $sourceRel
        target_path = $targetPath
        expected_sha256 = $expectedSha
        overwrite_policy = $overwritePolicy
    }
}

function Invoke-AdbCli {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $AdbPath
    $psi.ArgumentList.Clear()
    foreach ($arg in $Arguments) {
        [void]$psi.ArgumentList.Add($arg)
    }
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.Start()
    $finished = $proc.WaitForExit($TimeoutSeconds * 1000)
    if (-not $finished) {
        try { $proc.Kill() } catch {}
        try { $proc.WaitForExit() } catch {}
        return @{
            status = "timeout"
            exit_code = -1
            stdout = ""
            stderr = "command_timeout"
            invocation = "$AdbPath $($Arguments -join ' ')"
        }
    }
    return @{
        status = $(if ($proc.ExitCode -eq 0) { "executed" } else { "failed" })
        exit_code = $proc.ExitCode
        stdout = $proc.StandardOutput.ReadToEnd()
        stderr = $proc.StandardError.ReadToEnd()
        invocation = "$AdbPath $($Arguments -join ' ')"
    }
}

function Invoke-AdbPushOperation {
    param(
        [Parameter(Mandatory = $true)][string]$NormalizedCommand,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $startedAt = (Get-Date).ToUniversalTime().ToString("o")
    $parsed = Parse-AssetPushCommand -Command $NormalizedCommand
    if (-not [bool]$parsed.ok) {
        $finishedAt = (Get-Date).ToUniversalTime().ToString("o")
        return @{
            normalized_command = $NormalizedCommand
            raw_executor_invocation = "asset_push_parse_failed"
            expanded_command = "adb.exe push <bridge_asset> <target_path>"
            execution_status = "failed"
            exit_code = 2
            stdout = ""
            stderr = [string]$parsed.reason
            started_at = $startedAt
            finished_at = $finishedAt
        }
    }

    $sourceRelWin = ([string]$parsed.source_rel).Replace('/', '\')
    $sourcePath = Join-Path $BridgeRoot $sourceRelWin
    if (-not (Test-Path $sourcePath)) {
        $finishedAt = (Get-Date).ToUniversalTime().ToString("o")
        return @{
            normalized_command = $NormalizedCommand
            raw_executor_invocation = "asset_missing:$sourcePath"
            expanded_command = "adb.exe push <bridge_asset> <target_path>"
            execution_status = "failed"
            exit_code = 3
            stdout = ""
            stderr = "asset_source_missing"
            started_at = $startedAt
            finished_at = $finishedAt
        }
    }

    $srcSha = (Get-FileHash -Path $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($srcSha -ne [string]$parsed.expected_sha256) {
        $finishedAt = (Get-Date).ToUniversalTime().ToString("o")
        return @{
            normalized_command = $NormalizedCommand
            raw_executor_invocation = "asset_hash_mismatch:$sourcePath"
            expanded_command = "adb.exe push <bridge_asset> <target_path>"
            execution_status = "failed"
            exit_code = 4
            stdout = ""
            stderr = "asset_source_sha256_mismatch"
            started_at = $startedAt
            finished_at = $finishedAt
        }
    }

    if ([string]$parsed.overwrite_policy -eq "no_overwrite") {
        $existsArgs = if ([string]::IsNullOrWhiteSpace($AdbSerial)) {
            @("shell", "ls " + [string]$parsed.target_path)
        } else {
            @("-s", $AdbSerial, "shell", "ls " + [string]$parsed.target_path)
        }
        $existsResult = Invoke-AdbCli -Arguments $existsArgs -TimeoutSeconds $TimeoutSeconds
        if ([int]$existsResult.exit_code -eq 0) {
            $finishedAt = (Get-Date).ToUniversalTime().ToString("o")
            return @{
                normalized_command = $NormalizedCommand
                raw_executor_invocation = [string]$existsResult.invocation
                expanded_command = "adb.exe push <bridge_asset> <target_path>"
                execution_status = "failed"
                exit_code = 5
                stdout = ""
                stderr = "target_exists_overwrite_blocked"
                started_at = $startedAt
                finished_at = $finishedAt
            }
        }
    }

    $pushArgs = if ([string]::IsNullOrWhiteSpace($AdbSerial)) {
        @("push", $sourcePath, [string]$parsed.target_path)
    } else {
        @("-s", $AdbSerial, "push", $sourcePath, [string]$parsed.target_path)
    }
    $pushResult = Invoke-AdbCli -Arguments $pushArgs -TimeoutSeconds $TimeoutSeconds
    if ([int]$pushResult.exit_code -ne 0) {
        $finishedAt = (Get-Date).ToUniversalTime().ToString("o")
        return @{
            normalized_command = $NormalizedCommand
            raw_executor_invocation = [string]$pushResult.invocation
            expanded_command = "adb.exe push <bridge_asset> <target_path>"
            execution_status = "failed"
            exit_code = [int]$pushResult.exit_code
            stdout = [string]$pushResult.stdout
            stderr = "adb_push_failed:$([string]$pushResult.stderr)"
            started_at = $startedAt
            finished_at = $finishedAt
        }
    }

    $sumCmd = "sha256sum " + [string]$parsed.target_path
    $sumArgs = if ([string]::IsNullOrWhiteSpace($AdbSerial)) {
        @("shell", $sumCmd)
    } else {
        @("-s", $AdbSerial, "shell", $sumCmd)
    }
    $sumResult = Invoke-AdbCli -Arguments $sumArgs -TimeoutSeconds $TimeoutSeconds
    if ([int]$sumResult.exit_code -ne 0 -or [string]::IsNullOrWhiteSpace([string]$sumResult.stdout)) {
        $sumCmd = "toybox sha256sum " + [string]$parsed.target_path
        $sumArgs = if ([string]::IsNullOrWhiteSpace($AdbSerial)) {
            @("shell", $sumCmd)
        } else {
            @("-s", $AdbSerial, "shell", $sumCmd)
        }
        $sumResult = Invoke-AdbCli -Arguments $sumArgs -TimeoutSeconds $TimeoutSeconds
    }

    $targetSha = ""
    if (-not [string]::IsNullOrWhiteSpace([string]$sumResult.stdout)) {
        $targetSha = ([string]$sumResult.stdout).Trim().Split(' ')[0].ToLowerInvariant()
    }
    if ([string]::IsNullOrWhiteSpace($targetSha) -or $targetSha -ne [string]$parsed.expected_sha256) {
        $finishedAt = (Get-Date).ToUniversalTime().ToString("o")
        return @{
            normalized_command = $NormalizedCommand
            raw_executor_invocation = [string]$pushResult.invocation
            expanded_command = "adb.exe push <bridge_asset> <target_path>"
            execution_status = "failed"
            exit_code = 6
            stdout = [string]$pushResult.stdout
            stderr = "target_sha256_verification_failed"
            started_at = $startedAt
            finished_at = $finishedAt
        }
    }

    $finishedAt = (Get-Date).ToUniversalTime().ToString("o")
    return @{
        normalized_command = $NormalizedCommand
        raw_executor_invocation = [string]$pushResult.invocation
        expanded_command = "adb.exe push <bridge_asset> <target_path>"
        execution_status = "executed"
        exit_code = 0
        stdout = [string]$pushResult.stdout
        stderr = ""
        started_at = $startedAt
        finished_at = $finishedAt
    }
}

function Test-IsPlaybackAplayCommand {
    param([string]$Command)
    return $Command -match '^AURA_PLAYBACK_APLAY\s+'
}

function Parse-PlaybackAplayCommand {
    param([string]$Command)
    $parts = @($Command -split '\s+')
    if ($parts.Count -ne 3) {
        return @{ ok = $false; reason = "playback_aplay_format_invalid" }
    }
    $alsaDevice = $parts[1]
    $targetPath = $parts[2]
    if ($alsaDevice -notmatch '^(hw|plughw):\d+,\d+$') {
        return @{ ok = $false; reason = "playback_aplay_device_invalid" }
    }
    if ($targetPath -notmatch '^/data/local/tmp/aura/audio/[A-Za-z0-9._/-]+$') {
        return @{ ok = $false; reason = "playback_aplay_target_invalid" }
    }
    return @{
        ok = $true
        alsa_device = $alsaDevice
        target_path = $targetPath
    }
}

function Test-IsPlaybackTinyplayCommand {
    param([string]$Command)
    return $Command -match '^AURA_PLAYBACK_TINYPLAY\s+'
}

function Parse-PlaybackTinyplayCommand {
    param([string]$Command)
    $parts = @($Command -split '\s+')
    if ($parts.Count -ne 4) {
        return @{ ok = $false; reason = "playback_tinyplay_format_invalid" }
    }
    $targetPath = $parts[1]
    $card = $parts[2]
    $device = $parts[3]
    if ($targetPath -notmatch '^/data/local/tmp/aura/audio/[A-Za-z0-9._/-]+$') {
        return @{ ok = $false; reason = "playback_tinyplay_target_invalid" }
    }
    if ($card -notmatch '^\d+$' -or $device -notmatch '^\d+$') {
        return @{ ok = $false; reason = "playback_tinyplay_card_or_device_invalid" }
    }
    return @{
        ok = $true
        target_path = $targetPath
        card = $card
        device = $device
    }
}

function Test-IsTinymixSetCommand {
    param([string]$Command)
    return $Command -match '^AURA_TINYMIX_SET\s+'
}

function Parse-TinymixSetCommand {
    param([string]$Command)
    $parts = @($Command -split '\s+')
    if ($parts.Count -ne 3) {
        return @{ ok = $false; reason = "tinymix_set_format_invalid" }
    }
    $controlId = $parts[1]
    $value = $parts[2]
    if ($controlId -notmatch '^\d+$' -or $value -notmatch '^-?\d+$') {
        return @{ ok = $false; reason = "tinymix_set_value_invalid" }
    }
    return @{
        ok = $true
        control_id = $controlId
        value = $value
    }
}

function Test-IsAmixerCsetCommand {
    param([string]$Command)
    return $Command -match '^AURA_AMIXER_CSET\s+'
}

function Parse-AmixerCsetCommand {
    param([string]$Command)
    $parts = @($Command -split '\s+')
    if ($parts.Count -ne 3) {
        return @{ ok = $false; reason = "amixer_cset_format_invalid" }
    }
    $numid = $parts[1]
    $value = $parts[2]
    if ($numid -notmatch '^numid=\d+$' -or $value -notmatch '^[A-Za-z0-9_+.,-]+$') {
        return @{ ok = $false; reason = "amixer_cset_value_invalid" }
    }
    return @{
        ok = $true
        numid = $numid
        value = $value
    }
}

function Test-IsAmixerNameSetCommand {
    param([string]$Command)
    return $Command -match '^AURA_AMIXER_NAME_SET\s+'
}

function Parse-AmixerNameSetCommand {
    param([string]$Command)
    $parts = @($Command -split '\s+')
    if ($parts.Count -ne 3) {
        return @{ ok = $false; reason = "amixer_name_set_format_invalid" }
    }
    $encodedName = $parts[1]
    $value = $parts[2]
    if ($encodedName -notmatch '^[A-Za-z0-9_-]+$') {
        return @{ ok = $false; reason = "amixer_name_set_name_encoding_invalid" }
    }
    if ($value -notmatch '^[A-Za-z0-9_+.,-]+$') {
        return @{ ok = $false; reason = "amixer_name_set_value_invalid" }
    }

    $decodedName = ""
    try {
        $decodedName = Decode-Base64UrlUtf8 -InputText $encodedName
    } catch {
        return @{ ok = $false; reason = "amixer_name_set_name_decode_invalid" }
    }
    if ($decodedName -notmatch '^[A-Za-z0-9 _+./-]+$') {
        return @{ ok = $false; reason = "amixer_name_set_name_invalid" }
    }

    return @{
        ok = $true
        encoded_name = $encodedName
        decoded_name = $decodedName
        value = $value
    }
}

function Test-IsCleanupCommand {
    param([string]$Command)
    return $Command -match '^AURA_ADB_RM\s+'
}

function Parse-CleanupCommand {
    param([string]$Command)
    $parts = @($Command -split '\s+')
    if ($parts.Count -ne 2) {
        return @{ ok = $false; reason = "cleanup_format_invalid" }
    }
    $targetPath = $parts[1]
    if ($targetPath -notmatch '^/data/local/tmp/aura/audio/[A-Za-z0-9._/-]+$') {
        return @{ ok = $false; reason = "cleanup_target_invalid" }
    }
    return @{
        ok = $true
        target_path = $targetPath
    }
}

function Invoke-AdbShellOperation {
    param(
        [Parameter(Mandatory = $true)][string]$NormalizedCommand,
        [Parameter(Mandatory = $true)][string]$ActualShellCommand,
        [Parameter(Mandatory = $true)][string]$ExpandedCommand,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $startedAt = (Get-Date).ToUniversalTime().ToString("o")
    $shellArgs = if ([string]::IsNullOrWhiteSpace($AdbSerial)) {
        @("shell", $ActualShellCommand)
    } else {
        @("-s", $AdbSerial, "shell", $ActualShellCommand)
    }
    $result = Invoke-AdbCli -Arguments $shellArgs -TimeoutSeconds $TimeoutSeconds
    $finishedAt = (Get-Date).ToUniversalTime().ToString("o")

    $status = [string]$result.status
    $exitCode = [int]$result.exit_code
    $stdoutText = [string]$result.stdout
    $stderrText = [string]$result.stderr
    $combined = ($stdoutText + "`n" + $stderrText).ToLowerInvariant()

    if ($status -eq "executed") {
        if (
            $combined -match "audio open error" -or
            $combined -match "no such file or directory" -or
            $combined -match "invalid argument" -or
            $combined -match "device or resource busy" -or
            $combined -match "failed to"
        ) {
            $status = "failed"
            if ($exitCode -eq 0) {
                $exitCode = 32
            }
        }
    }
    if ($status -eq "timeout") {
        $exitCode = -1
    }

    return @{
        normalized_command = $NormalizedCommand
        raw_executor_invocation = [string]$result.invocation
        expanded_command = $ExpandedCommand
        execution_status = $(if ($status -eq "executed") { "executed" } elseif ($status -eq "timeout") { "timeout" } else { "failed" })
        exit_code = $exitCode
        stdout = $stdoutText
        stderr = $stderrText
        started_at = $startedAt
        finished_at = $finishedAt
    }
}

function Invoke-PlaybackAplayOperation {
    param(
        [Parameter(Mandatory = $true)][string]$NormalizedCommand,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )
    $parsed = Parse-PlaybackAplayCommand -Command $NormalizedCommand
    if (-not [bool]$parsed.ok) {
        $now = (Get-Date).ToUniversalTime().ToString("o")
        return @{
            normalized_command = $NormalizedCommand
            raw_executor_invocation = "playback_aplay_parse_failed"
            expanded_command = "adb.exe shell aplay -D <(plug)hw:x,y> <target_path>"
            execution_status = "failed"
            exit_code = 2
            stdout = ""
            stderr = [string]$parsed.reason
            started_at = $now
            finished_at = $now
        }
    }
    $actual = "aplay -D " + [string]$parsed.alsa_device + " " + [string]$parsed.target_path
    return Invoke-AdbShellOperation -NormalizedCommand $NormalizedCommand -ActualShellCommand $actual -ExpandedCommand "adb.exe shell aplay -D <(plug)hw:x,y> <target_path>" -TimeoutSeconds $TimeoutSeconds
}

function Invoke-PlaybackTinyplayOperation {
    param(
        [Parameter(Mandatory = $true)][string]$NormalizedCommand,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )
    $parsed = Parse-PlaybackTinyplayCommand -Command $NormalizedCommand
    if (-not [bool]$parsed.ok) {
        $now = (Get-Date).ToUniversalTime().ToString("o")
        return @{
            normalized_command = $NormalizedCommand
            raw_executor_invocation = "playback_tinyplay_parse_failed"
            expanded_command = "adb.exe shell tinyplay <target_path> -D <card> -d <device>"
            execution_status = "failed"
            exit_code = 2
            stdout = ""
            stderr = [string]$parsed.reason
            started_at = $now
            finished_at = $now
        }
    }
    $actual = "tinyplay " + [string]$parsed.target_path + " -D " + [string]$parsed.card + " -d " + [string]$parsed.device
    return Invoke-AdbShellOperation -NormalizedCommand $NormalizedCommand -ActualShellCommand $actual -ExpandedCommand "adb.exe shell tinyplay <target_path> -D <card> -d <device>" -TimeoutSeconds $TimeoutSeconds
}

function Invoke-TinymixSetOperation {
    param(
        [Parameter(Mandatory = $true)][string]$NormalizedCommand,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )
    $parsed = Parse-TinymixSetCommand -Command $NormalizedCommand
    if (-not [bool]$parsed.ok) {
        $now = (Get-Date).ToUniversalTime().ToString("o")
        return @{
            normalized_command = $NormalizedCommand
            raw_executor_invocation = "tinymix_set_parse_failed"
            expanded_command = "adb.exe shell tinymix <control_id> <value>"
            execution_status = "failed"
            exit_code = 2
            stdout = ""
            stderr = [string]$parsed.reason
            started_at = $now
            finished_at = $now
        }
    }
    $actual = "tinymix " + [string]$parsed.control_id + " " + [string]$parsed.value
    return Invoke-AdbShellOperation -NormalizedCommand $NormalizedCommand -ActualShellCommand $actual -ExpandedCommand "adb.exe shell tinymix <control_id> <value>" -TimeoutSeconds $TimeoutSeconds
}

function Invoke-AmixerCsetOperation {
    param(
        [Parameter(Mandatory = $true)][string]$NormalizedCommand,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )
    $parsed = Parse-AmixerCsetCommand -Command $NormalizedCommand
    if (-not [bool]$parsed.ok) {
        $now = (Get-Date).ToUniversalTime().ToString("o")
        return @{
            normalized_command = $NormalizedCommand
            raw_executor_invocation = "amixer_cset_parse_failed"
            expanded_command = "adb.exe shell amixer cset numid=<id> <value>"
            execution_status = "failed"
            exit_code = 2
            stdout = ""
            stderr = [string]$parsed.reason
            started_at = $now
            finished_at = $now
        }
    }
    $actual = "amixer cset " + [string]$parsed.numid + " " + [string]$parsed.value
    return Invoke-AdbShellOperation -NormalizedCommand $NormalizedCommand -ActualShellCommand $actual -ExpandedCommand "adb.exe shell amixer cset numid=<id> <value>" -TimeoutSeconds $TimeoutSeconds
}

function Invoke-AmixerNameSetOperation {
    param(
        [Parameter(Mandatory = $true)][string]$NormalizedCommand,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )
    $parsed = Parse-AmixerNameSetCommand -Command $NormalizedCommand
    if (-not [bool]$parsed.ok) {
        $now = (Get-Date).ToUniversalTime().ToString("o")
        return @{
            normalized_command = $NormalizedCommand
            raw_executor_invocation = "amixer_name_set_parse_failed"
            expanded_command = "adb.exe shell amixer -c 0 cset iface=MIXER,name='<control>' '<value>'"
            execution_status = "failed"
            exit_code = 2
            stdout = ""
            stderr = [string]$parsed.reason
            started_at = $now
            finished_at = $now
        }
    }
    $actual = "amixer -c 0 cset iface=MIXER,name='" + [string]$parsed.decoded_name + "' '" + [string]$parsed.value + "'"
    return Invoke-AdbShellOperation -NormalizedCommand $NormalizedCommand -ActualShellCommand $actual -ExpandedCommand "adb.exe shell amixer -c 0 cset iface=MIXER,name='<control>' '<value>'" -TimeoutSeconds $TimeoutSeconds
}

function Invoke-CleanupOperation {
    param(
        [Parameter(Mandatory = $true)][string]$NormalizedCommand,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )
    $parsed = Parse-CleanupCommand -Command $NormalizedCommand
    if (-not [bool]$parsed.ok) {
        $now = (Get-Date).ToUniversalTime().ToString("o")
        return @{
            normalized_command = $NormalizedCommand
            raw_executor_invocation = "cleanup_parse_failed"
            expanded_command = "adb.exe shell rm -f <target_path>"
            execution_status = "failed"
            exit_code = 2
            stdout = ""
            stderr = [string]$parsed.reason
            started_at = $now
            finished_at = $now
        }
    }
    $actual = "rm -f " + [string]$parsed.target_path
    return Invoke-AdbShellOperation -NormalizedCommand $NormalizedCommand -ActualShellCommand $actual -ExpandedCommand "adb.exe shell rm -f <target_path>" -TimeoutSeconds $TimeoutSeconds
}

function Invoke-BoundedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$NormalizedCommand,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $startedAt = (Get-Date).ToUniversalTime().ToString("o")
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $rawInvocation = ""

    if ($UseAdbShell) {
        $psi.FileName = $AdbPath
        $argsArray = Build-AdbArguments -Command $NormalizedCommand
        $psi.ArgumentList.Clear()
        foreach ($arg in $argsArray) { [void]$psi.ArgumentList.Add($arg) }
        $rawInvocation = "$AdbPath $($argsArray -join ' ')"
    } else {
        $psi.FileName = "cmd.exe"
        $psi.Arguments = "/d /s /c `"$NormalizedCommand`""
        $rawInvocation = "cmd.exe $($psi.Arguments)"
    }

    if ($LiveTrace) {
        Write-Host ("[TARGET][INVOKE] {0}" -f $rawInvocation)
    }

    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.Start()

    $finishedInTime = $proc.WaitForExit($TimeoutSeconds * 1000)
    if (-not $finishedInTime) {
        try { $proc.Kill() } catch {}
        try { $proc.WaitForExit() } catch {}
        $stdout = ""
        $stderr = "command_timeout"
        $finishedAt = (Get-Date).ToUniversalTime().ToString("o")
        if ($LiveTrace) {
            Write-Host "[TARGET][STATUS] command_status=timeout exit_code=-1"
        }
        return @{
            normalized_command = $NormalizedCommand
            raw_executor_invocation = $rawInvocation
            expanded_command = $(if ($UseAdbShell) { "adb.exe shell <normalized_command>" } else { "cmd.exe /c <normalized_command>" })
            execution_status = "timeout"
            exit_code = -1
            stdout = $stdout
            stderr = $stderr
            started_at = $startedAt
            finished_at = $finishedAt
        }
    }

    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $exitCode = $proc.ExitCode
    $status = if ($exitCode -eq 0) { "executed" } else { "failed" }
    $combinedText = (($stdout ?? "") + "`n" + ($stderr ?? "")).ToLowerInvariant()
    if ($combinedText -match "/bin/sh: .* not found" -or $combinedText -match "not recognized as an internal or external command") {
        if ($exitCode -eq 0) {
            $exitCode = 127
        }
        $status = "failed"
    }
    $finishedAt = (Get-Date).ToUniversalTime().ToString("o")

    if ($LiveTrace) {
        foreach ($line in ($stdout -split "`r?`n")) {
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                Write-Host ("[TARGET][STDOUT] {0}" -f $line)
            }
        }
        foreach ($line in ($stderr -split "`r?`n")) {
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                Write-Host ("[TARGET][STDERR] {0}" -f $line)
            }
        }
        Write-Host ("[TARGET][STATUS] command_status={0} exit_code={1}" -f $status, $exitCode)
    }

    return @{
        normalized_command = $NormalizedCommand
        raw_executor_invocation = $rawInvocation
        expanded_command = $(if ($UseAdbShell) { "adb.exe shell <normalized_command>" } else { "cmd.exe /c <normalized_command>" })
        execution_status = $status
        exit_code = $exitCode
        stdout = $stdout
        stderr = $stderr
        started_at = $startedAt
        finished_at = $finishedAt
    }
}

function Get-AdbDeviceState {
    if (-not $UseAdbShell) {
        return @{ connected = $true; state = "local_mode"; stderr = "" }
    }
    if (-not (Test-Path $AdbPath)) {
        return @{ connected = $false; state = "adb_binary_missing"; stderr = "adb_binary_missing:$AdbPath" }
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $AdbPath
    if ([string]::IsNullOrWhiteSpace($AdbSerial)) {
        $psi.Arguments = "devices"
    } else {
        $psi.Arguments = ('-s "{0}" get-state' -f $AdbSerial)
    }
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.Start()
    [void]$proc.WaitForExit(5000)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()

    if ($proc.ExitCode -ne 0) {
        return @{ connected = $false; state = "adb_query_failed"; stderr = ("adb_query_failed: exit_code={0}; stderr={1}" -f $proc.ExitCode, $stderr) }
    }

    if ([string]::IsNullOrWhiteSpace($AdbSerial)) {
        $lines = @($stdout -split "`r?`n" | Where-Object { $_ -match "^\S+\s+device$" })
        if ($lines.Count -lt 1) {
            return @{ connected = $false; state = "no_adb_device"; stderr = "adb_no_device" }
        }
        return @{ connected = $true; state = "device"; stderr = "" }
    }

    if ($stdout -match "device") {
        return @{ connected = $true; state = "device"; stderr = "" }
    }
    return @{ connected = $false; state = "unknown"; stderr = ("adb_state_unknown:{0}" -f $stdout.Trim()) }
}

function Build-Response {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Request,
        [Parameter(Mandatory = $true)][string]$ExecutionStatus,
        [AllowEmptyString()][string]$RawOutput = "",
        [AllowEmptyString()][string]$Stderr = "",
        [Parameter(Mandatory = $true)][hashtable]$Timestamps,
        [array]$ExecutorCommandTrace = @(),
        [array]$TransportExpansionTrace = @(),
        [array]$RawExecutorInvocation = @()
    )

    $requestId = [string]$Request.request_id
    $requestSequence = [int]$Request.request_sequence
    $requestIntegrity = [string]$Request.request_integrity_sha256
    $transport = [string]$Request.transport

    $digestInput = Build-ResponseDigestInput `
        -RequestId $requestId `
        -RequestSequence $requestSequence `
        -RequestIntegrity $requestIntegrity `
        -ExecutionStatus $ExecutionStatus `
        -RawOutput $RawOutput `
        -Stderr $Stderr `
        -FinishedAt ([string]$Timestamps.finished_at) `
        -Transport $transport
    $responseHash = Get-Sha256Hex -Text $digestInput

    return [ordered]@{
        protocol_version = "bridge-v1"
        request_id = $requestId
        request_sequence = $requestSequence
        approved_commands = @($Request.approved_commands)
        command_entries = @($Request.command_entries)
        timeout_seconds = [int]$Request.timeout_seconds
        transport = $transport
        execution_mode = [string]$Request.execution_mode
        timestamps = $Timestamps
        execution_status = $ExecutionStatus
        raw_output = $RawOutput
        stderr = $Stderr
        request_integrity_sha256 = $requestIntegrity
        response_integrity_sha256 = $responseHash
        raw_executor_invocation = $RawExecutorInvocation
        executor_command_trace = $ExecutorCommandTrace
        transport_expansion_trace = $TransportExpansionTrace
        executor_identity = @{
            worker_id = ("{0}@{1}" -f $env:USERNAME, $env:COMPUTERNAME)
            username = $env:USERNAME
            hostname = $env:COMPUTERNAME
            worker_type = "windows_shared_folder_worker"
        }
        transport_metadata = @{
            bridge_root = $BridgeRoot
            worker_transport = "shared_folder"
            command_runtime = $(if ($UseAdbShell) { "adb_shell" } else { "local_cmd" })
            adb_path = $AdbPath
            adb_serial = $AdbSerial
        }
    }
}

function Save-Response {
    param([Parameter(Mandatory = $true)][string]$RequestId, [Parameter(Mandatory = $true)][hashtable]$ResponsePayload)
    $responsePath = Join-Path $ResponsesDir "$RequestId.json"
    $tmpPath = "$responsePath.tmp.$PID"
    $json = $ResponsePayload | ConvertTo-Json -Depth 10
    Set-Content -Path $tmpPath -Value $json -Encoding UTF8
    Move-Item -Path $tmpPath -Destination $responsePath -Force
}

function Is-ReplayedRequestId {
    param([string]$RequestId)
    $seen = Get-Content -Path $ProcessedLog -ErrorAction SilentlyContinue
    return ($seen -contains $RequestId)
}

function Mark-ProcessedRequestId {
    param([string]$RequestId)
    Add-Content -Path $ProcessedLog -Value $RequestId -Encoding UTF8
}

function Process-OneRequestFile {
    param([Parameter(Mandatory = $true)][System.IO.FileInfo]$RequestFile)

    $receivedAt = (Get-Date).ToUniversalTime().ToString("o")
    $requestRaw = Get-Content -Path $RequestFile.FullName -Raw -Encoding UTF8
    try {
        $requestObj = $requestRaw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-WorkerLog "malformed_json file=$($RequestFile.FullName) err=$($_.Exception.Message)"
        Move-Item -Path $RequestFile.FullName -Destination (Join-Path $DeliveredDir "$($RequestFile.Name).bad") -Force
        return
    }

    $request = @{}
    foreach ($p in $requestObj.PSObject.Properties) { $request[$p.Name] = $p.Value }

    $required = @(
        "request_id", "request_sequence", "approved_commands", "timeout_seconds",
        "transport", "execution_mode", "request_integrity_sha256", "command_entries"
    )
    foreach ($key in $required) {
        if (-not $request.ContainsKey($key)) {
            $timestamps = @{ received_at = $receivedAt; started_at = $receivedAt; finished_at = (Get-Date).ToUniversalTime().ToString("o") }
            $fallback = @{
                request_id = [string]($request.request_id)
                request_sequence = [int]($request.request_sequence)
                approved_commands = @()
                command_entries = @()
                timeout_seconds = 1
                transport = "shared_folder"
                execution_mode = "governed_read_only"
                request_integrity_sha256 = ""
            }
            if ([string]::IsNullOrWhiteSpace([string]$fallback.request_id)) {
                Move-Item -Path $RequestFile.FullName -Destination (Join-Path $DeliveredDir "$($RequestFile.Name).bad") -Force
                Write-WorkerLog "dropped malformed request without request_id file=$($RequestFile.FullName)"
                return
            }
            $response = Build-Response -Request $fallback -ExecutionStatus "rejected_malformed_request" -RawOutput "" -Stderr "missing_field:$key" -Timestamps $timestamps
            Save-Response -RequestId ([string]$fallback.request_id) -ResponsePayload $response
            Move-Item -Path $RequestFile.FullName -Destination (Join-Path $DeliveredDir $RequestFile.Name) -Force
            Write-WorkerLog "rejected_malformed_request id=$($fallback.request_id) reason=missing_field:$key"
            return
        }
    }

    $requestId = [string]$request.request_id
    $requestSequence = [int]$request.request_sequence
    $timeoutSeconds = [int]$request.timeout_seconds
    $executionMode = [string]$request.execution_mode
    $transport = [string]$request.transport

    if (Is-ReplayedRequestId -RequestId $requestId) {
        $timestamps = @{ received_at = $receivedAt; started_at = $receivedAt; finished_at = (Get-Date).ToUniversalTime().ToString("o") }
        $response = Build-Response -Request $request -ExecutionStatus "rejected" -RawOutput "" -Stderr "replayed_request_id" -Timestamps $timestamps
        Save-Response -RequestId $requestId -ResponsePayload $response
        Move-Item -Path $RequestFile.FullName -Destination (Join-Path $DeliveredDir $RequestFile.Name) -Force
        Write-WorkerLog "rejected replayed request_id=$requestId seq=$requestSequence"
        return
    }

    $approved = @()
    foreach ($c in @($request.approved_commands)) {
        $approved += (Normalize-CanonicalCommand -Command ([string]$c))
    }

    $requestDigestInput = Build-RequestDigestInput `
        -RequestId $requestId `
        -RequestSequence $requestSequence `
        -TimeoutSeconds $timeoutSeconds `
        -ExecutionMode $executionMode `
        -Transport $transport `
        -Commands $approved
    $computedRequestHash = Get-Sha256Hex -Text $requestDigestInput
    if ($computedRequestHash -ne [string]$request.request_integrity_sha256) {
        $timestamps = @{ received_at = $receivedAt; started_at = $receivedAt; finished_at = (Get-Date).ToUniversalTime().ToString("o") }
        $response = Build-Response -Request $request -ExecutionStatus "invalid" -RawOutput "" -Stderr "request_hash_mismatch" -Timestamps $timestamps
        Save-Response -RequestId $requestId -ResponsePayload $response
        Move-Item -Path $RequestFile.FullName -Destination (Join-Path $DeliveredDir $RequestFile.Name) -Force
        Mark-ProcessedRequestId -RequestId $requestId
        Write-WorkerLog "invalid request hash mismatch request_id=$requestId seq=$requestSequence"
        return
    }

    foreach ($cmd in $approved) {
        $isAssetPush = Test-IsAssetPushCommand -Command $cmd
        $isPlaybackAplay = Test-IsPlaybackAplayCommand -Command $cmd
        $isPlaybackTinyplay = Test-IsPlaybackTinyplayCommand -Command $cmd
        $isTinymixSet = Test-IsTinymixSetCommand -Command $cmd
        $isAmixerCset = Test-IsAmixerCsetCommand -Command $cmd
        $isAmixerNameSet = Test-IsAmixerNameSetCommand -Command $cmd
        $isCleanup = Test-IsCleanupCommand -Command $cmd

        if ($isAssetPush -or $isPlaybackAplay -or $isPlaybackTinyplay -or $isTinymixSet -or $isAmixerCset -or $isAmixerNameSet -or $isCleanup) {
            if (-not $EnableAssetPush) {
                $timestamps = @{ received_at = $receivedAt; started_at = $receivedAt; finished_at = (Get-Date).ToUniversalTime().ToString("o") }
                $response = Build-Response -Request $request -ExecutionStatus "rejected" -RawOutput "" -Stderr "governed_write_ops_disabled" -Timestamps $timestamps
                Save-Response -RequestId $requestId -ResponsePayload $response
                Move-Item -Path $RequestFile.FullName -Destination (Join-Path $DeliveredDir $RequestFile.Name) -Force
                Mark-ProcessedRequestId -RequestId $requestId
                Write-WorkerLog "rejected governed write disabled request_id=$requestId seq=$requestSequence"
                return
            }
            if ($executionMode -ne "governed_write_approved") {
                $timestamps = @{ received_at = $receivedAt; started_at = $receivedAt; finished_at = (Get-Date).ToUniversalTime().ToString("o") }
                $response = Build-Response -Request $request -ExecutionStatus "rejected" -RawOutput "" -Stderr "operator_approval_required_for_governed_write" -Timestamps $timestamps
                Save-Response -RequestId $requestId -ResponsePayload $response
                Move-Item -Path $RequestFile.FullName -Destination (Join-Path $DeliveredDir $RequestFile.Name) -Force
                Mark-ProcessedRequestId -RequestId $requestId
                Write-WorkerLog "rejected governed write missing operator approval request_id=$requestId seq=$requestSequence"
                return
            }
            $parsed = if ($isAssetPush) {
                Parse-AssetPushCommand -Command $cmd
            } elseif ($isPlaybackAplay) {
                Parse-PlaybackAplayCommand -Command $cmd
            } elseif ($isPlaybackTinyplay) {
                Parse-PlaybackTinyplayCommand -Command $cmd
            } elseif ($isTinymixSet) {
                Parse-TinymixSetCommand -Command $cmd
            } elseif ($isAmixerCset) {
                Parse-AmixerCsetCommand -Command $cmd
            } elseif ($isAmixerNameSet) {
                Parse-AmixerNameSetCommand -Command $cmd
            } else {
                Parse-CleanupCommand -Command $cmd
            }
            if (-not [bool]$parsed.ok) {
                $timestamps = @{ received_at = $receivedAt; started_at = $receivedAt; finished_at = (Get-Date).ToUniversalTime().ToString("o") }
                $response = Build-Response -Request $request -ExecutionStatus "rejected" -RawOutput "" -Stderr ([string]$parsed.reason) -Timestamps $timestamps
                Save-Response -RequestId $requestId -ResponsePayload $response
                Move-Item -Path $RequestFile.FullName -Destination (Join-Path $DeliveredDir $RequestFile.Name) -Force
                Mark-ProcessedRequestId -RequestId $requestId
                Write-WorkerLog "rejected governed command format request_id=$requestId seq=$requestSequence reason=$([string]$parsed.reason)"
                return
            }
            continue
        }

        $why = Test-ForbiddenCommand -Command $cmd
        if (-not [string]::IsNullOrWhiteSpace($why)) {
            $timestamps = @{ received_at = $receivedAt; started_at = $receivedAt; finished_at = (Get-Date).ToUniversalTime().ToString("o") }
            $response = Build-Response -Request $request -ExecutionStatus "rejected" -RawOutput "" -Stderr $why -Timestamps $timestamps
            Save-Response -RequestId $requestId -ResponsePayload $response
            Move-Item -Path $RequestFile.FullName -Destination (Join-Path $DeliveredDir $RequestFile.Name) -Force
            Mark-ProcessedRequestId -RequestId $requestId
            Write-WorkerLog "rejected forbidden command request_id=$requestId seq=$requestSequence reason=$why"
            return
        }
        if ($cmd -notin $AllowedCommands) {
            $timestamps = @{ received_at = $receivedAt; started_at = $receivedAt; finished_at = (Get-Date).ToUniversalTime().ToString("o") }
            $response = Build-Response -Request $request -ExecutionStatus "rejected" -RawOutput "" -Stderr "allowlist_violation" -Timestamps $timestamps
            Save-Response -RequestId $requestId -ResponsePayload $response
            Move-Item -Path $RequestFile.FullName -Destination (Join-Path $DeliveredDir $RequestFile.Name) -Force
            Mark-ProcessedRequestId -RequestId $requestId
            Write-WorkerLog "rejected allowlist violation request_id=$requestId seq=$requestSequence"
            return
        }
    }

    $adbState = Get-AdbDeviceState
    if (-not [bool]$adbState.connected) {
        $timestamps = @{ received_at = $receivedAt; started_at = $receivedAt; finished_at = (Get-Date).ToUniversalTime().ToString("o") }
        $response = Build-Response -Request $request -ExecutionStatus "transport_disconnected" -RawOutput "" -Stderr ([string]$adbState.stderr) -Timestamps $timestamps
        Save-Response -RequestId $requestId -ResponsePayload $response
        Move-Item -Path $RequestFile.FullName -Destination (Join-Path $DeliveredDir $RequestFile.Name) -Force
        Mark-ProcessedRequestId -RequestId $requestId
        Write-WorkerLog "transport_disconnected request_id=$requestId seq=$requestSequence reason=$([string]$adbState.state)"
        return
    }

    $allStdout = @()
    $allStderr = @()
    $commandTrace = @()
    $transportTrace = @()
    $rawInvocations = @()
    $finalStatus = "executed"
    $startedAt = (Get-Date).ToUniversalTime().ToString("o")

    foreach ($cmd in $approved) {
        if ($LiveTrace) { Write-Host ("[TARGET][EXEC] {0}" -f $cmd) }
        $result = if (Test-IsAssetPushCommand -Command $cmd) {
            Invoke-AdbPushOperation -NormalizedCommand $cmd -TimeoutSeconds $timeoutSeconds
        } elseif (Test-IsPlaybackAplayCommand -Command $cmd) {
            Invoke-PlaybackAplayOperation -NormalizedCommand $cmd -TimeoutSeconds $timeoutSeconds
        } elseif (Test-IsPlaybackTinyplayCommand -Command $cmd) {
            Invoke-PlaybackTinyplayOperation -NormalizedCommand $cmd -TimeoutSeconds $timeoutSeconds
        } elseif (Test-IsTinymixSetCommand -Command $cmd) {
            Invoke-TinymixSetOperation -NormalizedCommand $cmd -TimeoutSeconds $timeoutSeconds
        } elseif (Test-IsAmixerCsetCommand -Command $cmd) {
            Invoke-AmixerCsetOperation -NormalizedCommand $cmd -TimeoutSeconds $timeoutSeconds
        } elseif (Test-IsAmixerNameSetCommand -Command $cmd) {
            Invoke-AmixerNameSetOperation -NormalizedCommand $cmd -TimeoutSeconds $timeoutSeconds
        } elseif (Test-IsCleanupCommand -Command $cmd) {
            Invoke-CleanupOperation -NormalizedCommand $cmd -TimeoutSeconds $timeoutSeconds
        } else {
            Invoke-BoundedCommand -NormalizedCommand $cmd -TimeoutSeconds $timeoutSeconds
        }

        if (-not [string]::IsNullOrEmpty([string]$result.stdout)) { $allStdout += [string]$result.stdout }
        if (-not [string]::IsNullOrEmpty([string]$result.stderr)) { $allStderr += [string]$result.stderr }

        $rawInvocations += [string]$result.raw_executor_invocation
        $commandTrace += [ordered]@{
            normalized_command = [string]$result.normalized_command
            raw_executor_invocation = [string]$result.raw_executor_invocation
            exit_code = [int]$result.exit_code
            execution_status = [string]$result.execution_status
            stdout = [string]$result.stdout
            stderr = [string]$result.stderr
            started_at = [string]$result.started_at
            finished_at = [string]$result.finished_at
        }
        $transportTrace += [ordered]@{
            normalized_command = [string]$result.normalized_command
            expanded_command = [string]$result.expanded_command
            boundary = "adb_shell_boundary"
        }

        if ([string]$result.execution_status -eq "timeout") {
            $finalStatus = "timeout"
            break
        }
        if ([string]$result.execution_status -eq "failed") {
            $finalStatus = "failed"
        }
    }

    $timestamps = @{
        received_at = $receivedAt
        started_at = $startedAt
        finished_at = (Get-Date).ToUniversalTime().ToString("o")
    }
    $stdout = ($allStdout -join "`n")
    $stderr = ($allStderr -join "`n")

    $response = Build-Response `
        -Request $request `
        -ExecutionStatus $finalStatus `
        -RawOutput $stdout `
        -Stderr $stderr `
        -Timestamps $timestamps `
        -ExecutorCommandTrace $commandTrace `
        -TransportExpansionTrace $transportTrace `
        -RawExecutorInvocation $rawInvocations
    Save-Response -RequestId $requestId -ResponsePayload $response

    Move-Item -Path $RequestFile.FullName -Destination (Join-Path $DeliveredDir $RequestFile.Name) -Force
    Mark-ProcessedRequestId -RequestId $requestId
    Write-WorkerLog "processed request_id=$requestId seq=$requestSequence status=$finalStatus"
}

Write-Host "Windows bridge worker started"
Write-Host "BridgeRoot: $BridgeRoot"
Write-Host "Requests:   $RequestsDir"
Write-Host "Responses:  $ResponsesDir"
Write-Host "Allowed:    $($AllowedCommands -join ', ')"
Write-Host "WriteOps:   $(if ($EnableAssetPush) { 'governed write wrappers enabled' } else { 'disabled' })"
Write-Host "Runtime:    $(if ($UseAdbShell) { 'adb_shell' } else { 'local_cmd' })"
Write-Host "ADB Path:   $AdbPath"
if (-not [string]::IsNullOrWhiteSpace($AdbSerial)) { Write-Host "ADB Serial: $AdbSerial" }
Write-Host "LiveTrace:  $(if ($LiveTrace) { 'ON' } else { 'OFF' })"
Write-WorkerLog "worker_started bridge_root=$BridgeRoot"

while ($true) {
    $files = Get-ChildItem -Path $RequestsDir -Filter "*.json" -File | Sort-Object Name
    foreach ($f in $files) {
        Process-OneRequestFile -RequestFile $f
        if ($Once) {
            Write-WorkerLog "worker_exit_once"
            exit 0
        }
    }
    Start-Sleep -Seconds $PollSeconds
}
