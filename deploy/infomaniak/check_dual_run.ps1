# Smoke dual-run : health Railway + Infomaniak (si URL définie)

$ErrorActionPreference = "Continue"
$Backend = Resolve-Path (Join-Path $PSScriptRoot "..\..\backend")
$EnvFile = Join-Path $Backend ".env.infomaniak"

if (Test-Path $EnvFile) {
  Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { return }
    $i = $line.IndexOf("=")
    $k = $line.Substring(0, $i).Trim()
    $v = $line.Substring($i + 1).Trim().Trim('"').Trim("'")
    if ($k) { Set-Item -Path "Env:$k" -Value $v }
  }
}

$railway = if ($env:RAILWAY_APP_URL) { $env:RAILWAY_APP_URL } else { "https://prevoyance-frontend-production.up.railway.app" }
$inf = if ($env:INFOMANIAK_APP_URL) { $env:INFOMANIAK_APP_URL } else { $env:PUBLIC_APP_URL }

function Test-Health($name, $url) {
  if (-not $url) { Write-Host "[SKIP] $name URL vide"; return $false }
  try {
    $r = Invoke-WebRequest -Uri ($url.TrimEnd('/') + "/health") -UseBasicParsing -TimeoutSec 30
    Write-Host "[OK] $name $($r.StatusCode) $($r.Content)"
    return $true
  } catch {
    Write-Host "[FAIL] $name $_"
    return $false
  }
}

$okR = Test-Health "Railway" $railway
$okI = Test-Health "Infomaniak" $inf

Write-Host "Railway production retained: DO NOT DELETE"
if ($okR -and $okI) { Write-Host "DUAL_RUN_OK"; exit 0 }
if ($okR -and -not $inf) { Write-Host "DUAL_RUN_WAITING_JELASTIC"; exit 2 }
exit 1
