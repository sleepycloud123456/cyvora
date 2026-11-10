# Launch CYVORA Terminal on the native Windows desktop.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
& uv run cyvora-desktop
exit $LASTEXITCODE
