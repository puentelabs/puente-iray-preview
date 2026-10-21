# Installation — beta 0.3.0-beta.1 in preparation

[Español](es/installation-draft.md) · [Documentation](README.md)

The DLL passed integration testing with Daz Studio 6.25.2026.14722, Windows x64,
an RTX 4090, and driver 617.42. The package remains a draft because of the documented
permissions questions. Do not replace a working plugin during an active session.

1. Save your work and close Daz Studio.
2. If Puente Iray Preview is already installed, back up its DLL and supporting
   folder before upgrading.
3. Copy the package's `plugins/` contents into the `plugins/` directory of the
   correct Daz Studio installation. Keep the DLL and `PuenteIrayPreview` directory
   together; do not extract only the DLL.
4. Open Daz and the **Puente Iray Preview** pane.
5. In settings, use **Importar DLL NR...** (Import NR DLL) to select a compatible
   `nvngx_dlssnr.dll` that you have the right to use. The plugin prepares a verified
   copy with the included helper. Each combination is stored in its own directory;
   the original is not changed and no DLL is downloaded.
6. Start the preview or process a render. Missing-component diagnostics appear
   before rendering starts. For Real-ESRGAN, use the Full package; no separate
   installation of Python, Conda, ComfyUI, or packages is needed.

To check only the package, run `puente-worker.exe check`. Passing this diagnostic
does not, by itself, establish NR compatibility with the GPU; that is checked when
processing an image.

To roll back, close Daz and restore the backed-up DLL and supporting folder.
Original renders and imported runtimes remain outside the application directory.
Removing the plugin does not remove those files.

Runtime import, rendering/processing, Direct-to-File, existing-image processing,
cancellation, and preview were verified in a separate Daz instance with this DLL.
Installation, upgrade, and uninstallation testing on a clean Windows system is
still pending. The original installation was preserved during testing.
