#Requires -Version 5.1
<#
.SYNOPSIS
  Materialize gitignored Terraform backend/tfvars files from examples using pilot placeholders.

.DESCRIPTION
  Copies terraform.tfvars.example -> terraform.tfvars and backend.hcl.example -> backend.hcl
  for dev, staging, and prod. Safe to re-run; overwrites local placeholder files only.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$EnvRoot = Join-Path $Root "infra\terraform\environments"
$ZoneId = "Z000000000000000000000"

function Write-BackendHcl {
    param(
        [string]$Environment
    )

    $backendExample = Join-Path (Join-Path $EnvRoot $Environment) "backend.hcl.example"
    $backendTarget = Join-Path (Join-Path $EnvRoot $Environment) "backend.hcl"
    Copy-Item -Path $backendExample -Destination $backendTarget -Force
    Write-Host "Wrote $backendTarget"
}

function Write-TfVars {
    param(
        [string]$Environment
    )

    $tfvarsExample = Join-Path (Join-Path $EnvRoot $Environment) "terraform.tfvars.example"
    $tfvarsTarget = Join-Path (Join-Path $EnvRoot $Environment) "terraform.tfvars"
    Copy-Item -Path $tfvarsExample -Destination $tfvarsTarget -Force
    $content = Get-Content -Path $tfvarsTarget -Raw
    $content = $content -replace 'edge_route53_zone_id\s*=\s*"[^"]*"', "edge_route53_zone_id     = `"$ZoneId`""
    Set-Content -Path $tfvarsTarget -Value $content -NoNewline
    Write-Host "Wrote $tfvarsTarget"
}

foreach ($environment in @("dev", "staging", "prod")) {
    Write-BackendHcl -Environment $environment
    Write-TfVars -Environment $environment
}

$BootstrapDir = Join-Path $Root "infra\terraform\bootstrap"
$bootstrapExample = Join-Path $BootstrapDir "terraform.tfvars.example"
$bootstrapTarget = Join-Path $BootstrapDir "terraform.tfvars"
Copy-Item -Path $bootstrapExample -Destination $bootstrapTarget -Force
Write-Host "Wrote $bootstrapTarget"

Write-Host ""
Write-Host "Placeholder Terraform files are ready. Replace account, state bucket, zone, and hostnames before apply."
Write-Host "Operator handoff: docs/production/PLAN4_OPERATOR_HANDOFF.md"
