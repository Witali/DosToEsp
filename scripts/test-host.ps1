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
$siblingPython = Join-Path $sibling "local_tools\python\python.exe"
$python = if (Test-Path -LiteralPath $siblingPython -PathType Leaf) {
    $siblingPython
} else {
    Find-Tool "python.exe" @()
}
$capstone = Join-Path $project "local_tools\python_packages\capstone\__init__.py"
if (-not (Test-Path -LiteralPath $capstone -PathType Leaf)) {
    & (Join-Path $PSScriptRoot "setup-analysis-tools.ps1")
}
& $python (Join-Path $project "tests\test_analysis.py")
if ($LASTEXITCODE -ne 0) { throw "Static inventory tests failed" }
& $python (Join-Path $project "tests\test_trace.py")
if ($LASTEXITCODE -ne 0) { throw "Reference trace tests failed" }
& $python (Join-Path $project "tests\test_coverage.py")
if ($LASTEXITCODE -ne 0) { throw "Translator coverage tests failed" }
& $python (Join-Path $project "tests\test_build.py")
if ($LASTEXITCODE -ne 0) { throw "Unified source build tests failed" }
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

$configureArguments = @(
    "-S", $project,
    "-B", $build,
    "-G", "Ninja",
    "-DCMAKE_MAKE_PROGRAM=$ninja",
    "-DCMAKE_C_COMPILER=$compiler",
    "-DD2E_PYTHON=$python",
    "-DCMAKE_BUILD_TYPE=Debug"
)
$alleyCat = Join-Path $project "games\Alley-Cat_DOS_EN\alley-cat\CAT.EXE"
if (Test-Path -LiteralPath $alleyCat -PathType Leaf) {
    $configureArguments += "-DD2E_ALLEY_CAT_EXE=$alleyCat"
}
& $cmake @configureArguments
if ($LASTEXITCODE -ne 0) { throw "CMake configure failed" }

& $cmake --build $build
if ($LASTEXITCODE -ne 0) { throw "Host build failed" }

& (Join-Path $build "d2e_core_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "Host tests failed" }

& (Join-Path $build "d2e_cga_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "CGA tests failed" }

& (Join-Path $build "d2e_pc_at_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "PC/AT BIOS tests failed" }

& (Join-Path $build "d2e_loader_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "MZ loader tests failed" }

& (Join-Path $build "d2e_native_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "Native translation tests failed" }

& (Join-Path $build "d2e_native_memory_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "Native ModR/M memory tests failed" }

& (Join-Path $build "d2e_native_call_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "Native stack/call tests failed" }

& (Join-Path $build "d2e_native_logic_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "Native boolean/flag tests failed" }

& (Join-Path $build "d2e_native_shift_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "Native shift/rotate tests failed" }

& (Join-Path $build "d2e_native_string_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "Native string/REP tests failed" }

& (Join-Path $build "d2e_native_port_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "Native port-boundary tests failed" }

& (Join-Path $build "d2e_native_rare_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "Native rare-instruction tests failed" }

& (Join-Path $build "d2e_native_indirect_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "Native indirect jump-table tests failed" }

& (Join-Path $build "d2e_native_adc_flags_tests.exe")
if ($LASTEXITCODE -ne 0) { throw "Native ADC/flags-stack tests failed" }

$mzImageTest = Join-Path $build "d2e_mz_image_tests.exe"
if (Test-Path -LiteralPath $mzImageTest -PathType Leaf) {
    & $mzImageTest
    if ($LASTEXITCODE -ne 0) { throw "Generated Alley Cat MZ image test failed" }
}
