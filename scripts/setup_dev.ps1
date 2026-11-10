# Create the locked Phase 1 virtual environment.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

& uv sync --frozen --all-groups
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& uv run python -c "import sys; print(sys.executable); print(sys.version)"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Output "Virtual environment ready at $Root\.venv"
