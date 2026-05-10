# scripts/uninstall_schedules.ps1
# ----------------------------------------------------------------------
# Remove every PLOS scheduled task that scripts/install_schedules.ps1
# registers with Windows Task Scheduler.
#
# Uses Unregister-ScheduledTask (the PowerShell-native API), matching
# the install script. Idempotent: tasks that are absent print a skip
# notice rather than failing the run.
#
# Run from the repo root:
#   PS> .\scripts\uninstall_schedules.ps1
# ----------------------------------------------------------------------

[CmdletBinding()]
param(
    [switch]$WhatIf
)

$TaskNames = @(
    "PLOS_compile_this_week",
    "PLOS_compile_anomalies",
    "PLOS_compile_tax_prep",
    "PLOS_audit_pass",
    "PLOS_notifications",
    "PLOS_indexer"
)

foreach ($name in $TaskNames) {
    Write-Host "Removing $name"

    if ($WhatIf) {
        Write-Host "  (whatif) Unregister-ScheduledTask -TaskName $name -Confirm:`$false"
        continue
    }

    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $existing) {
        Write-Host "  (no such task — skipping)"
        continue
    }
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
}

Write-Host ""
Write-Host "Done. To re-register, run: .\scripts\install_schedules.ps1"
