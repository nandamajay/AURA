param(
    [string]$BridgeRoot = "\\hu-nandam-hyd\workspace\AURA_V1\bridge",
    [string]$WorkerScript = "",
    [int]$CheckIntervalSeconds = 3,
    [int]$RestartDelaySeconds = 1,
    [int]$WorkerPollSeconds = 1,
    [string]$AdbPath = "C:\adb_tool\platform-tools\adb.exe",
    [string]$AdbSerial = "",
    [switch]$UseAdbShell = $true,
    [switch]$EnableAssetPush,
    [switch]$LiveTrace,
    [switch]$TakeoverExisting,
    [switch]$NoConsoleOutput
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($WorkerScript)) {
    $WorkerScript = Join-Path $PSScriptRoot "windows-bridge-worker.ps1"
}

$LogsDir = Join-Path $BridgeRoot "logs"
New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
$SupervisorLog = Join-Path $LogsDir "windows_supervisor.log"

function Write-SupervisorLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format o), $Message
    Add-Content -Path $SupervisorLog -Value $line -Encoding UTF8
    if (-not $NoConsoleOutput) {
        Write-Host $line
    }
}

function Resolve-PwshExecutable {
    $pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($pwshCmd) {
        return $pwshCmd.Source
    }
    $psCmd = Get-Command powershell -ErrorAction SilentlyContinue
    if ($psCmd) {
        return $psCmd.Source
    }
    throw "No PowerShell executable found (pwsh/powershell)."
}

function Get-FileHashOrEmpty {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    try {
        return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    } catch {
        return ""
    }
}

function Stop-ProcessSafely {
    param([System.Diagnostics.Process]$ProcessRef)
    if ($null -eq $ProcessRef) {
        return
    }
    try {
        if (-not $ProcessRef.HasExited) {
            Stop-Process -Id $ProcessRef.Id -Force -ErrorAction SilentlyContinue
        }
    } catch {
    }
}

function Stop-ExistingWorkerProcesses {
    param([string]$WorkerScriptPath)
    $workerLeaf = [System.IO.Path]::GetFileName($WorkerScriptPath)
    $targets = Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -like "*$workerLeaf*" -and
            $_.ProcessId -ne $PID
        }

    foreach ($target in $targets) {
        try {
            Stop-Process -Id $target.ProcessId -Force -ErrorAction Stop
            Write-SupervisorLog ("terminated_existing_worker pid={0}" -f $target.ProcessId)
        } catch {
            Write-SupervisorLog ("failed_terminate_existing_worker pid={0} err={1}" -f $target.ProcessId, $_.Exception.Message)
        }
    }
}

function Start-WorkerProcess {
    param(
        [string]$PwshExe,
        [string]$WorkerPath
    )
    $stamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
    $stdoutLog = Join-Path $LogsDir ("windows_worker_stdout_{0}.log" -f $stamp)
    $stderrLog = Join-Path $LogsDir ("windows_worker_stderr_{0}.log" -f $stamp)

    $args = @(
        "-ExecutionPolicy", "Bypass",
        "-File", $WorkerPath,
        "-BridgeRoot", $BridgeRoot,
        "-PollSeconds", [string]$WorkerPollSeconds,
        "-AdbPath", $AdbPath
    )

    if (-not [string]::IsNullOrWhiteSpace($AdbSerial)) {
        $args += @("-AdbSerial", $AdbSerial)
    }
    if ($UseAdbShell) {
        $args += "-UseAdbShell"
    }
    if ($EnableAssetPush) {
        $args += "-EnableAssetPush"
    }
    if ($LiveTrace) {
        $args += "-LiveTrace"
    }

    $proc = Start-Process `
        -FilePath $PwshExe `
        -ArgumentList $args `
        -PassThru `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog

    Write-SupervisorLog ("worker_started pid={0} stdout={1} stderr={2}" -f $proc.Id, $stdoutLog, $stderrLog)
    return $proc
}

if (-not (Test-Path -LiteralPath $WorkerScript)) {
    throw ("Worker script not found: {0}" -f $WorkerScript)
}

$pwshExe = Resolve-PwshExecutable
Write-SupervisorLog ("supervisor_started bridge_root={0} worker_script={1}" -f $BridgeRoot, $WorkerScript)
Write-SupervisorLog ("runtime pwsh={0} adb_path={1} adb_serial={2}" -f $pwshExe, $AdbPath, $AdbSerial)

if ($TakeoverExisting) {
    Stop-ExistingWorkerProcesses -WorkerScriptPath $WorkerScript
}

$workerHash = Get-FileHashOrEmpty -Path $WorkerScript
if ([string]::IsNullOrWhiteSpace($workerHash)) {
    throw ("Unable to hash worker script: {0}" -f $WorkerScript)
}
Write-SupervisorLog ("worker_hash={0}" -f $workerHash)

$workerProc = $null
try {
    $workerProc = Start-WorkerProcess -PwshExe $pwshExe -WorkerPath $WorkerScript
    while ($true) {
        Start-Sleep -Seconds $CheckIntervalSeconds

        $latestHash = Get-FileHashOrEmpty -Path $WorkerScript
        if (-not [string]::IsNullOrWhiteSpace($latestHash) -and $latestHash -ne $workerHash) {
            Write-SupervisorLog ("worker_hash_changed old={0} new={1}" -f $workerHash, $latestHash)
            Stop-ProcessSafely -ProcessRef $workerProc
            Start-Sleep -Seconds $RestartDelaySeconds
            $workerProc = Start-WorkerProcess -PwshExe $pwshExe -WorkerPath $WorkerScript
            $workerHash = $latestHash
            continue
        }

        if ($null -eq $workerProc -or $workerProc.HasExited) {
            $exitCode = if ($null -eq $workerProc) { -9999 } else { $workerProc.ExitCode }
            Write-SupervisorLog ("worker_exited restarting exit_code={0}" -f $exitCode)
            Start-Sleep -Seconds $RestartDelaySeconds
            $workerProc = Start-WorkerProcess -PwshExe $pwshExe -WorkerPath $WorkerScript
            continue
        }
    }
} finally {
    Write-SupervisorLog "supervisor_stopping"
    Stop-ProcessSafely -ProcessRef $workerProc
}
