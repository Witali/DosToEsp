[CmdletBinding()]
param(
    [ValidateRange(1, 1000000)]
    [int]$FrameLimit = 60,
    [string]$InputPath
)

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
$root = [IO.Path]::GetFullPath((Join-Path $project "..\.."))
$commonDirectory = (& git -C $root rev-parse --path-format=absolute `
    --git-common-dir).Trim()
if ($LASTEXITCODE -ne 0 -or -not $commonDirectory) {
    throw "Could not locate the main DosToEsp repository"
}
$mainRoot = Split-Path -Parent ([IO.Path]::GetFullPath($commonDirectory))
$workspace = Split-Path -Parent $mainRoot
$hlvProject = Join-Path $workspace `
    "HLV-codec\firmware\esp32_2432s028_hlv_player_idf_c"
$qemuRoot = Join-Path $workspace "QEMU-ESP32"
$qemu = Join-Path $qemuRoot "bin\qemu-system-xtensa.exe"
$qemuData = Join-Path $qemuRoot "share\qemu"
if (-not $InputPath) {
    $InputPath = Join-Path $mainRoot `
        "games\volkov-commander-4.00\VC.COM"
}
$sourceDirectory = Split-Path -Parent $InputPath
$module = Join-Path $root "out\modules\VC.D2E"
$build = Join-Path $project "build-qemu-xip-volkov-commander"
$flash = Join-Path $build "d2e-xip-shell-qemu-4mb.bin"
$sd = Join-Path $build "d2e-xip-modules-sd.img"
$marker = Join-Path $build "qemu.txt"
$log = Join-Path $root "out\qemu\volkov-commander-xip-windows.log"

foreach ($required in @($qemu, $InputPath, $sourceDirectory)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required XIP run input does not exist: $required"
    }
}

& (Join-Path $root "scripts\build-volkov-commander.ps1") `
    -InputPath $InputPath -ModulePath $module

& (Join-Path $project "idf.ps1") -IdfArguments @(
    "-B", $build,
    "-D", "D2E_QEMU_SMOKE=ON",
    "-D", "D2E_QEMU_BOARD_DEVICES=ON",
    "-D", "D2E_ALLEY_CAT=OFF",
    "-D", "D2E_XIP_SHELL=ON",
    "-D", "D2E_SHELL=ON",
    "-D", "D2E_SHELL_AUTORUN=ON",
    "-D", "D2E_QEMU_XIP_INSTALL_FILE=VC.D2E",
    "-D", "D2E_QEMU_EXIT_AFTER_RETURN=ON",
    "-D", "D2E_QEMU_INTERACTIVE=ON",
    "-D", "D2E_QEMU_INTERACTIVE_FRAME_LIMIT=$FrameLimit",
    "build"
)

& (Join-Path $project "idf.ps1") -EsptoolArguments @(
    "--chip", "esp32", "merge_bin", "-o", $flash,
    "--flash_mode", "dio", "--flash_freq", "80m",
    "--flash_size", "4MB", "--fill-flash-size", "4MB",
    "0x1000", "bootloader\bootloader.bin",
    "0x8000", "partition_table\partition-table.bin",
    "0x10000", "dostoesp_native_smoke.bin"
) -EsptoolWorkingDirectory $build

function ConvertTo-WslPath([string]$Path) {
    $fullPath = [IO.Path]::GetFullPath($Path).Replace("\", "/")
    $converted = & wsl.exe wslpath -a -u $fullPath
    if ($LASTEXITCODE -ne 0) {
        throw "Could not convert path for WSL: $Path"
    }
    return $converted.Trim()
}

function Quote-Bash([string]$Value) {
    $singleQuote = [string][char]39
    $replacement = $singleQuote + '"' + $singleQuote + '"' + $singleQuote
    return $singleQuote + $Value.Replace($singleQuote, $replacement) +
        $singleQuote
}

New-Item -ItemType Directory -Force -Path $build,
    (Split-Path $log -Parent) | Out-Null
[IO.File]::WriteAllText($marker, "HLV ESP32 SPI3 SD test`n")
if (Test-Path -LiteralPath $sd -PathType Leaf) {
    $resolvedBuild = [IO.Path]::GetFullPath($build)
    $resolvedSd = [IO.Path]::GetFullPath($sd)
    if (-not $resolvedSd.StartsWith(
            $resolvedBuild + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace unexpected SD image: $resolvedSd"
    }
    Remove-Item -LiteralPath $resolvedSd -Force
}
$wslSd = Quote-Bash (ConvertTo-WslPath $sd)
$wslModule = Quote-Bash (ConvertTo-WslPath $module)
$wslMarker = Quote-Bash (ConvertTo-WslPath $marker)
$wslSource = Quote-Bash (ConvertTo-WslPath $sourceDirectory)
& wsl.exe bash -lc (
    "truncate -s 64M $wslSd && " +
    "mkfs.vfat -F 32 -n D2EXIP $wslSd >/dev/null && " +
    "mmd -i $wslSd ::/HLV && " +
    "mcopy -i $wslSd $wslMarker ::/HLV/qemu.txt && " +
    "mcopy -i $wslSd -s $wslSource/* ::/ && " +
    "mcopy -i $wslSd $wslModule ::/VC.D2E"
)
if ($LASTEXITCODE -ne 0) {
    throw "Could not create the Volkov Commander SD-card image"
}

$qemuArguments = @(
    "-L", $qemuData,
    "-accel", "tcg,thread=multi",
    "-machine", "esp32,sdspi=on,st7789=on",
    "-display", "none",
    "-monitor", "none",
    "-serial", "stdio",
    "-no-reboot",
    "-snapshot",
    "-drive", "file=$flash,if=mtd,format=raw",
    "-drive", "file=$sd,if=sd,format=raw"
)
& $qemu @qemuArguments 2>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "QEMU exited with code $LASTEXITCODE. See $log"
}
foreach ($expected in @(
    "D2E_QEMU_XIP_INSTALL,file=VC.D2E,result=ESP_OK",
    "D2E_MODULE_INSTALLED,command=VC",
    "D2E_AUTOEXEC_CREATED,file=A:/AUTOEXEC.BAT,command=VC",
    "D2E_AUTOEXEC_RUN,file=A:/AUTOEXEC.BAT",
    "D2E_AUTOEXEC_LINE,line=1,text=VC",
    "D2E_MODULE_ACTIVE,command=VC",
    "D2E_SHELL_RUN,command=VC",
    "D2E_SHELL_RETURN,command=VC,source=harness",
    "D2E_QEMU_DONE,0"
)) {
    if (-not (Select-String -LiteralPath $log -Quiet -SimpleMatch $expected)) {
        throw "XIP QEMU check is missing '$expected'. See $log"
    }
}
Write-Host "Volkov Commander XIP module QEMU run passed: $log"
