# scripts/install_schedules.ps1
# ----------------------------------------------------------------------
# Register the PLOS scheduled tasks with Windows Task Scheduler.
#
# Uses the Schedule.Service COM API directly. PowerShell's
# Register-ScheduledTask doesn't ship a working monthly-trigger surface
# in all versions, and schtasks.exe's CLI parser doesn't round-trip
# embedded quotes through PowerShell when the repo path contains
# spaces. The COM API sidesteps both problems: trigger types, action
# arguments, and principal settings are set as object properties, not
# parsed from a command line.
#
# Run from the repo root:
#   PS> .\scripts\install_schedules.ps1
#
# Each task runs under the *current user* account and only when the
# user is logged on (Interactive logon type). To run while logged off,
# open the task in Task Scheduler -> Properties -> "Run whether user
# is logged on or not" and provide the password.
#
# To remove the tasks again, run scripts/uninstall_schedules.ps1.
# ----------------------------------------------------------------------

[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$PythonExe,
    [string]$WrapperScript,
    [switch]$WhatIf
)

# Resolve defaults inside the body — $PSScriptRoot is not reliably
# populated in the param block across all PowerShell versions.
if (-not $RepoRoot) {
    $scriptDir = $PSScriptRoot
    if (-not $scriptDir) {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $RepoRoot = Split-Path -Parent $scriptDir
}
if (-not $PythonExe) {
    $PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
}
if (-not $WrapperScript) {
    $WrapperScript = Join-Path $RepoRoot "scripts\scheduled_run.py"
}

if (-not (Test-Path $PythonExe)) {
    Write-Error "Python executable not found at: $PythonExe"
    Write-Error "Create the venv first (python -m venv .venv) or pass -PythonExe."
    exit 1
}
if (-not (Test-Path $WrapperScript)) {
    Write-Error "Wrapper script not found at: $WrapperScript"
    exit 1
}

# Task Scheduler COM constants.
$TASK_TRIGGER_TIME    = 1   # one-time / repeating
$TASK_TRIGGER_DAILY   = 2
$TASK_TRIGGER_WEEKLY  = 3
$TASK_TRIGGER_MONTHLY = 4
$TASK_ACTION_EXEC               = 0
$TASK_LOGON_INTERACTIVE_TOKEN   = 3
$TASK_CREATE_OR_UPDATE          = 6
$TASK_RUNLEVEL_LUA              = 0   # least-privilege

# Day-of-week bitmask values for weekly triggers.
$DOW_SUNDAY    = 0x01
$DOW_MONDAY    = 0x02
$DOW_TUESDAY   = 0x04
$DOW_WEDNESDAY = 0x08
$DOW_THURSDAY  = 0x10
$DOW_FRIDAY    = 0x20
$DOW_SATURDAY  = 0x40

# Month-of-year bitmask. 4095 = all 12 months (2^0..2^11 = 0xFFF).
$ALL_MONTHS = 0xFFF

# Start dates use today as the boundary; for past times the scheduler
# computes the next valid occurrence automatically.
$today = (Get-Date -Format 'yyyy-MM-dd')

function Set-CommonTaskSettings {
    param($Settings)
    $Settings.Enabled                = $true
    $Settings.AllowDemandStart       = $true
    $Settings.StartWhenAvailable     = $true
    $Settings.DisallowStartIfOnBatteries = $false
    $Settings.StopIfGoingOnBatteries     = $false
    $Settings.ExecutionTimeLimit     = "PT1H"   # 1-hour timeout
    $Settings.RunOnlyIfNetworkAvailable = $false
    $Settings.MultipleInstances      = 2   # IgnoreNew
}

# Per-task spec. Each task carries one trigger-builder closure that
# accepts the task's Triggers collection and adds a trigger to it.
$Tasks = @(
    @{
        Name         = "PLOS_compile_this_week"
        Module       = "compile_this_week"
        Description  = "Daily compile pass for compiled/this-week.md"
        AddTrigger   = {
            param($triggers)
            $t = $triggers.Create($TASK_TRIGGER_DAILY)
            $t.StartBoundary = "${today}T06:00:00"
            $t.Enabled = $true
            $t.DaysInterval = 1
        }
    },
    @{
        Name         = "PLOS_compile_anomalies"
        Module       = "compile_anomalies"
        Description  = "Monthly compile pass for compiled/anomalies.md (1st of month)"
        AddTrigger   = {
            param($triggers)
            $t = $triggers.Create($TASK_TRIGGER_MONTHLY)
            $t.StartBoundary = "${today}T03:00:00"
            $t.Enabled = $true
            $t.DaysOfMonth = 1   # 1st of month
            $t.MonthsOfYear = $ALL_MONTHS
        }
    },
    @{
        Name         = "PLOS_compile_tax_prep"
        Module       = "compile_tax_prep"
        Description  = "Monthly compile pass for compiled/tax-prep.md (1st of month)"
        AddTrigger   = {
            param($triggers)
            $t = $triggers.Create($TASK_TRIGGER_MONTHLY)
            $t.StartBoundary = "${today}T04:00:00"
            $t.Enabled = $true
            $t.DaysOfMonth = 1
            $t.MonthsOfYear = $ALL_MONTHS
        }
    },
    @{
        Name         = "PLOS_audit_pass"
        Module       = "audit_pass"
        Description  = "Weekly audit of compiled-artifact provenance (Sun)"
        AddTrigger   = {
            param($triggers)
            $t = $triggers.Create($TASK_TRIGGER_WEEKLY)
            $t.StartBoundary = "${today}T05:00:00"
            $t.Enabled = $true
            $t.DaysOfWeek = $DOW_SUNDAY
            $t.WeeksInterval = 1
        }
    },
    @{
        Name         = "PLOS_notifications"
        Module       = "notifications"
        Description  = "Weekly digest (Sun); dry-run unless PLOS_NOTIFY_SEND=1 in .env"
        AddTrigger   = {
            param($triggers)
            $t = $triggers.Create($TASK_TRIGGER_WEEKLY)
            $t.StartBoundary = "${today}T08:00:00"
            $t.Enabled = $true
            $t.DaysOfWeek = $DOW_SUNDAY
            $t.WeeksInterval = 1
        }
    },
    @{
        Name         = "PLOS_indexer"
        Module       = "indexer"
        Description  = "Review-queue self-cleaner + queue.md renderer (every 10 min)"
        AddTrigger   = {
            param($triggers)
            $t = $triggers.Create($TASK_TRIGGER_TIME)
            $t.StartBoundary = "${today}T08:05:00"
            $t.Enabled = $true
            $t.Repetition.Interval = "PT10M"            # ISO-8601 duration
            $t.Repetition.Duration = "P3650D"           # ~10 years
            $t.Repetition.StopAtDurationEnd = $false
        }
    }
)

Write-Host ""
Write-Host "Repo root:      $RepoRoot"
Write-Host "Python exe:     $PythonExe"
Write-Host "Wrapper script: $WrapperScript"
Write-Host ""

$schedule = New-Object -ComObject "Schedule.Service"
$schedule.Connect()
$rootFolder = $schedule.GetFolder("\")

$user = "$env:USERDOMAIN\$env:USERNAME"

foreach ($task in $Tasks) {
    Write-Host "Registering $($task.Name)"
    Write-Host "  $($task.Description)"

    if ($WhatIf) {
        Write-Host "  (whatif) RegisterTaskDefinition $($task.Name) for $user"
        continue
    }

    $def = $schedule.NewTask(0)
    $def.RegistrationInfo.Description = $task.Description
    $def.RegistrationInfo.Author = "plos-reference install_schedules.ps1"

    $def.Principal.UserId = $user
    $def.Principal.LogonType = $TASK_LOGON_INTERACTIVE_TOKEN
    $def.Principal.RunLevel = $TASK_RUNLEVEL_LUA

    Set-CommonTaskSettings $def.Settings

    & $task.AddTrigger $def.Triggers | Out-Null

    $action = $def.Actions.Create($TASK_ACTION_EXEC)
    $action.Path = $PythonExe
    # Wrapping the wrapper-script path in double quotes survives intact
    # through the COM API — no command-line reparsing happens.
    $action.Arguments = "`"$WrapperScript`" $($task.Module)"
    $action.WorkingDirectory = $RepoRoot

    try {
        $rootFolder.RegisterTaskDefinition(
            $task.Name,
            $def,
            $TASK_CREATE_OR_UPDATE,
            $user,
            $null,
            $TASK_LOGON_INTERACTIVE_TOKEN,
            $null
        ) | Out-Null
    }
    catch {
        Write-Error "RegisterTaskDefinition failed for $($task.Name): $($_.Exception.Message)"
        exit 1
    }
}

Write-Host ""
Write-Host "Done. View registered tasks:"
Write-Host "  Get-ScheduledTask -TaskName 'PLOS_*' | Format-Table TaskName, State, @{N='Next';E={(`$_.Triggers | Select-Object -First 1).StartBoundary}}"
Write-Host "Inspect run history in SQLite:"
Write-Host "  SELECT task_name, started_at, exit_status, error_summary"
Write-Host "    FROM scheduled_runs ORDER BY id DESC LIMIT 20;"
Write-Host ""
Write-Host "To remove these tasks again, run: .\scripts\uninstall_schedules.ps1"
