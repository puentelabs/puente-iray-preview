# Construcción local

El SDK de Daz y Qt deben obtenerse por sus canales oficiales y con sus licencias.
No se incluyen SDK, cabeceras ni bibliotecas de Daz en el repositorio.

```powershell
cmake -S src/daz-plugin -B build/plugin -A x64 `
  "-DDAZ_SDK_DIR=<SDK de Daz Studio 6>" "-DQt6_DIR=<Qt6/lib/cmake/Qt6>" `
  -DPUENTE_ENABLE_VALIDATION_API=OFF -DPUENTE_PACKAGED_ONLY=ON
cmake --build build/plugin --config Release
```

El backend de referencia es `lisitskyaa/ComfyUI-DLSS5-NR`, commit
`41dcdfa593cb61b6a98c65bb8ed27606260bb598`. Preparar su bridge/helper propios
siguiendo sus instrucciones y conservar sus avisos. El builder no copia el NR.
Un Python de construcción Full necesita PyTorch CUDA, spandrel, NumPy, Pillow,
optree y sus dependencias; PyInstaller 6.22.3 puede residir en carpeta separada.
El inventario de versiones exactas se guarda en cada paquete generado.

```powershell
./tools/build-package.ps1 -Python '<Python CUDA de construcción>' `
  -PluginDll 'build/plugin/Release/dsp_PuenteIrayPreview.dll' `
  -BackendRoot '<checkout fijado del backend>' -BuildTools '<PyInstaller>' `
  -Profile Full -ModelDirectory '<modelos oficiales>' `
  -OutputDirectory 'dist/candidato-nuevo'
```

El perfil Core solo contiene NR + Lanczos. Full conserva Real-ESRGAN. Recoger
las licencias exactas con `tools/collect-runtime-licenses.py`, incluir los avisos
complementarios de spandrel y Real-ESRGAN, revisar las bibliotecas nativas
transitivas y actualizar el manifiesto con `tools/finalize-candidate.py`.
Un manifiesto generado no constituye por sí mismo autorización de publicación.

Validar el worker real desde una carpeta vacía:

```powershell
python -B tools/validate-candidate.py --package dist/candidato-nuevo `
  --input '<render propio.png>' --runtime '<runtime NR del usuario>' `
  --output evidence/prueba-nueva --neural
```

Repetir la integración en una instancia propia de Daz al cambiar la DLL nativa.
Nunca reemplazarla con Daz en ejecución.
