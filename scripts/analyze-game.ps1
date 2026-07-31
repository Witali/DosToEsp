[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,
    [string]$Name = "alley-cat",
    [ValidateSet("auto", "com", "mz", "raw")]
    [string]$Format = "auto",
    [switch]$HexInput
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$input = if ([IO.Path]::IsPathRooted($InputPath)) {
    [IO.Path]::GetFullPath($InputPath)
} else {
    [IO.Path]::GetFullPath((Join-Path $project $InputPath))
}
if (-not (Test-Path -LiteralPath $input -PathType Leaf)) {
    throw "Game image was not found: $input"
}

$siblingPython = Join-Path $project "..\HLV-codec\local_tools\python\python.exe"
$python = if (Test-Path -LiteralPath $siblingPython -PathType Leaf) {
    $siblingPython
} else {
    (Get-Command python.exe -CommandType Application |
        Select-Object -First 1 -ExpandProperty Source)
}
$capstone = Join-Path $project "local_tools\python_packages\capstone\__init__.py"
if (-not (Test-Path -LiteralPath $capstone -PathType Leaf)) {
    & (Join-Path $PSScriptRoot "setup-analysis-tools.ps1")
}

$output = Join-Path $project "out\analysis"
$arguments = @(
    (Join-Path $project "tools\d2e_analyze.py"),
    $input,
    "--format", $Format,
    "--json", (Join-Path $output "$Name.json"),
    "--markdown", (Join-Path $output "$Name.md")
)
if ($HexInput) {
    $arguments += "--hex-input"
}
& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Static game analysis failed"
}
