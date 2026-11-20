# Prepare a daily local backup task.
# The default path prints the plan and does not register anything.
# Re-run with -ConfirmInstall only after you authorize a persistent task on this PC.
param(
    [switch]$ConfirmInstall
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not $ConfirmInstall) {
    Write-Output "CYVORA_BACKUP_TASK_NOT_INSTALLED"
    Write-Output "Planned task name: CYVORA Backup"
    Write-Output "Planned command: uv run python -m operations.backup"
    Write-Output "No scheduled task was registered."
    exit 0
}

$action = New-ScheduledTaskAction -Execute "uv" -Argument "run python -m operations.backup" -WorkingDirectory (Get-Location)
$trigger = New-ScheduledTaskTrigger -Daily -At 3am
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "CYVORA Backup" -Action $action -Trigger $trigger -Settings $settings -Description "CYVORA local database dump. Live trading is not enabled."
Write-Output "CYVORA_BACKUP_TASK_INSTALLED"
exit 0
