"""Disposable still-render postprocessor. Offline; original files are read only.

Runs current NR controls first, then optional 2x/4x Lanczos or tiled
Real-ESRGAN. Neural enlargement is separate from the NR runtime's 1x effect.
Only explicitly pinned official weights are loaded, with weights_only=True.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))  # Embedded CUDA Python omits the script folder.
import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageOps

from prototype import ROOT, sha256
from viewport_worker import request, terminate_self
from packaged_runtime import worker_command

MODELS = {
    2: ("RealESRGAN_x2plus.pth", "49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb",
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth"),
    4: ("RealESRGAN_x4plus.pth", "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1",
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"),
}
MAX_PIXELS = 32 * 1024 * 1024


def progress(message):
    print(message, flush=True)


def load_render(path):
    with Image.open(path) as source:
        if source.format not in ("PNG", "TIFF") or getattr(source, "n_frames", 1) != 1:
            raise ValueError("Use a single-frame PNG or TIFF render")
        if source.mode not in ("RGB", "RGBA", "P"):
            raise ValueError("Use an 8-bit RGB/RGBA render; keep HDR masters separately")
        if source.format == "PNG":
            with Path(path).open("rb") as stream:
                if stream.read(29)[24] != 8:
                    raise ValueError("16-bit/HDR PNG is not supported; export an 8-bit sRGB copy")
        else:
            bits = source.tag_v2.get(258, (8,))
            if isinstance(bits, int):
                bits = (bits,)
            if any(v != 8 for v in bits):
                raise ValueError("16-bit/HDR TIFF is not supported; export an 8-bit sRGB copy")
        if source.width * source.height > MAX_PIXELS or max(source.size) > 8192:
            raise ValueError("Input exceeds the alpha's 32 MP / 8192-pixel side limit")
        image = ImageOps.exif_transpose(source).convert("RGBA")
        conversion = "assumed sRGB"
        if source.info.get("icc_profile"):
            profile = ImageCms.ImageCmsProfile(io.BytesIO(source.info["icc_profile"]))
            rgb = ImageCms.profileToProfile(image.convert("RGB"), profile,
                                           ImageCms.createProfile("sRGB"), outputMode="RGB")
            rgb.putalpha(image.getchannel("A")); image = rgb
            conversion = "embedded ICC converted to sRGB"
        elif "gamma" in source.info and abs(source.info["gamma"] - 0.45455) > 0.002:
            raise ValueError("Non-sRGB PNG gamma; export an sRGB copy first")
        return image.copy(), conversion


def resize_rgba(image, size):
    if size == image.size:
        return image.copy()
    # Premultiplied resampling prevents invisible RGB bleeding into silhouettes.
    return image.convert("RGBa").resize(size, Image.Resampling.LANCZOS).convert("RGBA")


def enhance_nr(image, job):
    if max(image.size) > 4096:
        raise ValueError("NR enhancement currently accepts up to 4096 pixels per side; disable it for larger input")
    controls = job.get("controls", {})
    fields = [1, controls.get("style", 1), 3, controls.get("tone", 0), controls.get("structure", 1),
              controls.get("skin", -1), int(controls.get("auto_mask", False)), controls.get("blend", 1)]
    request("\t".join(map(str, fields)))
    with tempfile.TemporaryDirectory(prefix="PuenteRenderNR-") as folder:
        session = Path(folder)
        np.asarray(image).tofile(session / "frame.rgba")
        command = worker_command("viewport") + ["--session", folder,
                   "--runtime", str(job["runtime"]), "--transport", "rgba", "--parent-pid", str(os.getpid())]
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as child:
            try:
                protocol = "\t".join(map(str, fields + list(image.size))) + "\nQUIT\n"
                stdout, stderr = child.communicate(protocol, timeout=90)
            except BaseException:
                child.kill(); child.wait(timeout=5); raise
        if child.returncode != 0 or "OK\t1\t" not in stdout:
            raise RuntimeError("NR worker failed: " + (stdout + stderr)[-2048:])
        pixels = np.fromfile(session / "enhanced.rgba", dtype=np.uint8).reshape(image.height, image.width, 4)
        result = Image.fromarray(pixels)
        info = json.loads((session / "latest-report.json").read_text(encoding="utf-8"))
        return result, info


def upscale_neural(image, scale, model_dir, strength=0.5, tile=192, progress_fn=progress):
    try:
        import torch
        from spandrel import ImageModelDescriptor, ModelLoader
    except ModuleNotFoundError as exc:
        raise RuntimeError(f"GPU Python {sys.executable} is missing {exc.name}. "
                           "Set GPU Python in Render output to an executable with CUDA PyTorch and spandrel.") from exc

    if not torch.cuda.is_available():
        raise RuntimeError("Neural upscaling needs a CUDA-enabled PyTorch + spandrel Python. Set GPU Python under Render output.")
    name, expected_hash, url = MODELS[scale]
    weights = Path(model_dir) / name
    if not weights.is_file() or sha256(weights) != expected_hash:
        raise ValueError(f"Missing or mismatched official weights: {weights}. Run bootstrap-upscale.ps1.")
    state_dict = torch.load(weights, map_location="cpu", weights_only=True)
    model = ModelLoader().load_from_state_dict(state_dict)
    if not isinstance(model, ImageModelDescriptor) or model.scale != scale or model.input_channels != 3:
        raise ValueError("Unexpected upscaler architecture or scale")
    model = model.to(device="cuda")
    half = model.supports_half
    if half:
        model = model.half()
    model.eval()
    rgba = np.asarray(image).copy()
    alpha = rgba[..., 3:4].astype(np.float32) / 255
    source = np.ascontiguousarray(rgba[..., :3].astype(np.float32) / 255 * alpha + 0.5 * (1 - alpha))
    height, width = source.shape[:2]
    output = np.empty((height * scale, width * scale, 3), dtype=np.uint8)
    pad = 32
    total = math.ceil(width / tile) * math.ceil(height / tile)
    count = 0
    with torch.inference_mode():
        for y in range(0, height, tile):
            for x in range(0, width, tile):
                # x2 pixel-unshuffle requires the same even pixel phase for every tile.
                left, top = max(0, x - pad), max(0, y - pad)
                right, bottom = min(width, x + tile + pad), min(height, y + tile + pad)
                tensor = torch.from_numpy(source[top:bottom, left:right].transpose(2, 0, 1).copy()).unsqueeze(0)
                tensor = tensor.to(device="cuda", dtype=torch.float16 if half else torch.float32)
                inferred = model(tensor)
                if not torch.isfinite(inferred).all():
                    raise RuntimeError("Neural upscaler returned NaN/Inf")
                cropped = inferred[0, :, (y-top)*scale:(min(y+tile, height)-top)*scale,
                                   (x-left)*scale:(min(x+tile, width)-left)*scale]
                pixels = cropped.float().clamp(0, 1).mul(255).round().byte().permute(1, 2, 0).cpu().numpy()
                output[y*scale:min(y+tile,height)*scale, x*scale:min(x+tile,width)*scale] = pixels
                count += 1
                progress_fn(f"Neural upscale tile {count}/{total}")
                del inferred, tensor, cropped
    baseline = np.asarray(resize_rgba(image, (width * scale, height * scale))).copy()
    # Edges, alpha and soft shadows retain the premultiplied resize baseline.
    coverage = np.clip((baseline[..., 3:4].astype(np.float32) / 255 - 0.9) / 0.1, 0, 1) * strength
    baseline[..., :3] = np.rint(baseline[..., :3] + coverage * (output.astype(np.float32) - baseline[..., :3])).clip(0, 255).astype(np.uint8)
    return Image.fromarray(baseline), {"model": name, "model_sha256": expected_hash, "model_url": url,
           "loader": "spandrel", "torch": torch.__version__, "gpu": torch.cuda.get_device_name(),
           "precision": "fp16" if half else "fp32", "tile": tile, "tile_pad": pad, "strength": strength}


def save_png_exclusive(image, path):
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    # Exclusive destination creation; never replace originals or earlier outputs.
    with Path(path).open("xb") as stream:
        image.save(stream, format="PNG", icc_profile=profile)


def comparison(original, result):
    panels = []
    for image, label in [(original, "Original - Lanczos baseline"), (result, "Processed - inspect detail and likeness")]:
        image = image.copy(); image.thumbnail((900, 900))
        panel = Image.new("RGB", (image.width, image.height + 30), "#303033")
        panel.paste(image, (0, 30), image.getchannel("A"))
        ImageDraw.Draw(panel).text((8, 8), label, fill="white"); panels.append(panel)
    sheet = Image.new("RGB", (sum(p.width for p in panels), max(p.height for p in panels)), "#303033")
    sheet.paste(panels[0], (0, 0)); sheet.paste(panels[1], (panels[0].width, 0))
    return sheet


def run(job):
    source = Path(job["input"]).resolve(strict=True)
    destination = Path(job["output_dir"]).resolve(strict=True)
    scale, method = job.get("scale", 2), job.get("method", "lanczos")
    strength = float(job.get("upscale_strength", 0.5))
    tile = job.get("tile", 192)
    if scale not in (1, 2, 4) or method not in ("lanczos", "realesrgan"):
        raise ValueError("Invalid scale or method")
    if not math.isfinite(strength) or not 0 <= strength <= 1 or not isinstance(tile, int) or tile < 64 or tile > 512 or tile % 2:
        raise ValueError("Invalid strength or tile size")
    outputs = [destination / name for name in ("enhanced.png", "baseline.png", "comparison.png", "report.json")]
    if any(path.exists() or path == source for path in outputs):
        raise ValueError("Use a fresh output folder; existing outputs are never overwritten")
    report = {"status": "running", "input": str(source), "source_sha256": sha256(source),
              "python_executable": sys.executable,
              "scale": scale, "method": method, "quality": "requires visual comparison; no equivalence to native high-resolution rendering claimed"}
    started = time.perf_counter()
    try:
        image, report["color_conversion"] = load_render(source)
        size = (image.width * scale, image.height * scale)
        if max(size) > 8192 or size[0] * size[1] > MAX_PIXELS:
            raise ValueError("Output exceeds the alpha's 32 MP / 8192-pixel side limit; use a lower scale")
        report["input_size"] = list(image.size); report["output_size"] = list(size)
        baseline = resize_rgba(image, size)
        processed = image
        if job.get("enhance", True):
            progress("Applying current neural enhancement controls...")
            processed, report["enhancement"] = enhance_nr(image, job)
        if scale > 1 and method == "realesrgan" and strength > 0:
            progress("Loading pinned Real-ESRGAN model...")
            processed, report["upscaler"] = upscale_neural(processed, scale, job.get("model_dir", ROOT / "runtime" / "upscale"), strength, tile)
        else:
            processed = resize_rgba(processed, size)
        save_png_exclusive(baseline, destination / "baseline.png")
        save_png_exclusive(processed, destination / "enhanced.png")
        save_png_exclusive(comparison(baseline, processed), destination / "comparison.png")
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        if not report["source_unchanged"]:
            raise RuntimeError("Source file changed externally during processing")
        report["alpha_matches_baseline"] = bool(np.array_equal(np.asarray(processed.getchannel("A")), np.asarray(baseline.getchannel("A"))))
        report["status"] = "passed"
        progress("Saved enhanced.png, baseline.png and comparison.png")
    except Exception as exc:
        report["status"] = "failed"; report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["elapsed_seconds"] = time.perf_counter() - started
        with (destination / "report.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
    return report


def watch_parent(parent_pid):
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    handle = kernel.OpenProcess(0x00100000, False, parent_pid)
    deadline = time.monotonic() + 1800
    while True:
        if not handle or kernel.WaitForSingleObject(handle, 0) == 0 or time.monotonic() > deadline:
            terminate_self(4)
        time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--parent-pid", type=int, default=0)
    args = parser.parse_args()
    if os.name == "nt" and args.parent_pid:
        threading.Thread(target=watch_parent, args=(args.parent_pid,), daemon=True).start()
    try:
        job = json.loads(args.job.read_text(encoding="utf-8-sig"))
        run(job)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
