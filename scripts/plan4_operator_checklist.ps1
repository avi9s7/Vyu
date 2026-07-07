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
    @{ Name = "aws"; Ok = (Test-CommandAvailable "aws") },
    @{ Name = "uv"; Ok = (Test-CommandAvailable "uv") },
    @{ Name = "gh"; Ok = (Test-CommandAvailable $Gh) }
)

foreach ($check in $checks) {
    $status = if ($check.Ok) { "ok" } else { "missing" }
    Write-Host ("[{0}] {1}" -f $status, $check.Name)
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
Write-Host "  1. powershell -File scripts/bootstrap_aws_placeholders.ps1"
Write-Host "  2. copy infra\terraform\bootstrap\terraform.tfvars.example infra\terraform\bootstrap\terraform.tfvars"
Write-Host "  3. terraform -chdir=infra/terraform/bootstrap init && terraform apply"
Write-Host "  4. powershell -File scripts/sync_backend_hcl_from_bootstrap.ps1"
Write-Host "  5. terraform -chdir=infra/terraform/environments/dev init -backend-config=backend.hcl"
Write-Host "  6. terraform -chdir=infra/terraform/environments/dev apply"
Write-Host "  7. uv run python scripts/render_github_ci_vars.py dev"
Write-Host "  8. Trigger Deploy workflow for staging per docs/production/runbooks/deployment.md"
