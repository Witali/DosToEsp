[CmdletBinding()]
param(
    [switch]$AlleyCat,
    [switch]$XtensaAsmSmoke
)

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
$repository = [IO.Path]::GetFullPath((Join-Path $project "..\.."))
$sibling = [IO.Path]::GetFullPath((Join-Path $repository "..\HLV-codec"))
$python = Join-Path $sibling "local_tools\python\python.exe"
$output = if ($XtensaAsmSmoke) {
    Join-Path $project "main\generated\xtensa-asm-smoke"
} else {
    Join-Path $project "main\generated\native_smoke.c"
}

if ($AlleyCat -and $XtensaAsmSmoke) {
    throw "AlleyCat and XtensaAsmSmoke cannot be generated together"
}

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
} elseif ($XtensaAsmSmoke) {
    & $python (Join-Path $repository "tools\d2e_build.py") `
        --hex-input --format com --name native_asm_smoke `
        --load-segment 0x1000 --backend xtensa-asm --output $output `
        (Join-Path $repository "tests\fixtures\native_asm_mixed.hex")
    if ($LASTEXITCODE -ne 0) {
        throw "Xtensa assembly smoke translation failed"
    }
    $manifest = Get-Content -LiteralPath `
        (Join-Path $output "manifest.json") -Raw | ConvertFrom-Json
    if ($manifest.status -ne "complete") {
        throw "Xtensa assembly smoke source generation is not complete"
    }
} else {
    & $python (Join-Path $repository "tools\d2e_translate.py") `
        --hex-input --name native_smoke --load-segment 0x1000 `
        (Join-Path $repository "tests\fixtures\native_smoke.hex") $output
    if ($LASTEXITCODE -ne 0) {
        throw "Native smoke translation failed"
    }
}
