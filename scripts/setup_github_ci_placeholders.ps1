#Requires -Version 5.1
<#
.SYNOPSIS
  Create GitHub environments and wire placeholder CI variables (replace after terraform apply).
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Repo = "avi9s7/Vyu"
$AccountId = "123456789012"
$Gh = Join-Path (Split-Path -Parent $PSScriptRoot) "gh_portable\bin\gh.exe"
if (-not (Test-Path $Gh)) {
    $Gh = "gh"
}

$AppHosts = @{
    dev     = "dev.app.vyu.example"
    staging = "staging.app.vyu.example"
    prod    = "app.vyu.example"
}

$SubnetIds = "subnet-0aaa1111bbbb2222,subnet-0ccc3333dddd4444,subnet-0eee5555ffff6666"
$MigrationSg = "sg-0placeholdermigration"

foreach ($environment in $AppHosts.Keys) {
    '{"wait_timer":0}' | & $Gh api "repos/$Repo/environments/$environment" -X PUT --input - | Out-Null
    Write-Host "Ensured GitHub environment: $environment"
}

& $Gh variable set AWS_PLAN_ROLE_ARN --repo $Repo --body "arn:aws:iam::${AccountId}:role/vyu-dev-github-plan"
Write-Host "Set repository variable AWS_PLAN_ROLE_ARN (placeholder)"

foreach ($environment in $AppHosts.Keys) {
    $prefix = "vyu-$environment"
    & $Gh variable set AWS_APPLY_ROLE_ARN --repo $Repo --env $environment --body "arn:aws:iam::${AccountId}:role/${prefix}-github-apply"
    & $Gh variable set AWS_BUILD_ROLE_ARN --repo $Repo --env $environment --body "arn:aws:iam::${AccountId}:role/${prefix}-github-build"
    & $Gh variable set AWS_PRIVATE_SUBNET_IDS --repo $Repo --env $environment --body $SubnetIds
    & $Gh variable set AWS_MIGRATION_SECURITY_GROUP_ID --repo $Repo --env $environment --body $MigrationSg
    & $Gh variable set APP_BASE_URL --repo $Repo --env $environment --body $AppHosts[$environment]
    Write-Host "Set placeholder deploy variables for environment: $environment"
}

Write-Host ""
Write-Host "After terraform apply, run: uv run python scripts/render_github_ci_vars.py <env>"
Write-Host "and replace the placeholder gh variable set commands with real output values."
