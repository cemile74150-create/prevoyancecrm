# Contrôle avant déploiement. Ce script n'appelle jamais Railway.
param(
  [string]$FichierObligatoireSupplementaire = "",
  [switch]$SansTests
)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

function Fail([string]$Message) {
  [Console]::Error.WriteLine($Message)
  exit 1
}

if ((Split-Path $Root -Leaf) -ne "leosoft-saisie-preneur") {
  Fail "Refus : le dossier ouvert n'est pas leosoft-saisie-preneur."
}

if ($FichierObligatoireSupplementaire -and -not (Test-Path (Join-Path $Root $FichierObligatoireSupplementaire))) {
  Fail "Refus : fichier obligatoire absent ($FichierObligatoireSupplementaire)."
}

$marker = Join-Path $Root ".leosoft-release-source"
if (-not (Test-Path $marker)) {
  Fail "Refus : .leosoft-release-source est absent. Cette copie n'est pas la source de référence."
}
$markerText = Get-Content $marker -Raw
if ($markerText -notmatch "leosoft-saisie-preneur") {
  Fail "Refus : le marqueur de source ne désigne pas leosoft-saisie-preneur."
}

$wizardPath = Join-Path $Root "frontend\src\analyse-prevoyance\lib\analyseWizard.ts"
if (-not (Test-Path $wizardPath)) {
  Fail "Refus : parcours d'analyse introuvable."
}
$wizard = Get-Content $wizardPath -Raw
foreach ($step in @("client", "assure2", "avs", "lpp", "piliers3", "libresPassages", "retraits", "hypotheses")) {
  if ($wizard -notmatch [regex]::Escape("id: `"$step`"")) {
    Fail "Refus : l'étape $step n'est plus dans le parcours."
  }
}

$pdfPath = Join-Path $Root "backend\analyse_prevoyance_engine\pdf\renderPrintableReportHtml.ts"
if (-not (Test-Path $pdfPath)) {
  Fail "Refus : le rapport PDF est introuvable."
}
$pdf = Get-Content $pdfPath -Raw
if ($pdf -notmatch "COMPARATIF DES RENTES") {
  Fail "Refus : le titre COMPARATIF DES RENTES a disparu."
}

$branch = git rev-parse --abbrev-ref HEAD
if ($branch -eq "HEAD") {
  Fail "Refus : HEAD détaché. Le déploiement exige une branche nommée."
}
$head = git rev-parse HEAD
$remoteLine = git ls-remote origin refs/heads/main | Select-Object -First 1
$remoteMain = ($remoteLine -split "\s+")[0]
if (-not $remoteMain) {
  Fail "Refus : impossible de lire GitHub main."
}
git merge-base --is-ancestor $remoteMain HEAD
if ($LASTEXITCODE -ne 0) {
  Fail "Refus : $head ne descend pas de GitHub main $remoteMain."
}

$tracked = git ls-files
$secrets = $tracked | Where-Object {
  $_ -match '(^|/)\.env($|\.)' -and $_ -notmatch '\.env\.example$' -or
  $_ -match 'conflicted' -or
  $_ -match '\.pem$' -or
  $_ -match 'credentials\.json$'
}
if ($secrets) {
  Fail ("Refus : fichiers sensibles suivis par Git : " + ($secrets -join ", "))
}

function Test-PlaywrightChromiumPresent {
  # Docker/CI : PLAYWRIGHT_BROWSERS_PATH=/ms-playwright (installé dans le Dockerfile).
  # Local : %LOCALAPPDATA%\ms-playwright après `npx playwright install chromium`.
  $roots = @()
  if ($env:PLAYWRIGHT_BROWSERS_PATH) { $roots += $env:PLAYWRIGHT_BROWSERS_PATH }
  if ($env:LOCALAPPDATA) { $roots += (Join-Path $env:LOCALAPPDATA "ms-playwright") }
  if (Test-Path "/ms-playwright") { $roots += "/ms-playwright" }
  foreach ($root in $roots) {
    if (-not (Test-Path $root)) { continue }
    $hit = Get-ChildItem -Path $root -Recurse -Filter "chrome-headless-shell.exe" -ErrorAction SilentlyContinue |
      Select-Object -First 1
    if (-not $hit) {
      $hit = Get-ChildItem -Path $root -Recurse -Filter "chrome-headless-shell" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    }
    if (-not $hit) {
      $hit = Get-ChildItem -Path $root -Recurse -Filter "chrome.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    }
    if ($hit) { return $true }
  }
  return $false
}

if (-not $SansTests) {
  $engine = Join-Path $Root "backend\analyse_prevoyance_engine"
  $tsx = Join-Path $engine "node_modules\tsx"
  if (-not (Test-Path $tsx)) {
    Fail "Refus : tsx n'est pas installé dans le moteur d'analyse. Les tests n'ont pas pu tourner."
  }
  $tests = @(Get-ChildItem (Join-Path $engine "rules\*.test.ts") | ForEach-Object { $_.FullName })
  if (-not $tests) {
    Fail "Refus : aucun test du moteur d'analyse."
  }

  # Tests PDF (Playwright generatePdfBuffer) — exclus seulement si Chromium manque EN LOCAL.
  # Docker install Playwright (Dockerfile) : ces tests restent obligatoires.
  $pdfTestNames = @(
    "cinq-contrats-3p.test.ts",
    "pdf-route-hypotheses.test.ts"
  )
  $inCiOrDocker = (
    $env:CI -eq "true" -or
    $env:GITHUB_ACTIONS -eq "true" -or
    $env:RAILWAY_ENVIRONMENT -or
    (Test-Path "/ms-playwright") -or
    $env:FORCE_ANALYSE_PDF_TESTS -eq "1"
  )
  $playwrightOk = Test-PlaywrightChromiumPresent
  if (-not $playwrightOk) {
    if ($inCiOrDocker) {
      Fail "Refus : Chromium Playwright introuvable en CI/Docker. Exécutez `npx playwright install --with-deps chromium` (déjà dans le Dockerfile)."
    }
    Write-Output "ATTENTION : Chromium Playwright absent en local — exclusion temporaire des tests PDF :"
    foreach ($name in $pdfTestNames) { Write-Output "  - $name" }
    Write-Output "Les autres tests du moteur tournent. Pour tout exécuter localement : cd backend\analyse_prevoyance_engine ; npx playwright install chromium"
    $tests = @($tests | Where-Object {
      $leaf = Split-Path $_ -Leaf
      $pdfTestNames -notcontains $leaf
    })
  }

  Push-Location $engine
  try {
    if ($tests.Count -eq 0) {
      Fail "Refus : aucun test du moteur d'analyse à exécuter."
    }
    node --import tsx --test @tests
    if ($LASTEXITCODE -ne 0) {
      Fail "Refus : les tests du moteur d'analyse ont échoué."
    }
  } finally {
    Pop-Location
  }
}

Write-Output "Contrôle réussi."
Write-Output "Branche : $branch"
Write-Output "Commit local : $head"
Write-Output "GitHub main : $remoteMain"
Write-Output "Déploiement NON lancé. Un accord explicite reste obligatoire."
exit 0
