# Beta 0.3.0-beta.1 validation

[Español](es/TESTING.md) · [Documentation](README.md)

Tests conducted on 19 October 2026 with Windows x64, Daz Studio 6.25.2026.14722,
an RTX 4090, and NVIDIA driver 617.42. Testing used a separate Daz instance with
a local application copy and the new plugin; the original installed DLL was
preserved. The private validation API was disabled.

| Workflow | Observed result |
| --- | --- |
| Bring-your-own runtime import through the method used by the button, repeated | Passed; verified copy and safe reuse. |
| New Iray render + NR + Real-ESRGAN 2x | 256×192 → 512×384. |
| Automatic Direct-to-File processing | Passed; output and render settings preserved. |
| Existing user-owned render + NR + Real-ESRGAN 2x | 1280×720 → 2560×1440. |
| Destination already exists | Rejected without overwriting. |
| Cancel 4x processing, then process again | Passed; worker stopped and recovery verified. |
| Preview, zero blend, and restart | Passed; image received and overlay removed at zero blend. |
| Isolated Full worker, without external Python | Repeatable NR 1x; NR + 2x and 4x passed. |
| Originals and alpha | SHA-256 preserved; additional test with variable alpha. |

Testing exposed a path-handling error: nesting two full hashes could push the
helper beyond MAX_PATH and produce 0xBAD00002. The same image and binaries passed
with a short path and failed with a long path. The importer now uses a 24-character
identifier, verifies both full SHA-256 hashes before reusing a directory, and
reports excessively long paths. The complete test inside Daz passed after this change.

Still pending: installation, upgrade, and uninstallation on a clean Windows system;
other GPUs and Daz/runtime/driver versions; long sessions; and more scenes. These
measurements do not guarantee image quality or rendering-time savings. The user
images, private Daz copies, and logs containing local paths used for these tests
are not included in this repository.
