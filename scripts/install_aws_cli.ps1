#Requires -Version 5.1
<#
.SYNOPSIS
  Install AWS CLI v2 on Windows when missing (user-scope, no admin required).
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (Get-Command aws -ErrorAction SilentlyContinue) {
    aws --version
    exit 0
}

$InstallRoot = Join-Path $env:LOCALAPPDATA "VYU\tools\aws-cli"
$MsiPath = Join-Path $env:TEMP "AWSCLIV2.msi"
$Url = "https://awscli.amazonaws.com/AWSCLIV2.msi"

Write-Host "Downloading AWS CLI v2..."
Invoke-WebRequest -Uri $Url -OutFile $MsiPath

Write-Host "Installing AWS CLI to $InstallRoot ..."
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
$arguments = @("/i", $MsiPath, "/qn", "INSTALLDIR=$InstallRoot")
Start-Process -FilePath "msiexec.exe" -ArgumentList $arguments -Wait

$AwsExe = Join-Path $InstallRoot "aws.exe"
if (-not (Test-Path $AwsExe)) {
    throw "AWS CLI install failed; aws.exe not found at $AwsExe"
}

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$InstallRoot*") {
    [Environment]::SetEnvironmentVariable("Path", "$UserPath;$InstallRoot", "User")
    $env:Path = "$env:Path;$InstallRoot"
}

Remove-Item -Force $MsiPath -ErrorAction SilentlyContinue
& $AwsExe --version
Write-Host "AWS CLI installed. Open a new terminal or run: aws configure"
