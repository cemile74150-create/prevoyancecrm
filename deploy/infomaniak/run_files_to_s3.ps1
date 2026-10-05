# Migre les fichiers vers S3 Infomaniak (après PG migrate)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Backend = Join-Path $Root "backend"
$EnvFile = Join-Path $Backend ".env.infomaniak"

function Import-DotEnv($path) {
  if (-not (Test-Path $path)) { throw "Manquant: $path" }
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

Push-Location $Backend
try {
  python scripts\migrate_files_to_s3.py
  if ($LASTEXITCODE -ne 0) { throw "migrate_files_to_s3 failed" }
  $env:SAMPLE_PER_TABLE = "10"
  python scripts\verify_migration.py
  if ($LASTEXITCODE -ne 0) { throw "verify_migration failed" }
  Write-Host "FILES_TO_S3_OK"
} finally {
  Pop-Location
}
