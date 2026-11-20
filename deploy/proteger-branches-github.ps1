# Applique les protections GitHub sur main (+ develop).
# Prérequis : gh auth login (ou GH_TOKEN).
# Conçu pour un usage solo (Cemile) : PR + CI obligatoires, sans review tierce bloquante.
# Ne déploie rien, ne touche pas Railway.

param(
  [string]$Owner = "cemile74150-create",
  [string]$Repo = "prevoyancecrm",
  [switch]$SkipDevelop
)

$ErrorActionPreference = "Stop"

function Require-Gh {
  gh auth status 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI non authentifié. Lance: gh auth login"
  }
}

function Protect-Branch([string]$Branch, [int]$ReviewCount) {
  # Contextes = noms des jobs CI (workflow "ci")
  $body = @{
    required_status_checks                   = @{
      strict   = $true
      contexts = @("backend-unit", "frontend-build", "guard-no-railway-deploy")
    }
    enforce_admins                           = $true
    required_pull_request_reviews            = @{
      required_approving_review_count = $ReviewCount
      dismiss_stale_reviews           = $true
      require_code_owner_reviews      = $false
    }
    restrictions                             = $null
    allow_force_pushes                       = $false
    allow_deletions                          = $false
    required_conversation_resolution         = $true
  }

  $json = $body | ConvertTo-Json -Depth 6 -Compress
  Write-Host "Protecting $Owner/$Repo branch=$Branch reviews=$ReviewCount ..."
  $tmp = [System.IO.Path]::GetTempFileName()
  try {
    [System.IO.File]::WriteAllText($tmp, $json)
    gh api `
      -X PUT `
      "repos/$Owner/$Repo/branches/$Branch/protection" `
      -H "Accept: application/vnd.github+json" `
      --input $tmp | Out-Null
  } finally {
    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
  }
  Write-Host "OK: $Branch protected"
}

Require-Gh

# main : PR + CI obligatoires, 0 review tierce (solo). Pas de push direct.
Protect-Branch -Branch "main" -ReviewCount 0

# develop : PR + CI recommandés ; 0 review pour ne pas bloquer ton rythme.
if (-not $SkipDevelop) {
  Protect-Branch -Branch "develop" -ReviewCount 0
}

Write-Host ""
Write-Host "DONE — aucun déploiement effectué."
Write-Host "Tu peux toujours : pousser feat/*, ouvrir des PR, merger tes propres PR (sans review externe)."
Write-Host "Tu ne peux plus : push direct / force-push sur main (ni develop si protégé)."
