[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
$toolProject = [IO.Path]::GetFullPath((Join-Path $project `
    "..\..\..\HLV-codec\firmware\esp32_2432s028_hlv_player_idf_c"))

& (Join-Path $project "generate-game.ps1") -AlleyCat
& (Join-Path $toolProject "setup-qemu.ps1")
& (Join-Path $project "idf.ps1") -IdfArguments @(
    "-B", "build-qemu-alley-cat",
    "-D", "D2E_QEMU_SMOKE=ON",
    "-D", "D2E_ALLEY_CAT=ON",
    "qemu",
    "--qemu-extra-args=-no-reboot"
)
