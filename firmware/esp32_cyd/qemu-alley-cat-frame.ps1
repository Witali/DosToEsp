[CmdletBinding()]
param(
    [int]$FrameLimit = 8,
    [switch]$ScriptedInput,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
$root = [IO.Path]::GetFullPath((Join-Path $project "..\.."))
$toolProject = [IO.Path]::GetFullPath((Join-Path $project `
    "..\..\..\HLV-codec\firmware\esp32_2432s028_hlv_player_idf_c"))
$python = Join-Path $toolProject ".tools\python\python.exe"
$outputDirectory = Join-Path $root "out\qemu"
$log = Join-Path $outputDirectory "alley-cat-frame.log"
$frame = Join-Path $outputDirectory "alley-cat-frame.bmp"

if ($FrameLimit -le 0) {
    throw "FrameLimit must be positive"
}

New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
& (Join-Path $project "generate-game.ps1") -AlleyCat
& (Join-Path $toolProject "setup-qemu.ps1")

$qemuOutput = & (Join-Path $project "idf.ps1") -IdfArguments @(
    "-B", "build-qemu-alley-cat",
    "-D", "D2E_QEMU_SMOKE=ON",
    "-D", "D2E_ALLEY_CAT=ON",
    "-D", "D2E_SHELL=ON",
    "-D", "D2E_SHELL_AUTORUN=ON",
    "-D", "D2E_QEMU_EXIT_AFTER_RETURN=ON",
    "-D", "D2E_QEMU_INTERACTIVE=ON",
    "-D", "D2E_QEMU_INTERACTIVE_FRAME_LIMIT=$FrameLimit",
    "-D", "D2E_QEMU_DUMP_FRAME=ON",
    "-D", "D2E_QEMU_SCRIPTED_INPUT=$(if ($ScriptedInput) { 'ON' } else { 'OFF' })",
    "qemu",
    "--qemu-extra-args=-no-reboot"
) 2>&1
$qemuOutput | Tee-Object -FilePath $log

if (-not (Test-Path -LiteralPath $python)) {
    throw "ESP-IDF Python was not found: $python"
}
& $python (Join-Path $root "tools\d2e_qemu_frame.py") $log $frame
if ($LASTEXITCODE -ne 0) {
    throw "frame conversion failed with exit code $LASTEXITCODE"
}

Write-Host "CGA frame: $frame"
if (-not $NoOpen) {
    Start-Process -FilePath $frame
}
