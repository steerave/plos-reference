# scripts/uninstall_schedules.ps1
# ----------------------------------------------------------------------
# Remove every PLOS scheduled task that scripts/install_schedules.ps1
# registers with Windows Task Scheduler.
#
# Run from the repo root:
#   PS> .\scripts\uninstall_schedules.ps1
#
# Idempotent: missing tasks are reported but do not fail the run.
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
        Write-Host "  (whatif) schtasks /Delete /TN $name /F"
        continue
    }
    & schtasks.exe /Delete /TN $name /F 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  (no such task — skipping)"
    }
}

Write-Host ""
Write-Host "Done. To re-register, run: .\scripts\install_schedules.ps1"
