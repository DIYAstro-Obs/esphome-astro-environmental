# =========================================================
# ESPHome Master Workflow: Compile -> Deploy
# Path: scripts/build_and_deploy.ps1
# =========================================================

$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Magenta
Write-Host "  STARTING FULL WORKFLOW  " -ForegroundColor Magenta
Write-Host "=========================================" -ForegroundColor Magenta
Write-Host ""

# 1. STEP: COMPILE
Write-Host "[STEP 1/2] Local Compilation Check..." -ForegroundColor Cyan
& "$PSScriptRoot\build.ps1"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" -ForegroundColor Red
    Write-Host "!!! COMPILE FAILED - ABORTING DEPLOY  !!!" -ForegroundColor Red
    Write-Host "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[STEP 2/2] Local check passed. Deploying to HA..." -ForegroundColor Cyan
Write-Host ""

# 2. STEP: DEPLOY
& "$PSScriptRoot\deploy.ps1"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host " ALL DONE! Firmware is ready on HA." -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Green
}