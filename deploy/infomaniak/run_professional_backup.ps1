# Daily professional backup: Mongo + all files -> encrypt -> Infomaniak S3
# Requires: backend/.env.backup with BACKUP_ENCRYPTION_PASSPHRASE (+ BACKUP_S3_*)
#
# IMPORTANT: native Python stderr must NOT trip $ErrorActionPreference=Stop.
# We run Python via Start-Process and only trust $LASTEXITCODE / ExitCode.

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Backend = Join-Path $Root "backend"
$BackupDir = Join-Path $Backend "backups"
$EnvFile = Join-Path $Backend ".env.backup"

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

function Import-DotEnv($path) {
  if (-not (Test-Path $path)) { return }
  Get-Content $path -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { return }
    $i = $line.IndexOf("=")
    $k = $line.Substring(0, $i).Trim()
    $v = $line.Substring($i + 1).Trim().Trim('"').Trim("'")
    if ($k -and $v) { Set-Item -Path "Env:$k" -Value $v }
  }
}

function Write-BackupLog([string]$Message) {
  $ts = Get-Date -Format "o"
  Write-Output "[$ts] $Message"
}

function Invoke-NativeLogged {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter(Mandatory = $true)][string[]]$ArgumentList,
    [Parameter(Mandatory = $true)][string]$WorkingDirectory,
    [Parameter(Mandatory = $true)][string]$Label
  )
  # Capture stdout/stderr to durable logs under backups\ so failures remain diagnosable.
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $outFile = Join-Path $BackupDir ("backup_python_{0}_out.log" -f $stamp)
  $errFile = Join-Path $BackupDir ("backup_python_{0}_err.log" -f $stamp)
  try {
    $p = Start-Process -FilePath $FilePath `
      -ArgumentList $ArgumentList `
      -WorkingDirectory $WorkingDirectory `
      -NoNewWindow `
      -Wait `
      -PassThru `
      -RedirectStandardOutput $outFile `
      -RedirectStandardError $errFile

    if (Test-Path $outFile) {
      Get-Content -Path $outFile -ErrorAction SilentlyContinue | ForEach-Object { Write-Output $_ }
    }
    if (Test-Path $errFile) {
      Get-Content -Path $errFile -ErrorAction SilentlyContinue | ForEach-Object { Write-Output "[stderr] $_" }
    }

    $code = $p.ExitCode
    if ($null -eq $code) { $code = -1 }
    if ($code -ne 0) {
      throw "$Label failed with exit code $code (see $outFile / $errFile)"
    }
    return $code
  } catch {
    # Keep logs on failure; do not delete them here.
    throw
  }
}

if (-not (Test-Path $EnvFile)) {
  throw "Missing $EnvFile - copy deploy/infomaniak/env.backup.example and set BACKUP_ENCRYPTION_PASSPHRASE (+ S3)"
}
Import-DotEnv $EnvFile

if (-not $env:BACKUP_ENCRYPTION_PASSPHRASE -or $env:BACKUP_ENCRYPTION_PASSPHRASE -like "CHANGEZ*") {
  throw "Set a real BACKUP_ENCRYPTION_PASSPHRASE in backend/.env.backup"
}

# Upload Infomaniak obligatoire pour considérer la sauvegarde réussie
$requireRemote = $true
if ($env:BACKUP_REQUIRE_REMOTE) {
  $requireRemote = @("1", "true", "yes", "on") -contains $env:BACKUP_REQUIRE_REMOTE.Trim().ToLower()
}
$env:BACKUP_REQUIRE_REMOTE = if ($requireRemote) { "true" } else { "false" }

Push-Location $Root
$exitCode = 1
try {
  Write-BackupLog "Fetching Railway variables..."
  # railway CLI: capture as text without Stop on stderr noise
  $prevEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $appJson = & railway variables -s prevoyance-frontend --json 2>&1 | Out-String
  $mongoJson = & railway variables -s MongoDB --json 2>&1 | Out-String
  $ErrorActionPreference = $prevEap

  try {
    $appVars = $appJson | ConvertFrom-Json
    $mongoVars = $mongoJson | ConvertFrom-Json
  } catch {
    throw "Impossible de lire les variables Railway (CLI non connecté ou JSON invalide). Détail: $($_.Exception.Message)"
  }

  $mongoUrl = [string]$mongoVars.MONGO_PUBLIC_URL
  if (-not $mongoUrl) { $mongoUrl = [string]$mongoVars.MONGO_URL }
  if (-not $mongoUrl) { throw "MONGO_PUBLIC_URL / MONGO_URL missing on Railway MongoDB service" }

  $env:MONGO_URL = $mongoUrl
  $env:DB_NAME = if ($appVars.DB_NAME) { [string]$appVars.DB_NAME } else { "prevoyancecrm" }
  $env:BACKUP_DIR = $BackupDir
  $env:PYTHONUNBUFFERED = "1"
  if (-not $env:BACKUP_STRICT) { $env:BACKUP_STRICT = "true" }
  if (-not $env:BACKUP_MAX_FAIL_RATIO) { $env:BACKUP_MAX_FAIL_RATIO = "0" }
  # Prune off par défaut. Suppression seulement si BACKUP_ALLOW_PRUNE est explicite.
  $allowPrune = @("1", "true", "yes", "on") -contains (("" + $env:BACKUP_ALLOW_PRUNE).Trim().ToLower())
  if (-not $allowPrune) {
    $env:BACKUP_NO_PRUNE = "true"
  }
  if (-not $env:BACKUP_RETENTION_COUNT) { $env:BACKUP_RETENTION_COUNT = "9999" }
  if (-not $env:BACKUP_RETENTION_REMOTE) { $env:BACKUP_RETENTION_REMOTE = "9999" }
  if (-not $env:BACKUP_RETENTION_LOCAL) { $env:BACKUP_RETENTION_LOCAL = "9999" }

  # Lecture des documents: object_storage exige S3_* (distinct de BACKUP_S3_* pour l'upload).
  # Sans S3_*, l'export fichiers échoue à 100% avec « S3 non configuré ».
  foreach ($k in @(
      "S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY",
      "S3_BUCKET", "S3_REGION", "S3_FORCE_PATH_STYLE"
    )) {
    if (-not (Get-Item -Path "Env:$k" -ErrorAction SilentlyContinue).Value -and $appVars.$k) {
      Set-Item -Path "Env:$k" -Value ([string]$appVars.$k)
    }
  }
  # Fallback: réutiliser BACKUP_S3_* si S3_* encore absents (même bucket Infomaniak).
  $map = @{
    "S3_ENDPOINT_URL" = "BACKUP_S3_ENDPOINT_URL"
    "S3_ACCESS_KEY" = "BACKUP_S3_ACCESS_KEY"
    "S3_SECRET_KEY" = "BACKUP_S3_SECRET_KEY"
    "S3_BUCKET" = "BACKUP_S3_BUCKET"
    "S3_REGION" = "BACKUP_S3_REGION"
    "S3_FORCE_PATH_STYLE" = "BACKUP_S3_FORCE_PATH_STYLE"
  }
  foreach ($s3Key in $map.Keys) {
    $backupKey = $map[$s3Key]
    $s3Val = (Get-Item -Path "Env:$s3Key" -ErrorAction SilentlyContinue).Value
    $bVal = (Get-Item -Path "Env:$backupKey" -ErrorAction SilentlyContinue).Value
    if (-not $s3Val -and $bVal) {
      Set-Item -Path "Env:$s3Key" -Value $bVal
    }
  }
  if (-not $env:S3_ENDPOINT_URL -or -not $env:S3_ACCESS_KEY -or -not $env:S3_SECRET_KEY -or -not $env:S3_BUCKET) {
    throw "S3_* manquants pour lire les documents (Railway S3_* ou BACKUP_S3_* dans .env.backup)."
  }
  Write-BackupLog "S3 docs ready bucket=$($env:S3_BUCKET) backup_bucket=$($env:BACKUP_S3_BUCKET) prefix=$($env:BACKUP_S3_PREFIX)"

  # BACKUP_NO_PRUNE=true : ne supprimer aucune archive locale/distante (demande explicite).
  if (@("1", "true", "yes", "on") -contains (($env:BACKUP_NO_PRUNE | ForEach-Object { "$_".Trim().ToLower() }) )) {
    $env:BACKUP_RETENTION_COUNT = "9999"
    $env:BACKUP_RETENTION_REMOTE = "9999"
    $env:BACKUP_RETENTION_LOCAL = "9999"
    Write-BackupLog "BACKUP_NO_PRUNE=true — rétention désactivée pour cette exécution"
  }

  Write-BackupLog "Professional backup starting (DB=$($env:DB_NAME), require_remote=$($env:BACKUP_REQUIRE_REMOTE))..."
  $py = (Get-Command python -ErrorAction Stop).Source
  $null = Invoke-NativeLogged -FilePath $py -ArgumentList @("scripts\backup_professional.py") -WorkingDirectory $Backend -Label "backup_professional.py"

  Write-BackupLog "PROFESSIONAL_BACKUP_OK"
  $exitCode = 0
} catch {
  Write-BackupLog "PROFESSIONAL_BACKUP_FAILED: $($_.Exception.Message)"
  Write-Output $_
  $exitCode = 1
} finally {
  Pop-Location
  Remove-Item Env:MONGO_URL -ErrorAction SilentlyContinue
}

exit $exitCode
