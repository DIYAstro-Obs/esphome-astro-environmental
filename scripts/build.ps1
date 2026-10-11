# =========================================================
# ESPHome Local Compiler Script
# Uses the default Python 3 of the Windows launcher (py -3).
# ESPHome 2026.9.0 or newer is required (encrypted OTA); it needs a recent Python.
# =========================================================
$ErrorActionPreference = "Stop"

$MinEsphomeVersion = [version]"2026.9.0"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "[*] Starting ESPHome build process..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check that ESPHome is installed and recent enough
$esphomeVersion = $null
try {
    $versionOutput = py -3 -m esphome version 2>$null
    if ($LASTEXITCODE -eq 0 -and "$versionOutput" -match '(\d+\.\d+\.\d+)') {
        $esphomeVersion = [version]$matches[1]
    }
} catch { }

if ($null -eq $esphomeVersion) {
    Write-Host "[!] ESPHome module not found for 'py -3'. Installing via pip..." -ForegroundColor Yellow
    py -3 -m pip install esphome
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[!] Error installing ESPHome. Installation failed." -ForegroundColor Red
        exit 1
    }
    $versionOutput = py -3 -m esphome version 2>$null
    if ("$versionOutput" -match '(\d+\.\d+\.\d+)') { $esphomeVersion = [version]$matches[1] }
}

if ($null -eq $esphomeVersion -or $esphomeVersion -lt $MinEsphomeVersion) {
    Write-Host "[!] ESPHome $MinEsphomeVersion or newer is required (found: $esphomeVersion)." -ForegroundColor Red
    Write-Host "    Update with: py -3 -m pip install -U esphome" -ForegroundColor Red
    exit 1
}
Write-Host "[+] ESPHome CLI is ready (version $esphomeVersion)." -ForegroundColor Green

# 2. Determine the path to astro-environmental.yaml
$mainYamlPath = Join-Path $PSScriptRoot "..\astro-environmental.yaml"
$projectDir = Join-Path $PSScriptRoot ".."

if (-Not (Test-Path $mainYamlPath)) {
    Write-Host "[!] Error: astro-environmental.yaml could not be found at: $mainYamlPath" -ForegroundColor Red
    exit 1
}

# 3. Change to the project directory and compile
Set-Location $projectDir
Write-Host "[*] Compiling $mainYamlPath ... Please wait." -ForegroundColor Yellow
Write-Host ""

# 4. The actual ESPHome command
py -3 -m esphome compile astro-environmental.yaml

# 5. Evaluate the compilation result
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host "[+] COMPILATION SUCCESSFUL!" -ForegroundColor Green
    Write-Host "The C++ firmware was built without errors." -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Red
    Write-Host "[-] COMPILATION FAILED!" -ForegroundColor Red
    Write-Host "Please check the console errors above." -ForegroundColor Red
    Write-Host "=========================================" -ForegroundColor Red
}
