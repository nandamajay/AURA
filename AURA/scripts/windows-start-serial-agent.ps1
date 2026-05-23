param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$ConfigPath = "",
    [string]$Host = "0.0.0.0",
    [int]$Port = 54888,
    [string]$LogPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "required_command_missing:$Name"
    }
}

Assert-Command -Name "python"

$sdkSrc = Join-Path $RepoRoot "workspace\aura-sdk\src"
if (-not (Test-Path $sdkSrc)) {
    throw "aura_sdk_source_not_found:$sdkSrc"
}

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $RepoRoot "scripts\windows-serial-agent-config.example.json"
}
if (-not (Test-Path $ConfigPath)) {
    throw "serial_agent_config_not_found:$ConfigPath"
}

if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogPath = Join-Path $RepoRoot "docs\operations\transport\remote_windows_bridge\windows_serial_agent_execution.jsonl"
}

$logDir = Split-Path -Parent $LogPath
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$configPayload = Get-Content -Path $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$requiredConfigKeys = @("com_port", "baudrate", "timeout_seconds", "prompt_regex", "reconnect_policy")
foreach ($key in $requiredConfigKeys) {
    if (-not ($configPayload.PSObject.Properties.Name -contains $key)) {
        throw "serial_agent_config_missing_key:$key"
    }
}

$pySerialCheck = python -c "import serial" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "pyserial_not_available"
}

if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $sdkSrc
} else {
    $env:PYTHONPATH = "$sdkSrc;$($env:PYTHONPATH)"
}

Write-Host "Starting Windows serial execute-only agent..."
Write-Host "Config: $ConfigPath"
Write-Host "Host:   $Host"
Write-Host "Port:   $Port"
Write-Host "Log:    $LogPath"

python -m aura_sdk.transport.windows_serial_agent `
    --config $ConfigPath `
    --host $Host `
    --port $Port `
    --log $LogPath
