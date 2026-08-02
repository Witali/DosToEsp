[CmdletBinding()]
param(
    [string]$InputPath,
    [string]$ModulePath,
    [string]$ToolchainBin
)

$ErrorActionPreference = "Stop"
$project = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$commonDirectory = (& git -C $project rev-parse --path-format=absolute `
    --git-common-dir).Trim()
if ($LASTEXITCODE -ne 0 -or -not $commonDirectory) {
    throw "Could not locate the main DosToEsp repository"
}
$mainProject = Split-Path -Parent ([IO.Path]::GetFullPath($commonDirectory))
$workspace = Split-Path -Parent $mainProject
$hlvProject = Join-Path $workspace `
    "HLV-codec\firmware\esp32_2432s028_hlv_player_idf_c"
$python = Join-Path $workspace "HLV-codec\local_tools\python\python.exe"

if (-not $InputPath) {
    $InputPath = Join-Path $mainProject `
        "games\volkov-commander-4.00\VC.COM"
}
if (-not $ModulePath) {
    $ModulePath = Join-Path $project "out\modules\VC.D2E"
}
if (-not $ToolchainBin) {
    $toolchainRoot = Join-Path $hlvProject `
        ".tools\espressif\tools\xtensa-esp-elf"
    $ToolchainBin = Get-ChildItem -LiteralPath $toolchainRoot -Directory |
        Sort-Object Name -Descending | ForEach-Object {
            Join-Path $_.FullName "xtensa-esp-elf\bin"
        } | Where-Object {
            Test-Path -LiteralPath `
                (Join-Path $_ "xtensa-esp32-elf-gcc.exe") -PathType Leaf
        } | Select-Object -First 1
}

foreach ($required in @($python, $InputPath, $ToolchainBin)) {
    if (-not $required -or -not (Test-Path -LiteralPath $required)) {
        throw "Required Volkov Commander build input does not exist: $required"
    }
}

$generated = Join-Path $project "out\generated\volkov-commander"
New-Item -ItemType Directory -Force -Path (Split-Path $ModulePath -Parent) |
    Out-Null
$buildTool = Join-Path $project "tools\d2e_build.py"
$packages = Join-Path $mainProject "local_tools\python_packages"
$pythonCommand = "import runpy,sys; " +
    "sys.path.insert(0,r'$packages'); " +
    "sys.argv=[r'$buildTool',*sys.argv[1:]]; " +
    "runpy.run_path(r'$buildTool',run_name='__main__')"
& $python -c $pythonCommand $InputPath --name volkov-commander `
    --backend xtensa-c --output $generated --entry-target 0x425 `
    --entry-target 0x397 --xip-module $ModulePath `
    --xtensa-toolchain-bin $ToolchainBin --command VC `
    --title "Volkov Commander 4.00"
if ($LASTEXITCODE -ne 0) {
    throw "Volkov Commander XIP translation failed"
}

$resolvedModule = (Resolve-Path -LiteralPath $ModulePath).Path
Write-Host "Volkov Commander XIP module: $resolvedModule"
