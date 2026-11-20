# Restore one local dump into a scratch database.
# -Swap renames the live database only after the scratch check succeeds.
# The script does not print the database URL and does not register a task.
param(
    [Parameter(Mandatory = $true)][string]$File,
    [switch]$Swap
)

$ErrorActionPreference = "Stop"
if ($File -notmatch '^cyvora-\d{8}T\d{6}Z\.dump$') {
    Write-Output "CYVORA_RESTORE_FAIL reason=file"
    exit 2
}
Set-Location (Split-Path -Parent $PSScriptRoot)
$arguments = @("run", "python", "-m", "operations.backup", "restore", "--file", $File)
if ($Swap) {
    Write-Output "CYVORA_RESTORE_SWAP The live database will be renamed after the scratch check."
    $arguments += @("--swap", "--confirm", "SWAP")
}
& uv @arguments
exit $LASTEXITCODE
