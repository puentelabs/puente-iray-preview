param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$PluginDll,
    [Parameter(Mandatory=$true)][string]$BackendRoot,
    [string]$BuildTools,
    [ValidateSet('Core','Full')][string]$Profile = 'Core',
    [string]$ModelDirectory,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
# Construye un candidato local. No instala ni publica; nunca copia el runtime NVIDIA.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'El destino ya existe. Usa una carpeta nueva.' }
$bridge = Join-Path $BackendRoot 'native\bin\dlss5nr_bridge.dll'
$caller = Join-Path $BackendRoot 'runtime\caller\nvngx.dll_comfy.dll'
foreach($file in @($Python,$PluginDll,$bridge,$caller,(Join-Path $BackendRoot 'LICENSE'),(Join-Path $BackendRoot 'THIRD_PARTY_NOTICES.md'))) {
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw "Falta el componente de construcción: $file" }
}
$stamp = [guid]::NewGuid().ToString('N')
$build = Join-Path $root "build\freezer-$stamp"
$runtimeDependencies = & $Python -B (Join-Path $PSScriptRoot 'runtime-dependencies.py') --profile $Profile
if ($LASTEXITCODE -ne 0) { throw 'No se pudo resolver el inventario de dependencias del runtime.' }
$dependencyInfo = $runtimeDependencies | ConvertFrom-Json
$arguments = @('--noconfirm','--onedir','--console','--noupx','--name','puente-worker',
    '--distpath',(Join-Path $build 'dist'),'--workpath',(Join-Path $build 'work'),
    '--specpath',$build,'--paths',(Join-Path $root 'src'),
    '--hidden-import','render_worker','--hidden-import','viewport_worker',
    '--copy-metadata','numpy','--copy-metadata','Pillow')
# PyTorch explora backends opcionales presentes en entornos grandes. Ninguno de
# estos módulos forma parte del pipeline RRDB/NR; no arrastrar ComfyUI completo.
foreach($module in @('tensorflow','keras','transformers','diffusers','onnx','onnxruntime','onnxscript',
    'tensorboard','IPython','jupyter','matplotlib','pandas','cv2','torchaudio','scipy','sklearn')) {
    $arguments += @('--exclude-module',$module)
}
foreach($module in $dependencyInfo.exclude_modules) { $arguments += @('--exclude-module',$module) }
if ($Profile -eq 'Full') {
    & $Python -B -c 'import torch,spandrel; assert torch.cuda.is_available(), "Se necesita PyTorch CUDA"'
    if ($LASTEXITCODE -ne 0) { throw 'El Python de construcción no tiene PyTorch CUDA + spandrel. No se modifica ese entorno.' }
    if (!$ModelDirectory) { throw 'Full requiere los dos modelos oficiales en ModelDirectory.' }
    $modelHashes = @{
        'RealESRGAN_x2plus.pth' = '49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb'
        'RealESRGAN_x4plus.pth' = '4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1'
    }
    foreach($name in $modelHashes.Keys) {
        $model = Join-Path $ModelDirectory $name
        if (!(Test-Path -LiteralPath $model) -or (Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash -ne $modelHashes[$name]) { throw "Modelo oficial ausente o inválido: $name" }
    }
    $arguments += @('--collect-all','spandrel','--copy-metadata','spandrel','--copy-metadata','torch')
} else {
    $arguments += @('--exclude-module','torch','--exclude-module','spandrel')
}
$arguments += (Join-Path $root 'src\puente_worker.py')
# sys.path solo afecta al proceso de construcción; no cambia PATH ni el Python instalado.
& $Python -B -c 'import runpy,sys; tools=sys.argv.pop(1); sys.path.insert(0,tools) if tools else None; runpy.run_module("PyInstaller",run_name="__main__")' $BuildTools @arguments
if ($LASTEXITCODE -ne 0) { throw 'Falló el empaquetado del worker. Se conservan los diagnósticos.' }
$pluginFolder = Join-Path $output 'plugins'
$support = Join-Path $pluginFolder 'PuenteIrayPreview'
New-Item -ItemType Directory -Path $support -Force | Out-Null
Copy-Item -LiteralPath $PluginDll -Destination (Join-Path $pluginFolder 'dsp_PuenteIrayPreview.dll')
Get-ChildItem -LiteralPath (Join-Path $build 'dist\puente-worker') -Force | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $support -Recurse }
New-Item -ItemType Directory -Path (Join-Path $support 'backend') | Out-Null
Copy-Item -LiteralPath $bridge,$caller -Destination (Join-Path $support 'backend')
$licenses = Join-Path $support 'licenses'
New-Item -ItemType Directory -Path $licenses | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'src\LICENSE') -Destination (Join-Path $licenses 'Puente-Labs-MIT.txt')
Copy-Item -LiteralPath (Join-Path $BackendRoot 'LICENSE') -Destination (Join-Path $licenses 'ComfyUI-DLSS5-NR-MIT.txt')
Copy-Item -LiteralPath (Join-Path $BackendRoot 'THIRD_PARTY_NOTICES.md') -Destination (Join-Path $licenses 'Backend-notices.md')
$pythonLicense = & $Python -B -c 'from pathlib import Path; import sys; p=Path(sys.base_prefix)/"LICENSE.txt"; print(p if p.is_file() else "")'
if (!$pythonLicense -or !(Test-Path -LiteralPath $pythonLicense)) { throw 'No se encontró la licencia del Python de construcción.' }
Copy-Item -LiteralPath $pythonLicense -Destination (Join-Path $licenses 'Python-LICENSE.txt')
if ($BuildTools) {
    $freezerLicense = Join-Path $BuildTools 'pyinstaller-6.22.3.dist-info\licenses\COPYING.txt'
    if (!(Test-Path -LiteralPath $freezerLicense)) { throw 'Falta el aviso de PyInstaller con su excepción de bootloader.' }
} else {
    $freezerLicense = & $Python -B -c 'import importlib.metadata as m; d=m.distribution("PyInstaller"); print(next(d.locate_file(f) for f in d.files if str(f).endswith("licenses/COPYING.txt")))'
}
Copy-Item -LiteralPath $freezerLicense -Destination (Join-Path $licenses 'PyInstaller-COPYING.txt')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'configure-runtime.ps1') -Destination $support
Copy-Item -LiteralPath (Join-Path $root 'docs\installation-draft.md') -Destination (Join-Path $output 'LEEME.md')
$dependencyInfo.pins | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $output 'runtime-dependencies.json') -Encoding utf8
if ($Profile -eq 'Full') {
    $models = Join-Path $support 'runtime\upscale'
    New-Item -ItemType Directory -Path $models -Force | Out-Null
    foreach($name in $modelHashes.Keys) { Copy-Item -LiteralPath (Join-Path $ModelDirectory $name) -Destination $models }
    # Preservar también fuentes/extensión/metadatos de la dependencia dinámica
    # comprobada durante la validación; no depender solo del análisis de imports.
    & $Python -B (Join-Path $PSScriptRoot 'stage-runtime-dependency.py') --distribution optree --package $output
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo incluir optree en el runtime Full.' }
}
$worker = Join-Path $support 'puente-worker.exe'
& $worker check
if ($LASTEXITCODE -ne 0) { throw 'El worker empaquetado no pasó el diagnóstico básico.' }
$manifest = [ordered]@{version='0.3.0-preparation';profile=$Profile;public_release_ready=$false;nvidia_nr_runtime_included=$false;files=@()}
$forbidden = @(Get-ChildItem -LiteralPath $output -File -Recurse | Where-Object { $_.Name -match '^(?:_nvngx|nvngx_dlss(?:nr|d|g)?|nvofapi64|nvcuda)\.dll$' })
if ($forbidden.Count) { throw ('Se detectaron runtimes/driver fuera del paquete permitido: ' + ($forbidden.Name -join ', ')) }
$manifest.files = @(Get-ChildItem -LiteralPath $output -File -Recurse | Sort-Object FullName | ForEach-Object {
    [ordered]@{path=[IO.Path]::GetRelativePath($output,$_.FullName).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
})
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output 'manifest.json') -Encoding utf8
Write-Output "Candidato local creado: $output. La validación GPU/Daz y los avisos de terceros siguen siendo necesarios."
