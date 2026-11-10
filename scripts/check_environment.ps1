# Inspect the local toolchain without printing secrets.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Show-Check {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    Write-Output "=== $Name ==="
    try {
        & $Command
        if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
            Write-Output "EXIT $LASTEXITCODE"
        }
    }
    catch {
        Write-Output "FAILED: $($_.Exception.Message)"
    }
}

Show-Check "Windows" {
    $os = Get-CimInstance Win32_OperatingSystem
    Write-Output "$($os.Caption) $($os.Version) $($os.OSArchitecture) build $($os.BuildNumber)"
    Write-Output "PROCESSOR_ARCHITECTURE=$env:PROCESSOR_ARCHITECTURE"
}

Show-Check "Python launcher" { py -0p }
Show-Check "uv" { uv --version }
Show-Check "uv Python 3.13" { uv python find 3.13 }
Show-Check "Git" { git --version }
Show-Check "Node" { node --version }
Show-Check "npm" { npm --version }

Show-Check "psql" {
    if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
        Write-Output "MISSING: psql is not on PATH"
        return
    }
    psql --version
}

Show-Check "Docker" {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Output "MISSING: docker is not on PATH"
        return
    }
    docker --version
    docker compose version
}

Show-Check "PostgreSQL services" {
    $services = Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "postgres|pgsql" -or $_.DisplayName -match "postgres|pgsql" }
    if (-not $services) {
        Write-Output "NONE"
        return
    }
    $services | Format-Table Name, Status, DisplayName -AutoSize | Out-String
}

Write-Output "Environment variable values were not printed."
