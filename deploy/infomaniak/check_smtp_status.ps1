# Check SMTP-related Railway variables (names only, no secret values).

$ErrorActionPreference = "Stop"
Push-Location (Resolve-Path (Join-Path $PSScriptRoot "..\.."))
try {
  $vars = railway variables -s prevoyance-frontend --json 2>&1 | Out-String | ConvertFrom-Json
  $required = @("SMTP_HOST", "SMTP_PORT", "SMTP_TLS", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "PUBLIC_APP_URL")
  $missing = @()
  foreach ($k in $required) {
    $ok = [bool]$vars.$k
    Write-Host ("{0}={1}" -f $k, $(if ($ok) { "SET" } else { "MISSING" }))
    if (-not $ok) { $missing += $k }
  }
  if ($missing.Count -eq 0) {
    Write-Host "SMTP_READY"
    exit 0
  }
  Write-Host ("SMTP_INCOMPLETE missing=" + ($missing -join ","))
  Write-Host "Set the missing keys in Railway Variables (Infomaniak mailbox), then redeploy if needed."
  exit 1
} finally {
  Pop-Location
}
