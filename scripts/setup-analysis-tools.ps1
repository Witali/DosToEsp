[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$downloadDirectory = Join-Path $project "local_tools\downloads"
$packageDirectory = Join-Path $project "local_tools\python_packages"
$archive = Join-Path $downloadDirectory "capstone-5.0.9-win_amd64.zip"
$expectedHash = "732cedbbb56d42e723f14d7af6387f1454194a820b4b96b56d1e53f865ef85d0"
$url = "https://files.pythonhosted.org/packages/50/e6/6f06fdb6a9ed32b2f7cd9c036b92d5324112c3ef7080f2c71efc367d40dd/capstone-5.0.9-py3-none-win_amd64.whl"

New-Item -ItemType Directory -Force `
    -Path $downloadDirectory, $packageDirectory | Out-Null

if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    Write-Host "Downloading Capstone 5.0.9 from PyPI"
    Invoke-WebRequest -Uri $url -OutFile $archive
}

$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) {
    throw "Capstone archive SHA-256 mismatch: $actualHash"
}

$module = Join-Path $packageDirectory "capstone\__init__.py"
if (-not (Test-Path -LiteralPath $module -PathType Leaf)) {
    Expand-Archive -LiteralPath $archive -DestinationPath $packageDirectory -Force
}

Write-Host "Capstone analysis package is ready: $packageDirectory"

