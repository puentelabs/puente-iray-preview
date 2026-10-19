param(
    [Parameter(Mandatory=$true)][string]$RuntimeDll,
    [string]$Destination = (Join-Path $env:LOCALAPPDATA 'PuenteLabs\IrayPreview\runtime')
)
# El usuario aporta una copia compatible que tiene derecho a utilizar.
# No modifica el DLL ni descarga binarios de terceros.
$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $RuntimeDll -PathType Leaf) -or [IO.Path]::GetFileName($RuntimeDll) -ne 'nvngx_dlssnr.dll') {
    throw 'Selecciona tu nvngx_dlssnr.dll compatible.'
}
$caller = Join-Path $PSScriptRoot 'backend\nvngx.dll_comfy.dll'
if (!(Test-Path -LiteralPath $caller)) { throw 'Falta el helper del paquete. Conserva toda la carpeta del plugin.' }
if (Test-Path -LiteralPath $Destination) { throw 'La carpeta ya existe. Usa otro destino para conservar el runtime anterior.' }
New-Item -ItemType Directory -Path (Join-Path $Destination 'caller') -Force | Out-Null
Copy-Item -LiteralPath $RuntimeDll -Destination (Join-Path $Destination 'nvngx_dlssnr.dll')
Copy-Item -LiteralPath $caller -Destination (Join-Path $Destination 'caller\nvngx.dll_comfy.dll')
if ((Get-FileHash -LiteralPath $RuntimeDll -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath (Join-Path $Destination 'nvngx_dlssnr.dll') -Algorithm SHA256).Hash) { throw 'La copia no coincide con el original.' }
Write-Output "Runtime copiado sin modificaciones a $Destination. Selecciona esa carpeta en el plugin."
