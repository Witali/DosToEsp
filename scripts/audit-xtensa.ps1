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
$memoryGenerated = Join-Path $outputDirectory "native_memory.c"
$memoryAssembly = Join-Path $outputDirectory "native_memory.xtensa.s"
$callGenerated = Join-Path $outputDirectory "native_call.c"
$callAssembly = Join-Path $outputDirectory "native_call.xtensa.s"
$logicGenerated = Join-Path $outputDirectory "native_logic.c"
$logicAssembly = Join-Path $outputDirectory "native_logic.xtensa.s"
$shiftGenerated = Join-Path $outputDirectory "native_shift.c"
$shiftAssembly = Join-Path $outputDirectory "native_shift.xtensa.s"

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

& $python (Join-Path $project "tools\d2e_translate.py") `
    --hex-input --name native_memory `
    (Join-Path $project "tests\fixtures\native_memory.hex") $memoryGenerated
if ($LASTEXITCODE -ne 0) { throw "ModR/M fixture translation failed" }

& $compiler -std=c99 -O2 -Wall -Wextra -Werror `
    -I (Join-Path $project "include") -S $memoryGenerated -o $memoryAssembly
if ($LASTEXITCODE -ne 0) { throw "ModR/M Xtensa compilation failed" }

& $python (Join-Path $project "tools\d2e_translate.py") `
    --hex-input --name native_call `
    (Join-Path $project "tests\fixtures\native_call.hex") $callGenerated
if ($LASTEXITCODE -ne 0) { throw "Stack/call fixture translation failed" }

& $compiler -std=c99 -O2 -Wall -Wextra -Werror `
    -I (Join-Path $project "include") -S $callGenerated -o $callAssembly
if ($LASTEXITCODE -ne 0) { throw "Stack/call Xtensa compilation failed" }

& $python (Join-Path $project "tools\d2e_translate.py") `
    --hex-input --name native_logic `
    (Join-Path $project "tests\fixtures\native_logic.hex") $logicGenerated
if ($LASTEXITCODE -ne 0) { throw "Boolean/flag fixture translation failed" }

& $compiler -std=c99 -O2 -Wall -Wextra -Werror `
    -I (Join-Path $project "include") -S $logicGenerated -o $logicAssembly
if ($LASTEXITCODE -ne 0) { throw "Boolean/flag Xtensa compilation failed" }

& $python (Join-Path $project "tools\d2e_translate.py") `
    --hex-input --name native_shift `
    (Join-Path $project "tests\fixtures\native_shift.hex") $shiftGenerated
if ($LASTEXITCODE -ne 0) { throw "Shift/rotate fixture translation failed" }

& $compiler -std=c99 -O2 -Wall -Wextra -Werror `
    -I (Join-Path $project "include") -S $shiftGenerated -o $shiftAssembly
if ($LASTEXITCODE -ne 0) { throw "Shift/rotate Xtensa compilation failed" }

$generatedText = Get-Content -LiteralPath $generated -Raw
foreach ($pattern in @(
        "static uint32_t program_region",
        "uint16_t r_ax;",
        "uint16_t r_cx;",
        "goto block_0106;")) {
    if ($generatedText -notmatch [regex]::Escape($pattern)) {
        throw "Expected native region pattern was not emitted: $pattern"
    }
}
if ($generatedText -match "static void block_") {
    throw "Legacy per-block functions were emitted instead of a cached region"
}

$memoryText = Get-Content -LiteralPath $memoryGenerated -Raw
foreach ($pattern in @(
        "d2e_x86_read16_seg",
        "d2e_x86_write16_seg",
        "d2e_x86_write8",
        "D2E_X86_SS",
        "D2E_X86_ES")) {
    if ($memoryText -notmatch [regex]::Escape($pattern)) {
        throw "Expected ModR/M pattern was not emitted: $pattern"
    }
}

$text = Get-Content -LiteralPath $assembly -Raw
foreach ($mnemonic in @("entry", "l32i", "s16i", "call8")) {
    if ($text -notmatch "(?m)^\s*$mnemonic(?:\.n)?\s") {
        throw "Expected Xtensa instruction was not emitted: $mnemonic"
    }
}
if ($text -notmatch "(?m)^program_region:") {
    throw "The generated native region is missing from Xtensa assembly"
}
if ($text -match "(?m)^block_[0-9a-f]+:") {
    throw "Guest blocks became ABI function boundaries in Xtensa assembly"
}
Write-Host `
    "Xtensa native-code audit passed: $assembly, $memoryAssembly, " `
    "$callAssembly, $logicAssembly, $shiftAssembly"
