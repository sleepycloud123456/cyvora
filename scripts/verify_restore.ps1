# Restore the newest local dump into a scratch database and check it.
# The live database is not renamed. Nothing is scheduled.
param(
    [string]$File = ""
)

$ErrorActionPreference = "Stop"
if ($File -ne "" -and $File -notmatch '^cyvora-\d{8}T\d{6}Z\.dump$') {
    Write-Output "CYVORA_RESTORE_FAIL reason=file"
    exit 2
}
Set-Location (Split-Path -Parent $PSScriptRoot)
$arguments = @("run", "python", "-m", "operations.backup", "drill")
if ($File -ne "") {
    $arguments += @("--file", $File)
}
& uv @arguments
exit $LASTEXITCODE
