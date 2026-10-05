# Charge backend/.env.infomaniak + secrets Mongo Railway, puis alembic + migrate_mongo_to_postgres

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Backend = Join-Path $Root "backend"
$EnvFile = Join-Path $Backend ".env.infomaniak"

function Import-DotEnv($path) {
  if (-not (Test-Path $path)) { throw "Manquant: $path - copiez deploy/infomaniak/env.example" }
  Get-Content $path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { return }
    $i = $line.IndexOf("=")
    $k = $line.Substring(0, $i).Trim()
    $v = $line.Substring($i + 1).Trim().Trim('"').Trim("'")
    if ($k) { Set-Item -Path "Env:$k" -Value $v }
  }
}

Import-DotEnv $EnvFile
if (-not $env:DATABASE_URL) { throw "DATABASE_URL manquant dans .env.infomaniak" }

# Source Mongo = Railway prod
Push-Location $Root
try {
  $vars = (railway variables -s prevoyance-frontend --json | Out-String) | ConvertFrom-Json
  $env:MONGO_URL = [string]$vars.MONGO_URL
  $env:DB_NAME = [string]$vars.DB_NAME
  if (-not $env:MONGO_URL) { throw "MONGO_URL Railway manquant" }
} finally {
  Pop-Location
}

Push-Location $Backend
try {
  Write-Host "alembic upgrade head..."
  python -m alembic upgrade head
  if ($LASTEXITCODE -ne 0) { throw "alembic failed" }

  Write-Host "migrate_mongo_to_postgres..."
  python scripts\migrate_mongo_to_postgres.py
  if ($LASTEXITCODE -ne 0) { throw "migrate_mongo_to_postgres failed" }

  Write-Host "compare_counts..."
  python scripts\compare_mongo_postgres_counts.py
  if ($LASTEXITCODE -ne 0) { throw "count mismatch" }
  Write-Host "PG_MIGRATE_OK"
} finally {
  Pop-Location
  Remove-Item Env:MONGO_URL -ErrorAction SilentlyContinue
}
