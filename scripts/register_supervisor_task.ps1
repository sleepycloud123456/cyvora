# Prepare a logon task for the local supervisor.
# The default path prints the plan and does not register anything.
# Re-run with -ConfirmInstall only after you authorize a persistent task on this PC.
param(
    [switch]$ConfirmInstall
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not $ConfirmInstall) {
    Write-Output "CYVORA_SERVICE_NOT_INSTALLED"
    Write-Output "Planned task name: CYVORA Supervisor"
    Write-Output "Planned command: uv run python -m operations.startup --ticks 0 --interval-seconds 120"
    Write-Output "No scheduled task was registered."
    exit 0
}

$action = New-ScheduledTaskAction -Execute "uv" -Argument "run python -m operations.startup --ticks 0 --interval-seconds 120" -WorkingDirectory (Get-Location)
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "CYVORA Supervisor" -Action $action -Trigger $trigger -Settings $settings -Description "CYVORA paper or read-only supervisor. Live trading is not enabled."
Write-Output "CYVORA_SERVICE_INSTALLED"
exit 0
