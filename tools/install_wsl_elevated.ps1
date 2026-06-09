# One-shot WSL install - run elevated (user approved admin).
$ErrorActionPreference = "Stop"
$LogDir = "E:\active_alpha_model\evidence\r0_migration"
$Log = Join-Path $LogDir "wsl_install_log.txt"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format o), $Message
    Add-Content -Path $Log -Value $line
    Write-Host $line
}

Log "START wsl install (admin)"
try {
    $out = wsl --install --no-distribution 2>&1 | Out-String
    Log ("wsl --install --no-distribution: " + $out.Trim())
} catch {
    Log ("wsl install error: " + $_.Exception.Message)
}

$features = @(
    "Microsoft-Windows-Subsystem-Linux",
    "VirtualMachinePlatform"
)
foreach ($f in $features) {
    try {
        $r = dism.exe /online /enable-feature /featurename:$f /all /norestart 2>&1 | Out-String
        Log ("dism " + $f + ": " + $r.Trim())
    } catch {
        Log ("dism " + $f + " error: " + $_.Exception.Message)
    }
}

try {
    $upd = wsl --update 2>&1 | Out-String
    Log ("wsl --update: " + $upd.Trim())
} catch {
    Log ("wsl --update skipped: " + $_.Exception.Message)
}

Log "DONE - reboot required"
Log "Then run: powershell -ExecutionPolicy Bypass -File E:\active_alpha_model\tools\post_reboot_wsl.ps1"
Log "END"
