#Requires -Version 5.1
<#
.SYNOPSIS
  Copy Plan 4 secret templates into gitignored config/ files for local editing.
#>
param(
    [ValidateSet("dev", "staging", "prod")]
    [string]$Environment = "dev"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$SecretsDir = Join-Path $Root "infra\terraform\bootstrap\secrets"
$ConfigDir = Join-Path $Root "config"
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null

$databaseSource = Join-Path $SecretsDir "database-connection.example.txt"
$providersSource = Join-Path $SecretsDir "providers.example.json"
$databaseTarget = Join-Path $ConfigDir "$Environment-database-connection.txt"
$providersTarget = Join-Path $ConfigDir "$Environment-providers.json"

Copy-Item -Path $databaseSource -Destination $databaseTarget -Force
Copy-Item -Path $providersSource -Destination $providersTarget -Force

Write-Host "Wrote $databaseTarget"
Write-Host "Wrote $providersTarget"
Write-Host ""
Write-Host "Upload after editing (do not commit these files):"
Write-Host "Get-Content $databaseTarget -Raw | uv run python scripts/configure_secrets.py --environment $Environment --secret-id vyu/$Environment/database/connection --value-stdin"
Write-Host "Get-Content $providersTarget -Raw | uv run python scripts/configure_secrets.py --environment $Environment --secret-id vyu/$Environment/providers --value-stdin"
