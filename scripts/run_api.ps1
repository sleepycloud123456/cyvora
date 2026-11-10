# Launch the loopback CYVORA API. The host comes from settings and must be loopback.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
& uv run cyvora-api
exit $LASTEXITCODE
