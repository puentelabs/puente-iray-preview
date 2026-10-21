# Building locally

[Español](es/BUILD.md) · [Documentation](README.md)

Obtain the Daz SDK and Qt through their official channels and under their respective
licenses. Daz SDK files, headers, and libraries are not included in this repository.

```powershell
cmake -S src/daz-plugin -B build/plugin -A x64 `
  "-DDAZ_SDK_DIR=<Daz Studio 6 SDK>" "-DQt6_DIR=<Qt6/lib/cmake/Qt6>" `
  -DPUENTE_ENABLE_VALIDATION_API=OFF -DPUENTE_PACKAGED_ONLY=ON
cmake --build build/plugin --config Release
```

The reference backend is `lisitskyaa/ComfyUI-DLSS5-NR`, commit
`41dcdfa593cb61b6a98c65bb8ed27606260bb598`, verified in the local checkout.
Prepare its bridge and helper following its instructions and retain its notices.
The builder does not copy the NR runtime. A Full build environment needs Python
with PyTorch CUDA, spandrel, NumPy, Pillow, optree, and their dependencies.
PyInstaller 6.22.3 may be kept in a separate directory. An inventory of exact
versions is saved in each generated package.

```powershell
./tools/build-package.ps1 -Python '<build-time CUDA Python>' `
  -PluginDll 'build/plugin/Release/dsp_PuenteIrayPreview.dll' `
  -BackendRoot '<pinned backend checkout>' -BuildTools '<PyInstaller>' `
  -Profile Full -ModelDirectory '<official models>' `
  -OutputDirectory 'dist/new-candidate'
```

The Core profile contains only NR + Lanczos. Full retains Real-ESRGAN. Collect
the exact licenses with `tools/collect-runtime-licenses.py`, include supplementary
spandrel and Real-ESRGAN notices, review transitive native libraries, and update
the manifest with `tools/finalize-candidate.py`. A generated manifest does not,
by itself, authorize publication.

Validate the actual worker from an empty directory:

```powershell
python -B tools/validate-candidate.py --package dist/new-candidate `
  --input '<your-own-render.png>' --runtime '<user-provided NR runtime>' `
  --output evidence/new-test --neural
```

Repeat integration testing in a separate Daz instance whenever the native DLL
changes. Never replace it while Daz is running.
