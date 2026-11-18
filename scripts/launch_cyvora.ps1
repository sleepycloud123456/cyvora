# Start CYVORA for one local session and stop it when the desktop closes.
# This script does not register a scheduled task or a Windows service.
# -IncludeSupervisor opts into the local supervisor for this session only.
# -CreateShortcut writes a desktop shortcut to this script and does not install a task.
param(
    [switch]$IncludeSupervisor,
    [switch]$PaperTrader,
    [switch]$CreateShortcut,
    [int]$HealthTimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$api = $null
$supervisor = $null
$started = $false
$desktopStarted = $false
$desktopCode = 0

function Write-Fail {
    param([string]$Reason)
    Write-Output "CYVORA_LAUNCH_FAIL reason=$Reason"
}

function Stop-CyvoraProcess {
    param($Process)
    if ($null -eq $Process) { return }
    try {
        if (-not $Process.HasExited) {
            & taskkill.exe /PID $Process.Id /T /F | Out-Null
        }
    }
    catch {
        Write-Output "CYVORA_LAUNCH_STOP_WARN"
    }
}

function Record-Lifecycle {
    param([string]$Component, [string]$Action)
    & uv run python -m operations.lifecycle --component $Component --action $Action > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Output "CYVORA_LIFECYCLE_FAIL component=$Component action=$Action"
    }
}

if ($CreateShortcut) {
    try {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $shell = New-Object -ComObject WScript.Shell
        $linkPath = Join-Path $desktop "CYVORA Terminal.lnk"
        $link = $shell.CreateShortcut($linkPath)
        $link.TargetPath = "powershell.exe"
        $link.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
        $link.WorkingDirectory = $Root
        $link.Description = "CYVORA Terminal. Live trading stays locked."
        $link.Save()
        Write-Output "CYVORA_SHORTCUT_CREATED"
    }
    catch {
        Write-Output "CYVORA_SHORTCUT_FAIL"
    }
}

try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Fail "uv"
        exit 2
    }

    & uv run python -m operations.preflight > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "postgres"
        exit 2
    }
    Write-Output "CYVORA_POSTGRES_OK"

    & uv run alembic upgrade head > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "migrate"
        exit 2
    }

    $port = 8787
    if ($env:CYVORA_API_PORT -match '^[0-9]+$') {
        $parsedPort = [int]$env:CYVORA_API_PORT
        if ($parsedPort -ge 1 -and $parsedPort -le 65535) {
            $port = $parsedPort
        }
    }

    $uv = (Get-Command uv).Source
    $api = Start-Process -FilePath $uv -ArgumentList @("run", "cyvora-api") -WorkingDirectory $Root -PassThru -WindowStyle Hidden
    $started = $true

    $deadline = (Get-Date).AddSeconds($HealthTimeoutSeconds)
    $healthy = $false
    while ((Get-Date) -lt $deadline) {
        if ($api.HasExited) { break }
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $healthy = $true
                break
            }
        }
        catch {
            # The API is still starting. The error text is not printed.
        }
        Start-Sleep -Seconds 1
    }
    if (-not $healthy) {
        Write-Fail "health"
        exit 2
    }

    Record-Lifecycle "launcher" "started"
    Write-Output "CYVORA_LAUNCH_OK"
    Write-Output "api=running"

    if ($IncludeSupervisor) {
        $supervisorArgs = @(
            "run", "python", "-m", "operations.startup", "--ticks", "0", "--interval-seconds", "120"
        )
        if ($PaperTrader) {
            $supervisorArgs += "--paper-trader"
        }
        $supervisor = Start-Process -FilePath $uv -ArgumentList $supervisorArgs -WorkingDirectory $Root -PassThru -WindowStyle Hidden
        Write-Output "supervisor=started"
    }
    else {
        Write-Output "supervisor=off"
    }

    $desktopStarted = $true
    & uv run cyvora-desktop
    $desktopCode = $LASTEXITCODE
}
finally {
    if ($started) {
        if ($desktopStarted) {
            Record-Lifecycle "desktop" "stopped"
        }
        if ($null -ne $supervisor) {
            Record-Lifecycle "supervisor" "stopped"
        }
        Record-Lifecycle "api" "stopped"
        Record-Lifecycle "launcher" "stopped"
        Stop-CyvoraProcess $supervisor
        Stop-CyvoraProcess $api
        Write-Output "CYVORA_LAUNCH_STOPPED"
        Write-Output "live_trading_enabled=false"
    }
}

exit $desktopCode
