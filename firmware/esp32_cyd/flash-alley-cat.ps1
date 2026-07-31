[CmdletBinding()]
param(
    [string]$Port = "COM8",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
if (-not $SkipBuild) {
    & (Join-Path $project "build-alley-cat.ps1")
}
& (Join-Path $project "idf.ps1") -IdfArguments @(
    "-B", "build-alley-cat", "-p", $Port, "flash"
)
