[CmdletBinding()]
param([switch]$Clean)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$build = Join-Path $project "build-host"

function Find-Tool([string]$Name, [string[]]$Fallbacks) {
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($command) {
        return $command.Source
    }
    foreach ($candidate in $Fallbacks) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    throw "Required tool was not found: $Name"
}

$sibling = Join-Path $project "..\HLV-codec"
$cmake = Find-Tool "cmake.exe" @(
    (Join-Path $sibling "firmware\esp32_2432s028_hlv_player_idf_c\.tools\espressif\tools\cmake\3.30.2\bin\cmake.exe")
)
$ninja = Find-Tool "ninja.exe" @(
    (Join-Path $sibling "firmware\esp32_2432s028_hlv_player_idf_c\.tools\espressif\tools\ninja\1.12.1\ninja.exe"),
    (Join-Path $sibling "local_tools\msys2\msys64\mingw64\bin\ninja.exe")
)
$compiler = $null
$vswhere = Join-Path ${env:ProgramFiles(x86)} `
    "Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path -LiteralPath $vswhere -PathType Leaf) {
    $vsRoot = & $vswhere -latest -products * `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
        -property installationPath
    if ($vsRoot) {
        $devShell = Join-Path $vsRoot "Common7\Tools\Launch-VsDevShell.ps1"
        if (Test-Path -LiteralPath $devShell -PathType Leaf) {
            . $devShell -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
            $compiler = (Get-Command "cl.exe" -CommandType Application |
                Select-Object -First 1 -ExpandProperty Source)
        }
    }
}
if (-not $compiler) {
    $compiler = Find-Tool "gcc.exe" @(
        (Join-Path $sibling "local_tools\msys2\msys64\mingw64\bin\gcc.exe")
    )
}

if ($Clean -and (Test-Path -LiteralPath $build)) {
    $resolvedProject = [IO.Path]::GetFullPath($project)
    $resolvedBuild = [IO.Path]::GetFullPath($build)
    $expectedBuild = Join-Path $resolvedProject "build-host"
    if (-not $resolvedBuild.Equals(
            $expectedBuild, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove unexpected directory: $resolvedBuild"
    }
    Remove-Item -LiteralPath $resolvedBuild -Recurse -Force
}

& $cmake -S $project -B $build -G Ninja `
    "-DCMAKE_MAKE_PROGRAM=$ninja" `
    "-DCMAKE_C_COMPILER=$compiler" `
    "-DCMAKE_BUILD_TYPE=Debug"
if ($LASTEXITCODE -ne 0) { throw "CMake configure failed" }

& $cmake --build $build
if ($LASTEXITCODE -ne 0) { throw "Host build failed" }

& (Join-Path $build "d2e_core_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "Host tests failed" }
