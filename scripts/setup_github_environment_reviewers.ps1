#Requires -Version 5.1
<#
.SYNOPSIS
  Add required reviewers to staging and prod GitHub environments.
#>
param(
    [string]$ReviewerLogin = "avi9s7",
    [string]$Repo = "avi9s7/Vyu"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Gh = Join-Path (Split-Path -Parent $PSScriptRoot) "gh_portable\bin\gh.exe"
if (-not (Test-Path $Gh)) { $Gh = "gh" }

$userId = & $Gh api "users/$ReviewerLogin" --jq .id
if (-not $userId) { throw "Unable to resolve GitHub user id for $ReviewerLogin" }

$payload = @{
    wait_timer = 0
    reviewers = @(
        @{
            type = "User"
            id   = [int]$userId
        }
    )
} | ConvertTo-Json -Depth 4 -Compress

foreach ($environment in @("staging", "prod")) {
    $payload | & $Gh api "repos/$Repo/environments/$environment" -X PUT --input - | Out-Null
    Write-Host "Set required reviewer $ReviewerLogin on environment: $environment"
}
