[CmdletBinding()]
param([int]$FrameLimit = 0)

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
$toolProject = [IO.Path]::GetFullPath((Join-Path $project `
    "..\..\..\HLV-codec\firmware\esp32_2432s028_hlv_player_idf_c"))

if ($FrameLimit -lt 0) {
    throw "FrameLimit must be zero (continuous) or positive"
}

& (Join-Path $project "generate-game.ps1") -AlleyCat
& (Join-Path $toolProject "setup-qemu.ps1")
& (Join-Path $project "idf.ps1") -IdfArguments @(
    "-B", "build-qemu-alley-cat",
    "-D", "D2E_QEMU_SMOKE=ON",
    "-D", "D2E_ALLEY_CAT=ON",
    "-D", "D2E_QEMU_INTERACTIVE=ON",
    "-D", "D2E_QEMU_INTERACTIVE_FRAME_LIMIT=$FrameLimit",
    "qemu",
    "--qemu-extra-args=-no-reboot"
)
