# Run AFTER reboot once WSL feature is enabled.
# Installs Ubuntu (if missing) and launches full WSL host setup.
param(
    [switch]$SetupOnly,
    [switch]$SkipUbuntuInstall
)

$ErrorActionPreference = "Stop"
$Root = "E:\active_alpha_model"
Set-Location $Root

Write-Host "=== Post-reboot WSL migration ===" -ForegroundColor Cyan

& "$Root\.venv\Scripts\python.exe" "$Root\tools\preflight_wsl_migration.py"
if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 1) {
    Write-Host "Preflight failed (exit $LASTEXITCODE)" -ForegroundColor Red
    exit $LASTEXITCODE
}

$state = Get-Content "$Root\evidence\r0_migration\wsl_migration_state.json" -Raw | ConvertFrom-Json
if (-not $state.wsl_installed) {
    Write-Host "WSL still not installed. Run as Admin:" -ForegroundColor Red
    Write-Host "  wsl --install --no-distribution"
    exit 2
}

if (-not $SkipUbuntuInstall -and -not $state.ubuntu_ready) {
    Write-Host "Installing Ubuntu..." -ForegroundColor Cyan
    wsl --install -d Ubuntu
    Write-Host "Complete Ubuntu first-run (username/password), then re-run:" -ForegroundColor Yellow
    Write-Host "  powershell -File tools/post_reboot_wsl.ps1 -SetupOnly"
    exit 0
}

if ($SetupOnly -or $state.ubuntu_ready) {
    Write-Host "Launching WSL setup (rsync + venv + caches)..." -ForegroundColor Cyan
    wsl bash -lc "bash /mnt/e/active_alpha_model/tools/setup_wsl_host.sh"
    Write-Host ""
    Write-Host "Smoke test:" -ForegroundColor Green
    wsl bash -lc "cd ~/active_alpha_model && bash tools/wsl_conductor.sh status"
    Write-Host ""
    Write-Host "Ready. In WSL:" -ForegroundColor Green
    Write-Host "  cd ~/active_alpha_model && bash tools/wsl_conductor.sh status"
    Write-Host "  bash tools/wsl_conductor.sh autoseal   # after M1 CSV exists"
}
