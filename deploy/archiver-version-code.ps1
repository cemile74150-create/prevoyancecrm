# Archive une version code LeoSoft (local et/ou Infomaniak).
# Ne déploie pas, ne touche pas Mongo, ne supprime aucune archive.
#
# Exemples :
#   .\deploy\archiver-version-code.ps1 -DryRun
#   .\deploy\archiver-version-code.ps1 -LocalOnly
#   .\deploy\archiver-version-code.ps1 -UploadS3 -AutoriserUploadS3
#   .\deploy\archiver-version-code.ps1 -UploadExisting -AutoriserUploadS3 -VersionId "2026-11-20_c81daf185154"
#   .\deploy\archiver-version-code.ps1 -UploadS3 -AutoriserUploadS3 -Ensure -Phase before-deploy
#   .\deploy\archiver-version-code.ps1 -LocalOnly -RailwayDeploymentId "848b1c5a-..."
param(
  [switch]$DryRun,
  [switch]$LocalOnly,
  [switch]$UploadS3,
  [switch]$UploadExisting,
  [switch]$Ensure,
  [switch]$AllowS3WithoutLocal,
  [switch]$AutoriserUploadS3,
  [switch]$SelfTest,
  [string]$Commit = "",
  [string]$VersionId = "",
  [string]$RailwayDeploymentId = "",
  [ValidateSet("", "before-deploy", "after-deploy", "manual")]
  [string]$Phase = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

if ((Split-Path $Root -Leaf) -ne "leosoft-saisie-preneur") {
  throw "Refus : le dossier ouvert n'est pas leosoft-saisie-preneur."
}
if (-not (Test-Path (Join-Path $Root ".leosoft-release-source"))) {
  throw "Refus : .leosoft-release-source absent."
}

$py = Join-Path $PSScriptRoot "archive_code_version.py"
if (-not (Test-Path $py)) {
  throw "Refus : deploy\archive_code_version.py introuvable."
}

$argsList = @($py)
if ($SelfTest) {
  $argsList += "--self-test"
} elseif ($UploadExisting) {
  if (-not $AutoriserUploadS3) {
    throw "Refus : upload S3 sans accord. Ajoutez -AutoriserUploadS3 seulement après GO explicite."
  }
  $argsList += "--upload-existing"
} elseif ($UploadS3) {
  if (-not $AutoriserUploadS3) {
    throw "Refus : upload S3 sans accord. Ajoutez -AutoriserUploadS3 seulement après GO explicite."
  }
  $argsList += "--upload-s3"
} elseif ($LocalOnly) {
  $argsList += "--local-only"
} else {
  # Défaut sûr
  $argsList += "--dry-run"
  $DryRun = $true
}

if ($Ensure) { $argsList += "--ensure" }
if ($AllowS3WithoutLocal) { $argsList += "--allow-s3-without-local" }
if ($Commit) { $argsList += @("--commit", $Commit) }
if ($VersionId) { $argsList += @("--version-id", $VersionId) }
if ($RailwayDeploymentId) { $argsList += @("--railway-deployment-id", $RailwayDeploymentId) }
if ($Phase) { $argsList += @("--phase", $Phase) }

$modeLabel = if ($SelfTest) { "self-test" } elseif ($UploadExisting) { "upload-existing" } elseif ($UploadS3) { "upload-s3" } elseif ($LocalOnly) { "local-only" } else { "dry-run" }
Write-Output "Racine : $Root"
Write-Output "Mode : $modeLabel"
python @argsList
if ($LASTEXITCODE -ne 0) {
  throw "Archivage échoué (code $LASTEXITCODE)."
}

if ($LocalOnly -or (($UploadS3 -or $UploadExisting) -and $AutoriserUploadS3)) {
  $versions = if ($env:LEOSOFT_VERSIONS_DIR) { $env:LEOSOFT_VERSIONS_DIR } else { "C:\LeoSoft\Versions" }
  if (-not $AllowS3WithoutLocal -and -not (Test-Path $versions)) {
    throw "Échec : dossier local Versions manquant après archivage ($versions)."
  }
  if (Test-Path $versions) {
    Write-Output "Versions locales : $versions"
  } else {
    Write-Output "ATTENTION : Versions locales absentes — sync ultérieure requise (voir VERSIONS.md)."
  }
}

Write-Output "Terminé. Aucun déploiement. Aucune suppression d'archives. Mongo intact."
exit 0
