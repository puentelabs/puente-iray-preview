param(
    [Parameter(Mandatory=$true)][string]$SdkRoot,
    [string]$Qt6Dir,
    [string]$BuildDirectory,
    [switch]$ValidationApi
)
$ErrorActionPreference = 'Stop'
$prototypeRoot = Split-Path -Parent $PSScriptRoot
if (!$Qt6Dir) { $Qt6Dir = Join-Path $prototypeRoot 'artifacts\qt\6.10.3\msvc2022_64\lib\cmake\Qt6' }
if (!$BuildDirectory) { $BuildDirectory = Join-Path $prototypeRoot 'artifacts\daz6-render-release' }
if (!(Test-Path -LiteralPath (Join-Path $SdkRoot 'include\dzversion.h'))) { throw 'Set SdkRoot to the official Studio 6 SDK matching your Daz application.' }
if (!(Test-Path -LiteralPath (Join-Path $Qt6Dir 'Qt6Config.cmake'))) { throw 'Set Qt6Dir to the Qt 6.10.3 MSVC 2022 x64 development kit cmake/Qt6 folder.' }
$validationOption = if ($ValidationApi) { 'ON' } else { 'OFF' }
& cmake -S $PSScriptRoot -B $BuildDirectory -A x64 "-DDAZ_SDK_DIR=$SdkRoot" "-DQt6_DIR=$Qt6Dir" "-DPUENTE_ENABLE_VALIDATION_API=$validationOption"
if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed.' }
& cmake --build $BuildDirectory --config Release
if ($LASTEXITCODE -ne 0) { throw 'Plugin build failed.' }
$builtPlugin = Join-Path $BuildDirectory 'Release\dsp_PuenteIrayPreview.dll'
Write-Output ("Built {0} ({1} bytes)" -f $builtPlugin,(Get-Item -LiteralPath $builtPlugin).Length)
Write-Output ("SHA-256: {0}" -f (Get-FileHash -LiteralPath $builtPlugin -Algorithm SHA256).Hash)
