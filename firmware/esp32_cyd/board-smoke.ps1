[CmdletBinding()]
param(
    [string]$Port = "COM8",
    [int[]]$Baud
)

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
$toolProject = [IO.Path]::GetFullPath((Join-Path $project `
    "..\..\..\HLV-codec\firmware\esp32_2432s028_hlv_player_idf_c"))
$idfPython = Join-Path $toolProject `
    ".tools\espressif\python_env\idf5.5_py3.11_env\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $idfPython -PathType Leaf)) {
    & (Join-Path $project "idf.ps1") -IdfArguments @("--version")
}

$arguments = @((Join-Path $project "board-smoke.py"), "--port", $Port)
foreach ($rate in $Baud) {
    $arguments += @("--baud", $rate.ToString())
}
& $idfPython @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Board smoke test failed"
}
