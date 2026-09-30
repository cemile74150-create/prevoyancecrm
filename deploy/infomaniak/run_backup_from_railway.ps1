# Full CRM backup from Railway Mongo (public TCP proxy) + fichiers S3.
# Output: backend/backups/ — never commit.

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Backend = Join-Path $Root "backend"
$BackupDir = Join-Path $Backend "backups"

Write-Host "Root=$Root"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

Push-Location $Root
try {
  $appVars = railway variables -s prevoyance-frontend --json 2>&1 | Out-String | ConvertFrom-Json
  $mongoVars = railway variables -s MongoDB --json 2>&1 | Out-String | ConvertFrom-Json

  $mongoUrl = [string]$mongoVars.MONGO_PUBLIC_URL
  if (-not $mongoUrl) { $mongoUrl = [string]$mongoVars.MONGO_URL }
  if (-not $mongoUrl) { throw "MONGO_PUBLIC_URL missing on MongoDB service" }

  $dbName = [string]$appVars.DB_NAME
  if (-not $dbName) { $dbName = "prevoyancecrm" }

  $env:MONGO_URL = $mongoUrl
  $env:DB_NAME = $dbName
  $env:BACKUP_DIR = $BackupDir
  $env:PYTHONUNBUFFERED = "1"

  Write-Host "Starting full backup DB=$($env:DB_NAME) via Mongo public proxy"
  Push-Location $Backend
  try {
    python scripts\backup_full.py
    if ($LASTEXITCODE -ne 0) { throw "backup_full.py exit=$LASTEXITCODE" }
  } finally {
    Pop-Location
  }

  $latest = Get-ChildItem $BackupDir -Directory -Filter "backups_full_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if (-not $latest) { throw "No backup directory created" }

  $manifest = Join-Path $latest.FullName "manifest.csv"
  if (Test-Path $manifest) {
    $rows = Import-Csv $manifest
    $ok = @($rows | Where-Object { $_.ok -eq "True" -or $_.ok -eq "true" }).Count
    $fail = @($rows | Where-Object { $_.ok -ne "True" -and $_.ok -ne "true" }).Count
    Write-Host "BACKUP_DIR=$($latest.FullName)"
    Write-Host "FILES_OK=$ok FILES_FAIL=$fail"
    $total = $ok + $fail
    if ($total -gt 0 -and ($fail / $total) -gt 0.05) {
      throw "Backup incomplete: $fail/$total files failed (>5%)"
    }
  }
  Write-Host "BACKUP_OK"
} finally {
  Pop-Location
  Remove-Item Env:MONGO_URL -ErrorAction SilentlyContinue
}
