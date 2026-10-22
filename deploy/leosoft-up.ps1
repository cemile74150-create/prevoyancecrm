# Déploie LeoSoft uniquement depuis cette branche, jamais depuis une ancienne copie.
param(
  [switch]$AutoriserDeploiement
)
$ErrorActionPreference = "Stop"
if (-not $AutoriserDeploiement) {
  throw "Refus : aucun déploiement sans accord explicite. Lancez d'abord deploy\verifier-avant-deploiement.ps1. Ajoutez -AutoriserDeploiement seulement après cet accord."
}
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

& (Join-Path $PSScriptRoot "verifier-avant-deploiement.ps1")
if ($LASTEXITCODE -ne 0) {
  throw "Refus : le contrôle pré-déploiement a échoué."
}

$head = git rev-parse HEAD
$remoteMain = (git ls-remote origin refs/heads/main | Select-Object -First 1).Split("`t")[0]
if (-not $remoteMain) {
  throw "Refus : GitHub main est illisible. Déploiement annulé."
}
git merge-base --is-ancestor $remoteMain HEAD
if ($LASTEXITCODE -ne 0) {
  throw "Refus : cette copie ne descend pas de GitHub main ($remoteMain). Déploiement annulé."
}

$required = @(
  ".leosoft-release-source",
  "frontend\src\analyse-prevoyance\components\AnalyseWizardNav.tsx",
  "frontend\src\analyse-prevoyance\lib\analyseWizard.ts",
  "frontend\src\analyse-prevoyance\lib\planificationSaisie.ts",
  "backend\analyse_prevoyance_engine\pdf\renderPrintableReportHtml.ts"
)
foreach ($rel in $required) {
  if (-not (Test-Path (Join-Path $Root $rel))) {
    throw "Refus : fichier manquant ($rel). Ce n'est pas la version de référence."
  }
}

$wizard = Get-Content (Join-Path $Root "frontend\src\analyse-prevoyance\lib\analyseWizard.ts") -Raw
foreach ($step in @("client","assure2","avs","lpp","piliers3","libresPassages","retraits","hypotheses")) {
  if ($wizard -notmatch [regex]::Escape("id: `"$step`"")) {
    throw "Refus : l'étape $step n'est plus dans le parcours. Déploiement annulé."
  }
}

$pdf = Get-Content (Join-Path $Root "backend\analyse_prevoyance_engine\pdf\renderPrintableReportHtml.ts") -Raw
if ($pdf -notmatch "COMPARATIF DES RENTES") {
  throw "Refus : le titre COMPARATIF DES RENTES a disparu. Déploiement annulé."
}

$forbidden = @("prevoyancecrm-prod", "leosoft-planification-latest", "leosoft-planification-ui")
foreach ($name in $forbidden) {
  if ($Root -match [regex]::Escape($name)) {
    throw "Refus : $name est une ancienne copie. Déploiement annulé."
  }
}

Write-Output "Version autorisée : $head"
$railway = "C:\Users\offic\AppData\Roaming\npm\node_modules\@railway\cli\bin\railway.js"
node $railway up --project 3a8f686b-b264-4b22-8982-f29001c7802c --service prevoyance-frontend --environment production --yes --ci --message "Deploie la branche de reference, pas une ancienne copie"
