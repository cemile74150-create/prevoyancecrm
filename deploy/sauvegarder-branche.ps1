# Enregistre une fonctionnalité terminée et testée sur sa branche GitHub.
# N'agit pas sur main, ne déploie pas, n'écrase pas un commit distant.
param(
  [string]$Message = "",
  [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

function Fail([string]$Text) {
  [Console]::Error.WriteLine($Text)
  exit 1
}

if ((Split-Path $Root -Leaf) -eq "prevoyancecrm") {
  Fail "Refus : prevoyancecrm n'est pas une source à pousser."
}

$branch = git rev-parse --abbrev-ref HEAD
if ($branch -eq "HEAD") { Fail "Refus : HEAD détaché." }
if ($branch -eq "main") { Fail "Refus : aucun push sur main." }

$dirty = git status --porcelain
$blocked = $dirty | Where-Object {
  $_ -match '\.env' -or $_ -match 'conflicted' -or $_ -match '\.pem' -or $_ -match 'credentials' -or $_ -match 'data_crypto_keys'
}
if ($blocked) {
  Fail ("Refus : fichier sensible dans les modifications : " + ($blocked -join " | "))
}

Write-Output "Branche : $branch"
if ($DryRun) {
  Write-Output "Simulation : aucun commit, aucun push, aucun déploiement."
  if ($dirty) { $dirty } else { Write-Output "Arbre de travail propre." }
  exit 0
}

if (-not $Message) { Fail "Refus : message de commit obligatoire." }
if (-not $dirty) { Fail "Rien à enregistrer." }

git add -A
$stagedSecrets = git diff --cached --name-only | Where-Object {
  $_ -match '(^|/)\.env($|\.)' -and $_ -notmatch '\.env\.example$' -or
  $_ -match 'conflicted' -or $_ -match '\.pem$' -or $_ -match 'credentials\.json$' -or $_ -match 'data_crypto_keys'
}
if ($stagedSecrets) {
  git reset -q
  Fail ("Refus : le commit contenait un fichier sensible : " + ($stagedSecrets -join ", "))
}

git commit -m $Message
if ($LASTEXITCODE -ne 0) { Fail "Le commit a échoué. Les fichiers locaux sont conservés." }

git push -u origin "HEAD:refs/heads/$branch"
if ($LASTEXITCODE -ne 0) { Fail "Le push a échoué. Le commit local est conservé et n'est pas sur GitHub." }

$local = git rev-parse HEAD
$remoteLine = git ls-remote origin "refs/heads/$branch" | Select-Object -First 1
$remote = ($remoteLine -split "\s+")[0]
if ($local -ne $remote) {
  Fail "Le commit distant ($remote) diffère du commit local ($local)."
}

Write-Output "Sauvegarde confirmée."
Write-Output "Branche : $branch"
Write-Output "Commit : $local"
Write-Output "GitHub : identique. Déploiement non lancé. main non modifiée."
exit 0
