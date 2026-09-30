# Wrapper for Task Scheduler: UTF-8 logging + clean exit codes.
# Invokes run_professional_backup.ps1 in-process (no nested -File with spaces).

$ErrorActionPreference = "Continue"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Script = Join-Path $PSScriptRoot "run_professional_backup.ps1"
$LogDir = Join-Path $Root "backend\backups"
$LogFile = Join-Path $LogDir "backup_task.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Append-Log([string]$line) {
  $ts = Get-Date -Format "o"
  Add-Content -Path $LogFile -Value "[$ts] $line" -Encoding utf8
}

Append-Log "======= START PrevoyanceCRM daily backup ======="
$exitCode = 1
try {
  if (-not (Test-Path -LiteralPath $Script)) {
    throw "Missing script: $Script"
  }
  Set-Location -LiteralPath $Root

  # Capture output while preserving exit code from child script
  $transcript = Join-Path $env:TEMP ("crm_backup_wrap_{0}.log" -f [guid]::NewGuid().ToString("N"))
  try {
    & $Script *> $transcript
    $exitCode = [int]$LASTEXITCODE
    if ($null -eq $LASTEXITCODE) { $exitCode = 1 }
  } catch {
    Append-Log "SCRIPT_EXCEPTION: $($_.Exception.Message)"
    $exitCode = 1
  }

  if (Test-Path -LiteralPath $transcript) {
    Get-Content -LiteralPath $transcript -ErrorAction SilentlyContinue | ForEach-Object { Append-Log $_ }
    Remove-Item -LiteralPath $transcript -Force -ErrorAction SilentlyContinue
  }
} catch {
  Append-Log "WRAPPER_EXCEPTION: $($_.Exception.Message)"
  $exitCode = 1
}

Append-Log "EXIT=$exitCode"
Append-Log "======= END ======="
exit $exitCode
