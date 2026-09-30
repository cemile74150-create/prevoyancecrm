# Register daily professional backup task at 02:00.
# Prefers "Run whether user is logged on or not" (Password / S4U).
# Falls back to Interactive if elevation is required and unavailable.
# Retention Infomaniak: BACKUP_RETENTION_COUNT=7 (7 archives .crmbak les plus récentes).

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Wrapper = Join-Path $PSScriptRoot "run_backup_task_wrapper.ps1"
$TaskName = "PrevoyanceCRM-DailyBackup"
$LogDir = Join-Path $Root "backend\backups"
$LogFile = Join-Path $LogDir "backup_task.log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not (Test-Path $Wrapper)) {
  throw "Missing backup wrapper: $Wrapper"
}

$others = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
  $_.TaskName -ne $TaskName -and (
    $_.TaskName -match "Prevoyance|CRM.*Backup|Backup.*CRM" -or
    ($_.Description -match "PrevoyanceCRM|prevoyancecrm")
  )
}
if ($others) {
  Write-Host "WARNING: other related tasks found:"
  $others | ForEach-Object { Write-Host (" - " + $_.TaskName + " state=" + $_.State) }
}

$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"Set-Location -LiteralPath '$Root'; & '$Wrapper'; exit `$LASTEXITCODE`"" `
  -WorkingDirectory "$Root"

$trigger = New-ScheduledTaskTrigger -Daily -At 2:00AM
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -WakeToRun `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Hours 6)

function Get-BackupTaskPassword {
  if ($env:BACKUP_TASK_PASSWORD) { return $env:BACKUP_TASK_PASSWORD }
  $envFile = Join-Path $Root "backend\.env.backup"
  if (Test-Path $envFile) {
    foreach ($raw in Get-Content $envFile -Encoding UTF8) {
      $line = $raw.Trim()
      if ($line -match '^BACKUP_TASK_PASSWORD=(.+)$') {
        return $Matches[1].Trim().Trim('"').Trim("'")
      }
    }
  }
  return $null
}

function Try-Register {
  param($Principal, $Password, $ModeLabel)
  try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    $params = @{
      TaskName    = $TaskName
      Action      = $action
      Trigger     = $trigger
      Settings    = $settings
      Principal   = $Principal
      Description = "Daily encrypted CRM backup at 02:00 to Infomaniak; retain last 30"
      Force       = $true
    }
    if ($Password) { $params["Password"] = $Password }
    Register-ScheduledTask @params | Out-Null
    return $ModeLabel
  } catch {
    Write-Host ("Register failed ($ModeLabel): " + $_.Exception.Message)
    return $null
  }
}

$userId = $env:USERNAME
$domainUser = if ($env:USERDOMAIN) { "$env:USERDOMAIN\$env:USERNAME" } else { $env:USERNAME }
$password = Get-BackupTaskPassword
$registeredMode = $null

if ($password) {
  $p = New-ScheduledTaskPrincipal -UserId $domainUser -LogonType Password -RunLevel Highest
  $registeredMode = Try-Register -Principal $p -Password $password -ModeLabel "Password+Highest (whether logged on or not)"
  if (-not $registeredMode) {
    $p = New-ScheduledTaskPrincipal -UserId $domainUser -LogonType Password -RunLevel Limited
    $registeredMode = Try-Register -Principal $p -Password $password -ModeLabel "Password+Limited (whether logged on or not)"
  }
}

if (-not $registeredMode) {
  $p = New-ScheduledTaskPrincipal -UserId $domainUser -LogonType S4U -RunLevel Highest
  $registeredMode = Try-Register -Principal $p -Password $null -ModeLabel "S4U+Highest (whether logged on or not)"
}
if (-not $registeredMode) {
  $p = New-ScheduledTaskPrincipal -UserId $domainUser -LogonType S4U -RunLevel Limited
  $registeredMode = Try-Register -Principal $p -Password $null -ModeLabel "S4U+Limited (whether logged on or not)"
}
if (-not $registeredMode) {
  # Works without admin elevation; runs when user session exists (StartWhenAvailable + WakeToRun still help)
  $p = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
  $registeredMode = Try-Register -Principal $p -Password $null -ModeLabel "Interactive+Limited (needs user session — elevate or set BACKUP_TASK_PASSWORD for off-session)"
}

if (-not $registeredMode) {
  throw "Impossible d'enregistrer la tâche $TaskName (droits insuffisants). Relancez PowerShell en Administrateur ou définissez BACKUP_TASK_PASSWORD."
}

$info = Get-ScheduledTaskInfo -TaskName $TaskName
$task = Get-ScheduledTask -TaskName $TaskName
$principal = $task.Principal
Write-Host "TASK_REGISTERED=$TaskName"
Write-Host "MODE=$registeredMode"
Write-Host "LOGON_TYPE=$($principal.LogonType)"
Write-Host "RUN_LEVEL=$($principal.RunLevel)"
Write-Host "STATE=$($task.State)"
Write-Host "NEXT_RUN=$($info.NextRunTime)"
Write-Host "LAST_RUN=$($info.LastRunTime)"
Write-Host "LAST_RESULT=$($info.LastTaskResult)"
Write-Host "MISSED=$($info.NumberOfMissedRuns)"
Write-Host "WAKE_TO_RUN=$($task.Settings.WakeToRun)"
Write-Host "START_WHEN_AVAILABLE=$($task.Settings.StartWhenAvailable)"
Write-Host "LOG=$LogFile"
Write-Host "Retention: BACKUP_RETENTION_COUNT=7 (Infomaniak)"
if ($registeredMode -match "Interactive") {
  Write-Host "IMPORTANT: Off-session mode needs admin elevation or BACKUP_TASK_PASSWORD in backend/.env.backup"
}
