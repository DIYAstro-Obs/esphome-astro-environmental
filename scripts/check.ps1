# =========================================================
# Local checks in WSL: firmware compile (entry file and examples) and the configuration tests
# Path: scripts/check.ps1
# Started by hand only - deploy.ps1 and build.ps1 never run it.
#
# Usage:
#   .\check.ps1                  firmware compile + configuration tests
#   .\check.ps1 -TestsOnly       only the configuration tests
#   .\check.ps1 -FirmwareOnly    only the firmware compile
#   .\check.ps1 -k wind          everything else is passed to pytest
#
# Needs WSL with a Linux distribution (wsl --install -d Ubuntu). No credentials are used:
# the checks run with dummy secrets and without sudo. Optional setting in
# scripts/deployconf.secrets: WSL_DISTRO=<name> (default: the default WSL distribution).
# =========================================================

param(
    [switch]$TestsOnly,
    [switch]$FirmwareOnly,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"

# --- 1. OPTIONAL SETTING ---
$distro = ""
$secretsFile = Join-Path $PSScriptRoot "deployconf.secrets"
if (Test-Path $secretsFile) {
    Get-Content $secretsFile -Encoding UTF8 | ForEach-Object {
        if ($_ -match "^\s*WSL_DISTRO\s*=\s*(.*?)\s*$") { $distro = $matches[1] }
    }
}
$wslArgs = @()
if ($distro -ne "") { $wslArgs = @("-d", $distro) }

# --- 2. IS WSL USABLE? ---
$probe = ""
try { $probe = (& wsl @wslArgs -- echo astro-env-ok 2>$null) } catch { }
if ("$probe".Trim() -ne "astro-env-ok") {
    Write-Host "[!] WSL is not usable (distribution: $(if ($distro -ne '') { $distro } else { 'default' }))." -ForegroundColor Red
    Write-Host "    Install it once with: wsl --install -d Ubuntu (then restart and create the Linux user)." -ForegroundColor Red
    exit 2
}

# --- 3. START THE CHECKS INSIDE WSL ---
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$wslRepo = ("" + (& wsl @wslArgs -- wslpath -a ($repo -replace '\\', '/'))).Trim()
if ($wslRepo -eq "") {
    Write-Host "[!] Could not translate the repository path for WSL." -ForegroundColor Red
    exit 2
}

$flags = @()
if ($TestsOnly) { $flags += "--tests-only" }
if ($FirmwareOnly) { $flags += "--firmware-only" }

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "[*] Checks in WSL: $wslRepo" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

& wsl @wslArgs -- python3 "$wslRepo/tests/run_checks.py" @flags @PytestArgs
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 0) {
    Write-Host "[+] ALL CHECKS PASSED" -ForegroundColor Green
} elseif ($code -eq 2) {
    Write-Host "[!] The WSL environment is not ready, see the message above." -ForegroundColor Red
} else {
    Write-Host "[-] CHECKS FAILED" -ForegroundColor Red
}
exit $code
