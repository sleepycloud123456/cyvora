# Create one local PostgreSQL dump. The script does not print the database URL.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
& uv run python -m operations.backup
exit $LASTEXITCODE
