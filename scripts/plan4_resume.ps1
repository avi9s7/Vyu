#Requires -Version 5.1
<#
.SYNOPSIS
  Orchestrate Plan 4 handoff phases A–E with prerequisite checks.

.PARAMETER Phase
  Phase letter to run: A (bootstrap), B (dev apply), C (github vars), D (secrets hint), E (drill checklist).

.PARAMETER DryRun
  Print commands without executing terraform/gh/aws writes.
#>
param(
    [ValidateSet("A", "B", "C", "D", "E", "All")]
    [string]$Phase = "A",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot

function Invoke-Step {
    param(
        [string]$Description,
        [scriptblock]$Action
    )
    Write-Host "==> $Description" -ForegroundColor Cyan
    if ($DryRun) {
        Write-Host "[dry-run] $($Action.ToString().Trim())"
        return
    }
    & $Action
}

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Run-PhaseA {
    Require-Command terraform
    Invoke-Step "Operator checklist" { powershell -NoProfile -File (Join-Path $Root "scripts\plan4_operator_checklist.ps1") }
    Invoke-Step "Bootstrap init" { terraform -chdir=(Join-Path $Root "infra\terraform\bootstrap") init }
    Invoke-Step "Bootstrap apply" { terraform -chdir=(Join-Path $Root "infra\terraform\bootstrap") apply -auto-approve }
    Invoke-Step "Sync backend.hcl files" { powershell -NoProfile -File (Join-Path $Root "scripts\sync_backend_hcl_from_bootstrap.ps1") }
}

function Run-PhaseB {
    Require-Command terraform
    $devDir = Join-Path $Root "infra\terraform\environments\dev"
    Invoke-Step "Dev init" { terraform -chdir=$devDir init -backend-config=backend.hcl }
    Invoke-Step "Dev plan" { terraform -chdir=$devDir plan -out=tfplan }
    Invoke-Step "Dev apply" { terraform -chdir=$devDir apply -auto-approve tfplan }
}

function Run-PhaseC {
    Require-Command uv
    Invoke-Step "Render GitHub CI variables" { uv run python (Join-Path $Root "scripts\render_github_ci_vars.py") dev }
    Write-Host "Run the printed gh variable set commands before deploying."
}

function Run-PhaseD {
    Invoke-Step "Seed local secret templates" { powershell -NoProfile -File (Join-Path $Root "scripts\seed_plan4_secret_templates.ps1") }
    Write-Host "Edit config/dev-*.json, then upload with configure_secrets.py (see PLAN4_OPERATOR_HANDOFF.md §4.6)."
}

function Run-PhaseE {
    Write-Host @"
Phase E is operator-run in staging. Execute runbooks in order:
  1. docs/production/runbooks/deployment.md
  2. docs/production/runbooks/rollback.md
  3. docs/production/runbooks/secret-rotation.md
  4. docs/production/runbooks/database-restore.md
Capture evidence and update IMPLEMENTATION_STATUS.md row 4.
"@
}

$phases = switch ($Phase) {
    "All" { @("A", "B", "C", "D", "E") }
    default { @($Phase) }
}

foreach ($item in $phases) {
    switch ($item) {
        "A" { Run-PhaseA }
        "B" { Run-PhaseB }
        "C" { Run-PhaseC }
        "D" { Run-PhaseD }
        "E" { Run-PhaseE }
    }
}
