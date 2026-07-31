[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
$repository = [IO.Path]::GetFullPath((Join-Path $project "..\.."))
$sibling = [IO.Path]::GetFullPath((Join-Path $repository "..\HLV-codec"))
$python = Join-Path $sibling "local_tools\python\python.exe"
$output = Join-Path $project "main\generated\native_smoke.c"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python from the sibling HLV-codec project was not found: $python"
}
if (-not (Test-Path -LiteralPath `
        (Join-Path $repository "local_tools\python_packages\capstone\__init__.py") `
        -PathType Leaf)) {
    & (Join-Path $repository "scripts\setup-analysis-tools.ps1")
}

& $python (Join-Path $repository "tools\d2e_translate.py") `
    --hex-input --name native_smoke --load-segment 0x1000 `
    (Join-Path $repository "tests\fixtures\native_smoke.hex") $output
if ($LASTEXITCODE -ne 0) {
    throw "Native game translation failed"
}
