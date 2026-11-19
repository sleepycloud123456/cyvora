# Run the local supervisor for a bounded number of ticks.
# The default is one tick and does not call GMGN. -IncludeRadar opts into one read-only cycle.
# -PaperTrader also enables that cycle and the autonomous paper trader. Live trading stays locked.
param(
    [int]$Ticks = 1,
    [switch]$IncludeRadar,
    [switch]$PaperTrader
)

$ErrorActionPreference = "Stop"
if ($Ticks -lt 0) {
    Write-Output "CYVORA_SUPERVISOR_FAIL reason=ticks"
    exit 2
}
Set-Location (Split-Path -Parent $PSScriptRoot)
$arguments = @("run", "python", "-m", "operations.startup", "--ticks", "$Ticks")
if ($IncludeRadar) {
    $arguments += "--include-radar"
}
if ($PaperTrader) {
    $arguments += "--paper-trader"
}
& uv @arguments
exit $LASTEXITCODE
