# Deploie LeoSoft uniquement depuis cette branche, jamais depuis une ancienne copie.
# Archivage code (local C:\LeoSoft\Versions + S3 leosoft-versions/) :
#   - UNIQUEMENT avec -AutoriserDeploiement (pas au simple demarrage local)
#   - avant railway up (phase before-deploy, --ensure)
#   - apres railway up reussi (phase after-deploy, --ensure + ID si fourni)
# Ne restaure jamais Mongo. Ne supprime aucune archive. Pas d'ecrasement S3.
param(
  [switch]$AutoriserDeploiement,
  [string]$RailwayDeploymentId = ""
)
$ErrorActionPreference = "Stop"
if (-not $AutoriserDeploiement) {
  throw "Refus : aucun deploiement sans accord explicite. Lancez d'abord deploy\verifier-avant-deploiement.ps1. Ajoutez -AutoriserDeploiement seulement apres cet accord."
}
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

function Invoke-LeoSoftCodeArchive {
  param(
    [Parameter(Mandatory = $true)][ValidateSet("before-deploy", "after-deploy")][string]$Phase,
    [string]$DeploymentId = ""
  )
  $archiver = Join-Path $PSScriptRoot "archiver-version-code.ps1"
  if (-not (Test-Path $archiver)) {
    throw "Refus : archiver-version-code.ps1 introuvable - deploiement annule (archivage obligatoire)."
  }
  Write-Output "=== Archivage code ($Phase) -> C:\LeoSoft\Versions + S3 leosoft-versions/ ==="
  $archiveArgs = @{
    UploadS3            = $true
    AutoriserUploadS3   = $true
    Ensure              = $true
    AllowS3WithoutLocal = $true
    Phase               = $Phase
  }
  if ($DeploymentId) {
    $archiveArgs["RailwayDeploymentId"] = $DeploymentId
  }
  & $archiver @archiveArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Echec archivage code ($Phase). Deploiement interrompu - ni local ni S3 ne doivent rester incoherents sans signal d'erreur."
  }
}

& (Join-Path $PSScriptRoot "verifier-avant-deploiement.ps1")
if ($LASTEXITCODE -ne 0) {
  throw "Refus : le controle pre-deploiement a echoue."
}

$branch = git rev-parse --abbrev-ref HEAD
$head = git rev-parse HEAD
$remoteMain = (git ls-remote origin refs/heads/main | Select-Object -First 1).Split("`t")[0]
if (-not $remoteMain) {
  throw "Refus : GitHub main est illisible. Deploiement annule."
}
git merge-base --is-ancestor $remoteMain HEAD
if ($LASTEXITCODE -ne 0) {
  throw "Refus : cette copie ne descend pas de GitHub main ($remoteMain). Deploiement annule."
}
if ($branch -ne "main" -or $head -ne $remoteMain) {
  Write-Output "INFO : deploiement depuis '$branch' (descend de GitHub main). Flux hebdomadaire recommande : merger dans main."
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
    throw "Refus : fichier manquant ($rel). Ce n'est pas la version de reference."
  }
}

$wizard = Get-Content (Join-Path $Root "frontend\src\analyse-prevoyance\lib\analyseWizard.ts") -Raw
foreach ($step in @("client","assure2","avs","lpp","piliers3","libresPassages","retraits","hypotheses")) {
  if ($wizard -notmatch [regex]::Escape("id: `"$step`"")) {
    throw "Refus : l'etape $step n'est plus dans le parcours. Deploiement annule."
  }
}

$pdf = Get-Content (Join-Path $Root "backend\analyse_prevoyance_engine\pdf\renderPrintableReportHtml.ts") -Raw
if ($pdf -notmatch "COMPARATIF DES RENTES") {
  throw "Refus : le titre COMPARATIF DES RENTES a disparu. Deploiement annule."
}

$forbidden = @("prevoyancecrm-prod", "leosoft-planification-latest", "leosoft-planification-ui")
foreach ($name in $forbidden) {
  if ($Root -match [regex]::Escape($name)) {
    throw "Refus : $name est une ancienne copie. Deploiement annule."
  }
}

Write-Output "Version autorisee : $head"

# GO Cemile (securite versions) : archive AVANT mise a jour prod
Invoke-LeoSoftCodeArchive -Phase "before-deploy"

$railway = "C:\Users\offic\AppData\Roaming\npm\node_modules\@railway\cli\bin\railway.js"
node $railway up --project 3a8f686b-b264-4b22-8982-f29001c7802c --service prevoyance-frontend --environment production --yes --ci --message "Deploie la branche de reference, pas une ancienne copie"
if ($LASTEXITCODE -ne 0) {
  throw "Echec railway up (code $LASTEXITCODE). Archive before-deploy deja en place - pas de after-deploy."
}

# Apres deploiement reussi : meme version_id (date+SHA) -> --ensure (pas d'ecrasement tar)
# Consigne l'ID Railway si fourni ; sinon noter manuellement via railway deployment list
Invoke-LeoSoftCodeArchive -Phase "after-deploy" -DeploymentId $RailwayDeploymentId

Write-Output "Deploiement + archivage termines."
Write-Output "Rappel : rollback Mongo / documents = operation SEPAREE (jamais automatique)."
if (-not $RailwayDeploymentId) {
  Write-Output "Astuce : relancer l'archivage after-deploy avec -RailwayDeploymentId une fois l'ID connu :"
  Write-Output "  .\deploy\archiver-version-code.ps1 -UploadS3 -AutoriserUploadS3 -Ensure -Phase after-deploy -RailwayDeploymentId <id>"
}
