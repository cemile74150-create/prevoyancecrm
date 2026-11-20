# Applique les protections GitHub sur main (+ develop).
# Prérequis : gh auth login (ou GH_TOKEN).
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

function Protect-Branch([string]$Branch, [bool]$StrictReviews) {
  $checks = @(
    @{ context = "backend-unit" },
    @{ context = "frontend-build" },
    @{ context = "guard-no-railway-deploy" }
  )

  $body = @{
    required_status_checks = @{
      strict   = $true
      contexts = @("backend-unit", "frontend-build", "guard-no-railway-deploy")
    }
    enforce_admins = $true
    required_pull_request_reviews = @{
      required_approving_review_count = $(if ($StrictReviews) { 1 } else { 0 })
      dismiss_stale_reviews           = $true
      require_code_owner_reviews      = $false
    }
    restrictions = $null
    allow_force_pushes = $false
    allow_deletions    = $false
    required_conversation_resolution = $true
  }

  $json = $body | ConvertTo-Json -Depth 6 -Compress
  Write-Host "Protecting $Owner/$Repo branch=$Branch ..."
  $tmp = [System.IO.Path]::GetTempFileName()
  try {
    [System.IO.File]::WriteAllText($tmp, $json)
    # API classic branch protection
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
Protect-Branch -Branch "main" -StrictReviews $true
if (-not $SkipDevelop) {
  Protect-Branch -Branch "develop" -StrictReviews $false
}
Write-Host "DONE — aucun déploiement effectué."
