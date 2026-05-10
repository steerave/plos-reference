# scripts/install_schedules.ps1
# ----------------------------------------------------------------------
# Register the PLOS scheduled tasks with Windows Task Scheduler.
#
# Each task invokes scripts/scheduled_run.py <task-name>, which records
# the run in the `scheduled_runs` SQLite table and returns a non-zero
# exit code if the wrapped module raised.
#
# Run from the repo root with the venv created:
#   PS> .\scripts\install_schedules.ps1
#
# Each task runs under the *current user* account and only when the user
# is logged on (default schtasks behaviour). For tasks that should run
# while the user is logged off, edit the registered task in Task
# Scheduler -> Properties -> Security options -> "Run whether user is
# logged on or not", supply the account password, and accept the prompt.
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

# $PSScriptRoot is only reliably populated inside the script body, not
# in the param block. Resolve defaults here.
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

# Schedule definitions.
#
# Each task command is exactly:
#   "<PythonExe>" "<WrapperScript>" <module-name>
# with surrounding quotes so paths containing spaces (e.g. "Claude
# Projects") survive schtasks parsing.
#
# Schedule choices:
#   - compile_anomalies (3:00 a.m.) runs before compile_this_week so the
#     daily "Watching" section in this-week.md sees fresh anomaly state.
#   - audit_pass (5:00 a.m. Sun) runs after the weekly settle.
#   - notifications (8:00 a.m. Sun) runs after the audit so the digest
#     can reference its findings in a later slice.
#   - indexer (every 10 min) handles drain-resolution latency.

$Tasks = @(
    @{
        Name     = "PLOS_compile_this_week"
        Module   = "compile_this_week"
        Schedule = "DAILY"
        Time     = "06:00"
        Extra    = @()
    },
    @{
        Name     = "PLOS_compile_anomalies"
        Module   = "compile_anomalies"
        Schedule = "MONTHLY"
        Time     = "03:00"
        Extra    = @("/D", "1")  # 1st of every month
    },
    @{
        Name     = "PLOS_compile_tax_prep"
        Module   = "compile_tax_prep"
        Schedule = "MONTHLY"
        Time     = "04:00"
        Extra    = @("/D", "1")  # 1st of every month
    },
    @{
        Name     = "PLOS_audit_pass"
        Module   = "audit_pass"
        Schedule = "WEEKLY"
        Time     = "05:00"
        Extra    = @("/D", "SUN")
    },
    @{
        Name     = "PLOS_notifications"
        Module   = "notifications"
        Schedule = "WEEKLY"
        Time     = "08:00"
        Extra    = @("/D", "SUN")
    },
    @{
        Name     = "PLOS_indexer"
        Module   = "indexer"
        Schedule = "MINUTE"
        Time     = "08:05"  # arbitrary start; recurs every 10 minutes
        Extra    = @("/MO", "10")
    }
)

Write-Host ""
Write-Host "Repo root:      $RepoRoot"
Write-Host "Python exe:     $PythonExe"
Write-Host "Wrapper script: $WrapperScript"
Write-Host ""

foreach ($task in $Tasks) {
    # Quoting note: schtasks /TR receives a string. To embed quoted paths
    # inside that string we wrap the whole TR in single quotes and use
    # PowerShell's `"` to emit literal double quotes around each path.
    $tr = "`"$PythonExe`" `"$WrapperScript`" $($task.Module)"

    $args = @(
        "/Create",
        "/TN", $task.Name,
        "/TR", $tr,
        "/SC", $task.Schedule,
        "/ST", $task.Time,
        "/F"     # overwrite if a same-named task already exists
    )
    $args += $task.Extra

    Write-Host "Registering $($task.Name) ($($task.Schedule) at $($task.Time))"

    if ($WhatIf) {
        Write-Host "  (whatif) schtasks $($args -join ' ')"
        continue
    }

    & schtasks.exe @args
    if ($LASTEXITCODE -ne 0) {
        Write-Error "schtasks failed for $($task.Name) (exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
}

Write-Host ""
Write-Host "Done. View registered tasks:"
Write-Host "  schtasks /Query /FO LIST /V | findstr PLOS_"
Write-Host "Inspect run history in SQLite:"
Write-Host "  SELECT task_name, started_at, exit_status, error_summary"
Write-Host "    FROM scheduled_runs ORDER BY id DESC LIMIT 20;"
Write-Host ""
Write-Host "To remove these tasks again, run: .\scripts\uninstall_schedules.ps1"
