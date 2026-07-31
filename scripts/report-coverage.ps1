[CmdletBinding()]
param([string]$Name = "alley-cat")

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project "..\HLV-codec\local_tools\python\python.exe"
$inventory = Join-Path $project "out\analysis\$Name.json"
$output = Join-Path $project "out\analysis"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python was not found: $python"
}
if (-not (Test-Path -LiteralPath $inventory -PathType Leaf)) {
    throw "Static inventory was not found: $inventory"
}
& $python (Join-Path $project "tools\d2e_coverage.py") $inventory `
    --json (Join-Path $output "$Name-coverage.json") `
    --markdown (Join-Path $output "$Name-coverage.md")
if ($LASTEXITCODE -ne 0) {
    throw "Translator coverage report failed"
}
