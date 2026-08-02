[CmdletBinding()]
param(
    [ValidateRange(1, 1000000)]
    [int]$FrameLimit = 60,
    [switch]$Profile
)

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
$root = [IO.Path]::GetFullPath((Join-Path $project "..\.."))
$hlvProject = [IO.Path]::GetFullPath((Join-Path $project `
    "..\..\..\HLV-codec\firmware\esp32_2432s028_hlv_player_idf_c"))
$qemuRoot = [IO.Path]::GetFullPath((Join-Path $project `
    "..\..\..\QEMU-ESP32"))
$qemu = Join-Path $qemuRoot "bin\qemu-system-xtensa.exe"
$qemuData = Join-Path $qemuRoot "share\qemu"
$python = [IO.Path]::GetFullPath((Join-Path $root `
    "..\HLV-codec\local_tools\python\python.exe"))
$toolchainRoot = Join-Path $hlvProject `
    ".tools\espressif\tools\xtensa-esp-elf"
$toolchainBin = Get-ChildItem -LiteralPath $toolchainRoot -Directory |
    Sort-Object Name -Descending | ForEach-Object {
        Join-Path $_.FullName "xtensa-esp-elf\bin"
    } | Where-Object {
        Test-Path -LiteralPath `
            (Join-Path $_ "xtensa-esp32-elf-gcc.exe") -PathType Leaf
    } | Select-Object -First 1
$input = Join-Path $root "games\Alley-Cat_DOS_EN\alley-cat\CAT.EXE"
$generated = Join-Path $project "main\generated\alley-cat"
$module = Join-Path $root "out\modules\ALLEY.D2E"
$build = Join-Path $project "build-qemu-xip-shell"
$flash = Join-Path $build "d2e-xip-shell-qemu-4mb.bin"
$sd = Join-Path $build "d2e-xip-modules-sd.img"
$marker = Join-Path $build "qemu.txt"
$log = Join-Path $root "out\qemu\alley-cat-xip-windows.log"
$profileValue = if ($Profile) { "ON" } else { "OFF" }

foreach ($required in @($qemu, $python, $input, $toolchainBin)) {
    if (-not $required -or -not (Test-Path -LiteralPath $required)) {
        throw "Required XIP build input does not exist: $required"
    }
}

& $python (Join-Path $root "tools\d2e_build.py") $input `
    --name alley-cat --backend xtensa-asm --output $generated `
    --xip-module $module --xtensa-toolchain-bin $toolchainBin `
    --command ALLEY --title "Alley Cat"
if ($LASTEXITCODE -ne 0) {
    throw "Alley Cat XIP translation failed"
}

$idfArguments = @(
    "-B", $build,
    "-D", "D2E_QEMU_SMOKE=ON",
    "-D", "D2E_QEMU_BOARD_DEVICES=ON",
    "-D", "D2E_ALLEY_CAT=OFF",
    "-D", "D2E_XIP_SHELL=ON",
    "-D", "D2E_SHELL=ON",
    "-D", "D2E_SHELL_AUTORUN=ON",
    "-D", "D2E_QEMU_XIP_INSTALL_FILE=ALLEY.D2E",
    "-D", "D2E_TRANSLATION_PROFILE=$profileValue",
    "-D", "D2E_QEMU_EXIT_AFTER_RETURN=ON",
    "-D", "D2E_QEMU_INTERACTIVE=ON",
    "-D", "D2E_QEMU_INTERACTIVE_FRAME_LIMIT=$FrameLimit",
    "build"
)
& (Join-Path $project "idf.ps1") -IdfArguments $idfArguments

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
    if (-not $resolvedSd.StartsWith($resolvedBuild + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace unexpected SD image: $resolvedSd"
    }
    Remove-Item -LiteralPath $resolvedSd -Force
}
$wslSd = Quote-Bash (ConvertTo-WslPath $sd)
$wslModule = Quote-Bash (ConvertTo-WslPath $module)
$wslMarker = Quote-Bash (ConvertTo-WslPath $marker)
& wsl.exe bash -lc (
    "truncate -s 64M $wslSd && " +
    "mkfs.vfat -F 32 -n D2EXIP $wslSd >/dev/null && " +
    "mmd -i $wslSd ::/HLV && " +
    "mcopy -i $wslSd $wslMarker ::/HLV/qemu.txt && " +
    "mcopy -i $wslSd $wslModule ::/ALLEY.D2E"
)
if ($LASTEXITCODE -ne 0) {
    throw "Could not create the XIP module SD-card image"
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
$expectedMarkers = @(
    "D2E_QEMU_XIP_INSTALL,file=ALLEY.D2E,result=ESP_OK",
    "D2E_MODULE_INSTALLED,command=ALLEY",
    "D2E_AUTOEXEC_CREATED,file=A:/AUTOEXEC.BAT,command=ALLEY",
    "D2E_AUTOEXEC_RUN,file=A:/AUTOEXEC.BAT",
    "D2E_AUTOEXEC_LINE,line=1,text=ALLEY",
    "D2E_MODULE_ACTIVE,command=ALLEY",
    "D2E_SHELL_RUN,command=ALLEY",
    "D2E_SHELL_RETURN,command=ALLEY,source=harness",
    "D2E_QEMU_DONE,0"
)
if ($Profile) {
    $expectedMarkers += "D2E_TRANSLATION_PROFILE,calls="
}
foreach ($expected in $expectedMarkers) {
    if (-not (Select-String -LiteralPath $log -Quiet -SimpleMatch $expected)) {
        throw "XIP QEMU check is missing '$expected'. See $log"
    }
}
Write-Host "Alley Cat XIP module QEMU run passed: $log"
