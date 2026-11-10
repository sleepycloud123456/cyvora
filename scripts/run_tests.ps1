# Run the Phase 1 quality checks and the desktop smoke launch.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-Uv {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$UvArgs)
    & uv @UvArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Invoke-Uv run ruff check .
Invoke-Uv run ruff format --check .
Invoke-Uv run mypy
Invoke-Uv run pytest
Invoke-Uv run python -m apps.desktop.main --smoke
Write-Output "Phase 1 checks finished."
