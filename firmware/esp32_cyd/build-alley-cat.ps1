[CmdletBinding()]
param([switch]$Clean)

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
$build = "build-alley-cat"

& (Join-Path $project "generate-game.ps1") -AlleyCat
if ($Clean) {
    & (Join-Path $project "idf.ps1") -IdfArguments @(
        "-B", $build, "fullclean"
    )
}
& (Join-Path $project "idf.ps1") -IdfArguments @(
    "-B", $build,
    "-D", "D2E_ALLEY_CAT=ON",
    "-D", "D2E_SHELL=ON",
    "-D", "D2E_SHELL_AUTORUN=OFF",
    "-D", "D2E_QEMU_EXIT_AFTER_RETURN=OFF",
    "build"
)
