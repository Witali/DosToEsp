[CmdletBinding()]
param([switch]$Clean)

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
& (Join-Path $project "generate-game.ps1")
if ($Clean) {
    & (Join-Path $project "idf.ps1") fullclean
}
& (Join-Path $project "idf.ps1") build
