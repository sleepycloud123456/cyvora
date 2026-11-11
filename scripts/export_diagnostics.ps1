# Write one redacted diagnostic file. The script prints the file name, not the directory.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
& uv run python -m operations.diagnostics
exit $LASTEXITCODE
