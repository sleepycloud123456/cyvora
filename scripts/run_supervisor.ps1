# Run the local supervisor for a bounded number of ticks.
# The default is one tick and does not call GMGN. -IncludeRadar opts into one read-only cycle.
param(
    [int]$Ticks = 1,
    [switch]$IncludeRadar
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
& uv @arguments
exit $LASTEXITCODE
