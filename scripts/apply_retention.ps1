# Show the retention plan. Pass -Confirm to delete aged backups, logs, and radar cycles.
# Audit events and backtests are not deleted. Nothing is scheduled.
param(
    [switch]$Confirm
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not $Confirm) {
    & uv run python -m operations.retention
    exit $LASTEXITCODE
}
& uv run python -m operations.retention --apply --confirm DELETE
exit $LASTEXITCODE
