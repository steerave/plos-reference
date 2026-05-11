# scripts/enable_logged_off.ps1
# ----------------------------------------------------------------------
# Switch every PLOS_* scheduled task to "Run whether user is logged on
# or not." Equivalent to opening each task in Task Scheduler ->
# Properties -> General -> selecting the second radio button and
# supplying your Windows password -- but done for all six tasks at once
# with one password prompt.
#
# How it works:
#   1. Prompt once for your Windows account password (typed as a
#      SecureString -- not echoed, kept in a managed buffer until the
#      COM call needs it, then zero-freed).
#   2. Connect to the Schedule.Service COM API (same one used by
#      scripts/install_schedules.ps1).
#   3. For each PLOS_* task: fetch its current definition, change
#      Principal.LogonType from Interactive (3) to Password (1),
#      re-register via RegisterTaskDefinition passing the password.
#      Windows stores the password encrypted in the local Credential
#      Manager (LSASS secret).
#   4. Report each result.
#
# To REVERT (switch back to logged-on-only): re-run
#   .\scripts\install_schedules.ps1
# which re-registers each task with LogonType=Interactive and no
# stored password. The Credential Manager entry is dropped automatically
# on the rewrite.
#
# Run from the repo root:
#   PS> .\scripts\enable_logged_off.ps1
#
# Smoke-test mode (no password prompt, no registration calls):
#   PS> .\scripts\enable_logged_off.ps1 -WhatIf
# ----------------------------------------------------------------------

[CmdletBinding()]
param(
    [switch]$WhatIf
)

# TASK_LOGON_TYPE enum values from the Task Scheduler 2.0 API.
$TASK_LOGON_PASSWORD          = 1
$TASK_LOGON_INTERACTIVE_TOKEN = 3
# TASK_CREATION flags. 6 = CREATE | UPDATE.
$TASK_CREATE_OR_UPDATE        = 6

$TaskNames = @(
    "PLOS_compile_this_week",
    "PLOS_compile_anomalies",
    "PLOS_compile_tax_prep",
    "PLOS_audit_pass",
    "PLOS_notifications",
    "PLOS_indexer"
)

$user = "$env:USERDOMAIN\$env:USERNAME"

Write-Host ""
Write-Host "Account:        $user"
Write-Host "Affects tasks:"
foreach ($n in $TaskNames) { Write-Host "  - $n" }
Write-Host ""

if ($WhatIf) {
    Write-Host "(whatif) Skipping password prompt and COM registration calls."
    Write-Host "         If you ran without -WhatIf, you would be prompted once"
    Write-Host "         for your Windows password and each task's LogonType"
    Write-Host "         would change from Interactive (3) to Password (1)."
    return
}

# SecureString prompt -- keystrokes are masked, value lives in protected
# memory until we marshal it for the single COM call below.
$securePw = Read-Host "Windows password for $user" -AsSecureString
if (-not $securePw -or $securePw.Length -eq 0) {
    Write-Error "Empty password -- aborting."
    exit 1
}

# Marshal SecureString -> plaintext BSTR for the COM API. The COM
# interop signature takes a plain string; there is no SecureString-
# aware overload. We minimise the plaintext lifetime by clearing it in
# the `finally` block.
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePw)
$plainPw = $null

try {
    $plainPw = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)

    $schedule = New-Object -ComObject "Schedule.Service"
    $schedule.Connect()
    $rootFolder = $schedule.GetFolder("\")

    $updated = 0
    $missing = 0

    foreach ($name in $TaskNames) {
        Write-Host "Updating $name"
        try {
            $task = $rootFolder.GetTask($name)
        }
        catch {
            Write-Host "  (no such task -- skipping; run install_schedules.ps1 first)"
            $missing++
            continue
        }

        $def = $task.Definition
        # Explicit re-set of UserId in case the task was created under
        # a different principal previously. Same value either way.
        $def.Principal.UserId = $user
        $def.Principal.LogonType = $TASK_LOGON_PASSWORD

        try {
            $rootFolder.RegisterTaskDefinition(
                $name,
                $def,
                $TASK_CREATE_OR_UPDATE,
                $user,
                $plainPw,
                $TASK_LOGON_PASSWORD,
                $null
            ) | Out-Null
            Write-Host "  OK"
            $updated++
        }
        catch {
            Write-Error "  FAILED: $($_.Exception.Message)"
            Write-Error "  Common cause: wrong password. Re-run to retry."
            exit 1
        }
    }

    Write-Host ""
    Write-Host "Updated $updated task(s); skipped $missing missing task(s)."
}
finally {
    # Wipe the plaintext password from memory as quickly as possible.
    if ($bstr -and $bstr -ne [IntPtr]::Zero) {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    if ($plainPw) {
        $plainPw = $null
    }
    [System.GC]::Collect()
}

Write-Host ""
Write-Host "Verify in Task Scheduler:"
Write-Host "  Right-click any PLOS_* task -> Properties -> General"
Write-Host "  -> 'Run whether user is logged on or not' should now be selected."
Write-Host ""
Write-Host "To revert (switch back to logged-on-only):"
Write-Host "  .\scripts\install_schedules.ps1"
