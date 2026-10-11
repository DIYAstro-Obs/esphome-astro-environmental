# =========================================================
# ESPHome Deployment Script for Home Assistant
# Path: scripts/deploy.ps1
# This script syncs the local workspace to the HA ESPHome folder via SCP.
#
# Settings come from scripts/deployconf.secrets (template: scripts/deployconf):
#   SSH_URL   host or host:port of the SSH add-on (required, no fallback)
#   SSH_USER  SSH user (default: root)
#   SSH_PW    SSH password (optional, plain text - use only for test systems)
# HA_* entries in the file are not used by this script.
# Without SSH_PW, scp asks for the password interactively.
#
# Usage:
#   .\deploy.ps1            deploy
#   .\deploy.ps1 -DryRun    show target and auth mode, do not connect
# =========================================================

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# SSH_ASKPASS needs an executable file. This helper is a tiny .cmd that prints the
# password from an environment variable, so the password itself is never written to disk.
function New-AskPassHelper {
    $name = "ha-deploy-askpass-" + [guid]::NewGuid().ToString("N") + ".cmd"
    $path = Join-Path ([System.IO.Path]::GetTempPath()) $name
    $command = '@powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); [Console]::Out.WriteLine($env:HA_DEPLOY_PASSWORD)"'
    [System.IO.File]::WriteAllText($path, $command + "`r`n", (New-Object System.Text.ASCIIEncoding))
    return $path
}

# Splits "host", "host:port" or "ssh://host:port" into host and port (default 22).
function ConvertFrom-SshUrl {
    param([string]$Url)
    $text = ($Url.Trim() -replace '^ssh://', '').TrimEnd('/')
    $sshHost = $text
    $port = 22
    if ($text -match '^([^:]+):(\d+)$') {
        $sshHost = $matches[1]
        $port = [int]$matches[2]
    }
    if ($sshHost -notmatch '^[A-Za-z0-9._-]+$') {
        throw "Invalid host '$sshHost' in SSH_URL (expected host or host:port)"
    }
    if ($port -lt 1 -or $port -gt 65535) {
        throw "Invalid port $port in SSH_URL"
    }
    return [pscustomobject]@{ SshHost = $sshHost; Port = $port }
}

# --- 1. CONFIGURATION & SECRETS ---
$SSH_URL = ""
$SSH_USER = "root"
$SSH_PW = ""
$REMOTE_BASE_PATH = "/config/esphome/"
$PROJECT_ROOT = Resolve-Path (Join-Path $PSScriptRoot "..")

# Load settings from deployconf.secrets
$secretsFile = Join-Path $PSScriptRoot "deployconf.secrets"
if (-not (Test-Path $secretsFile)) {
    Write-Host "[!] Error: $secretsFile not found. Copy scripts/deployconf to deployconf.secrets and fill in SSH_URL." -ForegroundColor Red
    exit 1
}
Get-Content $secretsFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match "^\s*([^#=]+)\s*=\s*(.*)\s*$") {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        if ($key -eq "SSH_URL") { $SSH_URL = $value }
        if ($key -eq "SSH_USER" -and $value -ne "") { $SSH_USER = $value }
        if ($key -eq "SSH_PW") { $SSH_PW = $value }
    }
}

# Validation
if ($SSH_URL -eq "") {
    Write-Host "[!] Error: SSH_URL not found in $secretsFile (example: SSH_URL=192.168.1.10:22)" -ForegroundColor Red
    exit 1
}
try {
    $target = ConvertFrom-SshUrl $SSH_URL
} catch {
    Write-Host "[!] Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
$SSH_HOST = $target.SshHost
$SSH_PORT = $target.Port

$authMode = if ($SSH_PW -ne "") { "password from deployconf.secrets (SSH_PW)" } else { "interactive (you will be asked for the password)" }

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "[*] Target: ${SSH_USER}@${SSH_HOST}:${SSH_PORT}" -ForegroundColor Cyan
Write-Host "[*] Path:   $REMOTE_BASE_PATH" -ForegroundColor Cyan
Write-Host "[*] Auth:   $authMode" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# --- 2. PREPARE FILE LIST ---
# We collect all items to be uploaded to avoid multiple password prompts
$ItemsToDeploy = @("esphome-astro-environmental", "astro-environmental.yaml")
$ValidLocalPaths = @()

foreach ($item in $ItemsToDeploy) {
    $fullPath = Join-Path $PROJECT_ROOT $item
    if (Test-Path $fullPath) {
        # Ensure paths with spaces are handled correctly
        $ValidLocalPaths += "`"$fullPath`""
    } else {
        Write-Host "[!] Warning: $item not found, skipping." -ForegroundColor Yellow
    }
}

if ($ValidLocalPaths.Count -eq 0) {
    Write-Host "[!] Error: No files found to deploy!" -ForegroundColor Red
    exit 1
}

if ($DryRun) {
    Write-Host "[*] Dry run: no connection is made. Would upload:" -ForegroundColor Yellow
    $ValidLocalPaths | ForEach-Object { Write-Host "    $_" }
    exit 0
}

# --- 3. EXECUTE DEPLOYMENT (SINGLE SESSION) ---
if ($SSH_PW -eq "") {
    Write-Host "[*] Uploading files... (You might be prompted for your password once)" -ForegroundColor Yellow
} else {
    Write-Host "[*] Uploading files..." -ForegroundColor Yellow
}

$remoteTarget = "${SSH_USER}@${SSH_HOST}:${REMOTE_BASE_PATH}"

# Build scp command with proper argument handling (avoids Command Injection)
# Flags: -r (recursive), -O (legacy SFTP/SCP for HA compatibility)
$scpArgs = @("-r", "-O", "-c", "aes256-gcm@openssh.com")
if ($SSH_PORT -ne 22) {
    $scpArgs += @("-P", "$SSH_PORT")
}
if ($SSH_PW -ne "") {
    # One attempt only (a wrong password fails fast), accept new host keys but reject changed ones
    $scpArgs += @("-o", "NumberOfPasswordPrompts=1", "-o", "StrictHostKeyChecking=accept-new", "-o", "PreferredAuthentications=password,keyboard-interactive")
}
$scpArgs += $ValidLocalPaths + @($remoteTarget)

$askPassHelper = $null
$scpExitCode = 1
try {
    if ($SSH_PW -ne "") {
        $askPassHelper = New-AskPassHelper
        $env:SSH_ASKPASS = $askPassHelper
        $env:SSH_ASKPASS_REQUIRE = "force"
        $env:HA_DEPLOY_PASSWORD = $SSH_PW
    }
    & scp @scpArgs
    $scpExitCode = $LASTEXITCODE
} finally {
    Remove-Item Env:SSH_ASKPASS, Env:SSH_ASKPASS_REQUIRE, Env:HA_DEPLOY_PASSWORD -ErrorAction SilentlyContinue
    if ($askPassHelper -and (Test-Path $askPassHelper)) { Remove-Item $askPassHelper -Force }
}

# --- 4. RESULT EVALUATION ---
if ($scpExitCode -eq 0) {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host "[+] DEPLOYMENT SUCCESSFUL!" -ForegroundColor Green
    Write-Host "All files have been synced to Home Assistant." -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Make sure /config/esphome/secrets.yaml on Home Assistant contains these keys:"
    Write-Host "   api_encryption_key, web_username, web_password"
    Write-Host "   (otherwise the Install stops with 'Secret ... not defined', see README, section Secrets)"
    Write-Host "2. Open your ESPHome Dashboard in Home Assistant."
    Write-Host "3. Click 'Install' on the 'astro-environmental'."
} else {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Red
    Write-Host "[-] DEPLOYMENT FAILED!" -ForegroundColor Red
    Write-Host "Check SSH_URL, SSH_USER and SSH_PW in deployconf.secrets and the HA SSH add-on settings." -ForegroundColor Red
    Write-Host "=========================================" -ForegroundColor Red
}
