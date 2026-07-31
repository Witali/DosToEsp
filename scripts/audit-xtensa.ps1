[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$sibling = Join-Path $project "..\HLV-codec"
$compiler = Join-Path $sibling `
    "firmware\esp32_2432s028_hlv_player_idf_c\.tools\espressif\tools\xtensa-esp-elf\esp-14.2.0_20260121\xtensa-esp-elf\bin\xtensa-esp32-elf-gcc.exe"
$python = Join-Path $sibling "local_tools\python\python.exe"
$outputDirectory = Join-Path $project "build-xtensa-audit"
$generated = Join-Path $outputDirectory "native_smoke.c"
$assembly = Join-Path $outputDirectory "native_smoke.xtensa.s"

if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) {
    throw "Xtensa ESP32 compiler was not found: $compiler"
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python was not found: $python"
}
if (-not (Test-Path -LiteralPath `
        (Join-Path $project "local_tools\python_packages\capstone\__init__.py") `
        -PathType Leaf)) {
    & (Join-Path $PSScriptRoot "setup-analysis-tools.ps1")
}

New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
& $python (Join-Path $project "tools\d2e_translate.py") `
    --hex-input --name native_smoke `
    (Join-Path $project "tests\fixtures\native_smoke.hex") $generated
if ($LASTEXITCODE -ne 0) { throw "COM translation failed" }

& $compiler -std=c99 -O2 -Wall -Wextra -Werror `
    -I (Join-Path $project "include") -S $generated -o $assembly
if ($LASTEXITCODE -ne 0) { throw "Xtensa compilation failed" }

$text = Get-Content -LiteralPath $assembly -Raw
foreach ($mnemonic in @("entry", "l32i", "s16i", "call8")) {
    if ($text -notmatch "(?m)^\s*$mnemonic(?:\.n)?\s") {
        throw "Expected Xtensa instruction was not emitted: $mnemonic"
    }
}
Write-Host "Xtensa native-code audit passed: $assembly"

