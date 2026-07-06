#Requires -Version 5.1
<#
.SYNOPSIS
  Update environment backend.hcl files from bootstrap Terraform outputs.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BootstrapDir = Join-Path $Root "infra\terraform\bootstrap"
$EnvRoot = Join-Path $Root "infra\terraform\environments"

Push-Location $BootstrapDir
try {
    $raw = terraform output -json
    if ($LASTEXITCODE -ne 0) {
        throw "terraform output failed. Apply infra/terraform/bootstrap first."
    }
}
finally {
    Pop-Location
}

$outputs = $raw | ConvertFrom-Json
$bucket = $outputs.state_bucket_name.value
$awsRegion = $outputs.aws_region.value
$kmsArn = $outputs.state_kms_key_arn.value
$lockTable = $outputs.lock_table_name.value
$accountId = $outputs.aws_account_id.value

foreach ($environment in @("dev", "staging", "prod")) {
    $target = Join-Path (Join-Path $EnvRoot $environment) "backend.hcl"
    @"
bucket         = "$bucket"
key            = "$environment/terraform.tfstate"
region         = "$awsRegion"
encrypt        = true
kms_key_id     = "$kmsArn"
dynamodb_table = "$lockTable"
"@ | Set-Content -Path $target -NoNewline
    Write-Host "Updated $target"
}

Write-Host ""
Write-Host "Bootstrap account id: $accountId"
Write-Host "Re-run setup_github_ci_placeholders.ps1 or render_github_ci_vars.py after environment apply."
