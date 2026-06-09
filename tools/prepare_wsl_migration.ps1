# WSL migration prep (Windows side). Safe while M1 backtest runs (no reboot unless -InstallWsl).
param(
    [switch]$InstallWsl,
    [switch]$LaunchSetup,
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$Root = "E:\active_alpha_model"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

Write-Host "=== WSL migration prep ===" -ForegroundColor Cyan

& $Py "$Root\tools\preflight_wsl_migration.py"
$preflightExit = $LASTEXITCODE

$manifestPath = Join-Path $Root "evidence\r0_migration\wsl_migration_manifest.json"
$statePath = Join-Path $Root "evidence\r0_migration\wsl_migration_state.json"
$checklistPath = Join-Path $Root "control\r0_migration\wsl_migration_checklist.json"

if (Test-Path $statePath) {
    $state = Get-Content $statePath -Raw | ConvertFrom-Json
    Write-Host ""
    Write-Host "State:" -ForegroundColor Cyan
    Write-Host "  WSL installed:  $($state.wsl_installed)"
    Write-Host "  Ubuntu ready:   $($state.ubuntu_ready)"
    Write-Host "  M1 productive:  $($state.m1_productive_windows)"
    Write-Host "  Reboot safe:    $($state.reboot_safe)"
    Write-Host "  Next step:      $($state.next_step)"
}

if ($PreflightOnly) {
    exit $preflightExit
}

if (-not $state.wsl_installed) {
    Write-Host ""
    Write-Host "WSL: NOT installed" -ForegroundColor Yellow
    if ($InstallWsl) {
        if ($state.m1_productive_windows) {
            Write-Host "M1 backtest RUNNING — WSL feature install OK, but defer REBOOT until CSV or hang." -ForegroundColor Yellow
        }
        Write-Host 'Running: wsl --install --no-distribution [Admin required]' -ForegroundColor Cyan
        wsl --install --no-distribution
        Write-Host ""
        Write-Host "AFTER reboot (when M1 done or hung):" -ForegroundColor Green
        Write-Host "  powershell -File tools/post_reboot_wsl.ps1"
    } else {
        Write-Host "Re-run with -InstallWsl (Admin) to enable WSL feature." -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "WSL: installed" -ForegroundColor Green
    wsl -l -v 2>$null
    if ($LaunchSetup) {
        if (-not $state.ubuntu_ready) {
            Write-Host "Ubuntu missing — run: powershell -File tools/post_reboot_wsl.ps1" -ForegroundColor Yellow
        } else {
            Write-Host "Launching setup inside WSL..." -ForegroundColor Cyan
            wsl bash -lc "bash /mnt/e/active_alpha_model/tools/setup_wsl_host.sh"
            wsl bash -lc "cd ~/active_alpha_model && bash tools/wsl_conductor.sh status"
        }
    } else {
        Write-Host "Ubuntu ready: $($state.ubuntu_ready)" -ForegroundColor Cyan
        Write-Host "After reboot: powershell -File tools/post_reboot_wsl.ps1" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Artifacts:" -ForegroundColor Cyan
Write-Host "  $manifestPath"
Write-Host "  $checklistPath"
Write-Host ""
Write-Host "Checklist: control/r0_migration/wsl_migration_checklist.json" -ForegroundColor Cyan

exit $preflightExit
