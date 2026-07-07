#Requires -Version 5.1
<#
.SYNOPSIS
  Verify Plan 4 operator prerequisites and print the next commands.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent $PSScriptRoot
$Gh = Join-Path $Root "gh_portable\bin\gh.exe"
if (-not (Test-Path $Gh)) { $Gh = "gh" }

function Test-CommandAvailable {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Host "=== Plan 4 operator checklist ===" -ForegroundColor Cyan

$checks = @(
    @{ Name = "terraform"; Ok = (Test-CommandAvailable "terraform") },
    @{ Name = "uv"; Ok = (Test-CommandAvailable "uv") },
    @{ Name = "gh"; Ok = (Test-CommandAvailable $Gh) }
)

foreach ($check in $checks) {
    $status = if ($check.Ok) { "ok" } else { "missing" }
    Write-Host ("[{0}] {1}" -f $status, $check.Name)
}

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    Write-Host "[missing] aws (run scripts/install_aws_cli.ps1)"
} else {
    Write-Host "[ok] aws"
}

$localFiles = @(
    "infra\terraform\bootstrap\terraform.tfvars",
    "infra\terraform\environments\dev\backend.hcl",
    "infra\terraform\environments\dev\terraform.tfvars"
)
foreach ($relative in $localFiles) {
    $path = Join-Path $Root $relative
    $status = if (Test-Path $path) { "ok" } else { "missing" }
    Write-Host ("[{0}] {1}" -f $status, $relative)
}

Write-Host ""
Write-Host "Operator handoff: docs/production/PLAN4_OPERATOR_HANDOFF.md"
Write-Host "GitHub repository variables:"
& $Gh variable list 2>$null

Write-Host ""
Write-Host "Next commands (after AWS credentials are configured):"
Write-Host "  1. powershell -File scripts/install_aws_cli.ps1"
Write-Host "  2. aws configure   # or aws configure sso"
Write-Host "  3. powershell -File scripts/plan4_resume.ps1 -Phase A"
