[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,
    [string]$Name = "game",
    [string]$OutputDirectory,
    [ValidateSet("c", "xtensa-asm")]
    [string]$Backend = "c"
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$input = if ([IO.Path]::IsPathRooted($InputPath)) {
    [IO.Path]::GetFullPath($InputPath)
} else {
    [IO.Path]::GetFullPath((Join-Path $project $InputPath))
}
if (-not (Test-Path -LiteralPath $input -PathType Leaf)) {
    throw "DOS executable was not found: $input"
}
$output = if ($OutputDirectory) {
    if ([IO.Path]::IsPathRooted($OutputDirectory)) {
        [IO.Path]::GetFullPath($OutputDirectory)
    } else {
        [IO.Path]::GetFullPath((Join-Path $project $OutputDirectory))
    }
} else {
    Join-Path $project "out\generated\$Name"
}
$python = Join-Path $project "..\HLV-codec\local_tools\python\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python was not found: $python"
}

& $python (Join-Path $project "tools\d2e_build.py") $input `
    --name $Name --backend $Backend --output $output
if ($LASTEXITCODE -eq 2) {
    Write-Warning "Source generation is blocked; inspect $output\manifest.json"
    return
}
if ($LASTEXITCODE -ne 0) {
    throw "DOS executable source build failed"
}
