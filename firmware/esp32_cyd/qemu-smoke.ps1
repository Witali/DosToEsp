[CmdletBinding()]
param([switch]$XtensaAsmSmoke)

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
$toolProject = [IO.Path]::GetFullPath((Join-Path $project `
    "..\..\..\HLV-codec\firmware\esp32_2432s028_hlv_player_idf_c"))

& (Join-Path $project "generate-game.ps1") -XtensaAsmSmoke:$XtensaAsmSmoke
& (Join-Path $toolProject "setup-qemu.ps1")
$buildDirectory = if ($XtensaAsmSmoke) {
    "build-qemu-xtensa-asm"
} else {
    "build-qemu"
}
$asmOption = if ($XtensaAsmSmoke) { "ON" } else { "OFF" }
& (Join-Path $project "idf.ps1") -IdfArguments @(
    "-B", $buildDirectory,
    "-D", "D2E_QEMU_SMOKE=ON",
    "-D", "D2E_XTENSA_ASM_SMOKE=$asmOption",
    "-D", "CCACHE_ENABLE=0",
    "qemu",
    "--qemu-extra-args=-no-reboot"
)
