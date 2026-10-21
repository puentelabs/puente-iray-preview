# Third-party components

[Español](docs/es/THIRD_PARTY_NOTICES.md)

The root MIT license covers Puente Labs code, not third-party SDKs, applications,
drivers, runtimes, or models.

- Reference backend: [ComfyUI-DLSS5-NR](https://github.com/lisitskyaa/ComfyUI-DLSS5-NR),
  commit `41dcdfa593cb61b6a98c65bb8ed27606260bb598`, MIT. The package retains the
  backend's LICENSE and THIRD_PARTY_NOTICES, including the NIGos/dlss5-bridge notice.
- The NVIDIA NR runtime and driver are not included. Rights to those components
  are separate.
- The worker includes Python, NumPy, Pillow, and, in Full, PyTorch/torchvision,
  spandrel, and dependencies. Each package retains the exact notices under
  `plugins/PuenteIrayPreview/licenses/` and an inventory of versions and licenses.
- PyInstaller uses its bootloader exception; COPYING is retained.
- [spandrel](https://github.com/chaiNNer-org/spandrel) uses MIT, copyright 2024
  The ChaiNNer Organization.
- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) publishes its code under
  BSD-3-Clause, copyright 2021 Xintao Wang. The Full model weights come from the
  official x2plus v0.2.1 and x4plus v0.1.0 releases, with SHA-256 hashes pinned in
  `src/render_worker.py`. No separate, unpublished license is attributed to the
  weights; the exact terms remain under review.

The Daz SDK and application and the Qt development kit are not redistributed here.
The review of Full's transitive native-library licenses and permissions for the
NR/IDs/helper contract remains open. This notice does not declare that review complete.
