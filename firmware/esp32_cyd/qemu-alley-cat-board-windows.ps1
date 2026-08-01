[CmdletBinding()]
param(
    [ValidateRange(0, 1000000)]
    [int]$FrameLimit = 0,
    [string]$SdImage,
    [switch]$Headless,
    [switch]$ScriptedInput
)

$ErrorActionPreference = "Stop"
if ($FrameLimit -eq 0) {
    $FrameLimit = if ($Headless) { 240 } else { 1000000 }
}
$project = $PSScriptRoot
$root = [IO.Path]::GetFullPath((Join-Path $project "..\.."))
$hlvProject = [IO.Path]::GetFullPath((Join-Path $project `
    "..\..\..\HLV-codec\firmware\esp32_2432s028_hlv_player_idf_c"))
$hlvRoot = [IO.Path]::GetFullPath((Join-Path $hlvProject "..\.."))
$qemuRoot = Join-Path $hlvRoot "local_tools\qemu-sdspi-windows"
$qemu = Join-Path $qemuRoot "bin\qemu-system-xtensa.exe"
$qemuData = Join-Path $qemuRoot "share\qemu"
$build = Join-Path $project "build-qemu-board-alley-cat"
$flash = Join-Path $build "d2e-alley-cat-qemu-4mb.bin"
$log = Join-Path $root "out\qemu\alley-cat-board-windows.log"
if (-not $SdImage) {
    $SdImage = Join-Path $hlvProject `
        "qemu\hlv-big-buck-bunny-5min-h263-avi.img"
}
$SdImage = [IO.Path]::GetFullPath($SdImage)

& (Join-Path $project "generate-game.ps1") -AlleyCat
if (-not (Test-Path -LiteralPath $qemu -PathType Leaf)) {
    & (Join-Path $hlvProject "setup-qemu-sdspi-windows.ps1")
}
foreach ($required in @($qemu, $SdImage)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required QEMU file does not exist: $required"
    }
}

& (Join-Path $project "idf.ps1") -IdfArguments @(
    "-B", $build,
    "-D", "D2E_QEMU_SMOKE=ON",
    "-D", "D2E_QEMU_BOARD_DEVICES=ON",
    "-D", "D2E_ALLEY_CAT=ON",
    "-D", "D2E_QEMU_INTERACTIVE=ON",
    "-D", "D2E_QEMU_INTERACTIVE_FRAME_LIMIT=$FrameLimit",
    "-D", "D2E_QEMU_DUMP_FRAME=OFF",
    "-D", "D2E_QEMU_SCRIPTED_INPUT=$(if ($ScriptedInput) { 'ON' } else { 'OFF' })",
    "build"
)

& (Join-Path $project "idf.ps1") -EsptoolArguments @(
    "--chip", "esp32",
    "merge_bin",
    "-o", $flash,
    "--flash_mode", "dio",
    "--flash_freq", "80m",
    "--flash_size", "4MB",
    "--fill-flash-size", "4MB",
    "0x1000", "bootloader\bootloader.bin",
    "0x8000", "partition_table\partition-table.bin",
    "0x10000", "dostoesp_native_smoke.bin"
) -EsptoolWorkingDirectory $build

New-Item -ItemType Directory -Force -Path (Split-Path $log -Parent) |
    Out-Null
$display = if ($Headless) { "none" } else { "sdl" }
$qemuArguments = @(
    "-L", $qemuData,
    "-accel", "tcg,thread=multi",
    "-machine", "esp32,sdspi=on,st7789=on",
    "-display", $display,
    "-monitor", "none",
    "-serial", "stdio",
    "-snapshot",
    "-drive", "file=$flash,if=mtd,format=raw",
    "-drive", "file=$SdImage,if=sd,format=raw"
)
if ($Headless) {
    # A bounded smoke run deliberately calls esp_restart() at its frame limit.
    # Turning that reboot into process exit keeps automation finite. Visible
    # runs omit this flag so the SDL Reset action resets the emulated ESP32.
    $qemuArguments += "-no-reboot"
}
& $qemu @qemuArguments 2>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "QEMU exited with code $LASTEXITCODE. See $log"
}
if (-not (Select-String -LiteralPath $log -Quiet -Pattern "D2E_SD_READY,")) {
    throw "QEMU did not mount the emulated SD card. See $log"
}
if (-not (Select-String -LiteralPath $log -Quiet -Pattern "D2E_FRAME,")) {
    throw "QEMU did not render an Alley Cat frame. See $log"
}
Write-Host "QEMU ST7789/SDSPI run passed: $log"
