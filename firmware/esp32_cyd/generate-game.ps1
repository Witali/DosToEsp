[CmdletBinding()]
param([switch]$AlleyCat)

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

if ($AlleyCat) {
    $input = Join-Path $repository `
        "games\Alley-Cat_DOS_EN\alley-cat\CAT.EXE"
    $outputDirectory = Join-Path $project "main\generated\alley-cat"
    & (Join-Path $repository "scripts\translate-game.ps1") `
        -InputPath $input -Name alley-cat -OutputDirectory $outputDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Alley Cat source generation failed"
    }
    $manifest = Get-Content -LiteralPath `
        (Join-Path $outputDirectory "manifest.json") -Raw | ConvertFrom-Json
    if ($manifest.status -ne "complete") {
        throw "Alley Cat source generation is not complete"
    }
} else {
    & $python (Join-Path $repository "tools\d2e_translate.py") `
        --hex-input --name native_smoke --load-segment 0x1000 `
        (Join-Path $repository "tests\fixtures\native_smoke.hex") $output
    if ($LASTEXITCODE -ne 0) {
        throw "Native smoke translation failed"
    }
}
