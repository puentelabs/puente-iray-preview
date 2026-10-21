# Backend permissions review for the bring-your-own DLL beta

[Español](es/backend-permissions-review-2026-10-19.md) · [Documentation](README.md)

Date: 19 October 2026. Status: technical and documentary review; this does not
constitute NVIDIA authorization to use the experimental runtime.

## What has been established

The backend used is `lisitskyaa/ComfyUI-DLSS5-NR`, commit
`41dcdfa593cb61b6a98c65bb8ed27606260bb598`, verified in the local checkout.
Its LICENSE grants MIT terms for its code. The author's notes expressly include
the bridge and helper among the author's redistributable materials, with a separate
qualification concerning runtime use. A new license from the maintainer is therefore
not missing for copying that MIT code while retaining the notices.

LICENSE, THIRD_PARTY_NOTICES, and the MIT notice for `NIGos/dlss5-bridge` incorporated
by the backend must be retained. Our code retains the Puente Labs MIT license.
Rights belonging to NVIDIA or Daz are not attributed to MIT.

The [current backend notes](https://github.com/lisitskyaa/ComfyUI-DLSS5-NR/blob/main/docs/LEGAL_NOTES.md)
recommend source code plus the author's bridge/helper, a user-provided runtime, and
experimental GitHub Releases. This describes the maintainer's position; it is not
contractual approval from NVIDIA for the integration.

## What bring-your-own DLL setup resolves

The beta excludes `nvngx_dlssnr.dll`, `_nvngx.dll`, other DLSS runtimes, driver DLLs,
the NVIDIA SDK, and Daz application files. The user supplies a compatible copy they
have the right to use. It is copied without patching into a directory with a compact
identifier and SHA-256 verification, alongside the helper. There are no automatic
downloads or links to leaked or modified copies. The NGX core comes from the installed
driver.

This resolves redistribution of those binaries on our part. It does not establish
that any DLL obtained online has a valid license, or that all runtime uses are authorized.

## Questions that remain open

| Question | Specific evidence | What remains to be resolved |
| --- | --- | --- |
| Application/project identifier | The pinned bridge uses observed IDs and feature ID 18. | Obtain a Puente Labs registration/ID or confirmation that this initialization contract is acceptable. Do not substitute an invented ID. |
| Caller verification | The helper is designed so that the call/return is attributed to its module; comments document an error when this is not done. | Clarify whether this integration is authorized and how it relates to the runtime's contractual restrictions. The helper's MIT license does not answer that question. |
| Agreement for the exact runtime | The copy used locally is user-provided; delivery of an NR SDK to Puente Labs has not been established. | Identify the applicable agreement and authorized origin of the binary; confirm use for still images, offline processing, and Daz Studio. |
| Platform/GPU | The local test uses Windows x64/RTX 4090. | Confirm authorized support for that GPU/runtime and validate other combinations before advertising them. |
| Release notice and trademarks | The public RTX/NGX license contains trademark restrictions and advance notice for commercial releases, including plugins. | Confirm applicability to this free beta. Do not assume that being free removes all obligations. Do not use logos or claim affiliation or approval. |

The [public RTX/NGX license](https://github.com/NVIDIA/DLSS/blob/main/LICENSE.txt)
restricts circumvention of limitations and authentication mechanisms. Its application
to the experimental contract and caller verification needs clarification; this document
does not present a legal conclusion of either infringement or authorization.

## Practical decision for this preparation

The beta, its repository, notices, and distribution files can be prepared and tested
locally. Documentation must keep the questions above visible. Permissions will not
be marked as resolved solely because the proprietary DLL is excluded.

The priority contact for resolving the runtime/ID/helper question is NVIDIA, through
the licensing channel identified in its own license. The maintainer can provide
technical context and any authorization received, but cannot grant rights to NVIDIA
software or contracts through MIT.

Draft inquiries were prepared separately from this repository. No messages, emails,
or issues were sent to third parties during this review.

## Other components of the Full package

The Full package retains Real-ESRGAN and CUDA PyTorch. Notices for the exact versions
of every included Python distribution are being collected. This is separate from NR
permissions. Transitive native libraries and CUDA/cuDNN notices must also be reviewed,
and both official model-weight files must be documented by URL and SHA-256. Real-ESRGAN
code uses BSD-3-Clause; the official origin of the weights is documented without
attributing a separate, unpublished license to them.
