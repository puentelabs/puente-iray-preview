# Puente Iray Preview 0.3.0-beta.1 — draft

A free experimental plugin from Puente Labs for exploring neural Iray previews
and processing renders inside Daz Studio 6 on Windows x64, with optional
Real-ESRGAN 2x/4x upscaling.

## What this beta is being prepared to include

- A compiled Daz Studio plugin and a Full worker with Python and its dependencies
  packaged together, without selecting an external Python environment or using ComfyUI.
- Neural preview, render processing, automatic Direct-to-File processing, and
  processing of existing images.
- Bring-your-own NVIDIA NR runtime setup through **Importar DLL NR...**
  (Import NR DLL), using a compatible copy the user has the right to use.

The package excludes the NVIDIA NR runtime and driver DLLs. The Full worker does
include PyTorch CUDA libraries and Real-ESRGAN models.

## Validation scope

Tested with Daz Studio **6.25.2026.14722**, an **RTX 4090**, NVIDIA driver
**617.42**, and Windows x64. Bring-your-own runtime import, preview, render and
processing, Direct-to-File, existing-image processing, cancellation, and recovery
passed testing. Only this configuration is verified. Keep a backup of the previous
installation. These results do not establish compatibility with other GPUs or
Daz versions, or general equivalence to gaming DLSS.

## Release status

**Source code is public; the packaged beta is not yet generally available.**
This release remains a draft while runtime, initialization IDs, and helper
permissions are resolved and the final review of Full-worker native-library and
model-weight licenses is completed. Bring-your-own runtime setup does not imply
NVIDIA approval.

See the [README](README.md), [testing record](docs/TESTING.md), and
[backend permissions review](docs/backend-permissions-review-2026-10-19.md).
