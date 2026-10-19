"""Private persistent GPU worker for the Daz preview pane; no network server.

Protocol: one tab-separated request per line:
id, style, preset, tone, structure, skin, auto_mask, blend.
The caller writes frame.png (or packed frame.rgb / frame.rgba) in a private
session directory and waits for OK/ERROR before writing the next frame. Raw
requests append width and height. RGBA mode preserves source alpha and applies
an optional coverage.alpha mask to protect UI, transparency and soft shadows.
Only READY/OK/ERROR protocol lines are written to stdout. Diagnostics go to stderr.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import json
import math
import os
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))  # Also support isolated embedded Python.
import numpy as np

from prototype import load_bridge, read_image, save_rgb


def terminate_self(code=0):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, ValueError):
            pass  # Parent may already have closed its pipes.
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel.TerminateProcess(kernel.GetCurrentProcess(), code)
    os._exit(code)


def encoded(value):
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def request(line):
    fields = line.strip().split("\t")
    if len(fields) != 8:
        raise ValueError("Expected eight tab-separated fields")
    ident, style, preset = map(int, fields[:3])
    tone, structure, skin = map(float, fields[3:6])
    mask, blend = int(fields[6]), float(fields[7])
    if not (0 <= ident <= 2147483647 and 0 <= style <= 6 and 0 <= preset <= 3):
        raise ValueError("Invalid request id, style, or preset")
    if not all(math.isfinite(v) for v in (tone, structure, skin, blend)):
        raise ValueError("Settings must be finite")
    if not (0 <= tone <= 2 and 0 <= structure <= 2 and -1 <= skin <= 2
            and mask in (0, 1) and 0 <= blend <= 1):
        raise ValueError("Setting out of range")
    return ident, style, preset, tone, structure, skin, mask, blend


def blend_preview(src, enhanced, strength):
    # Display-referred crossfade, independent of the experimental native intensity.
    return np.ascontiguousarray(src * (1 - strength) + enhanced * strength,
                                dtype=np.float32)


def watch_lifetime(state, parent_pid):
    """Bound native stalls and orphan lifetime without entering vendor teardown."""
    handle, kernel = None, None
    if os.name == "nt" and parent_pid:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        handle = kernel.OpenProcess(0x00100000, False, parent_pid)  # SYNCHRONIZE only
        if not handle:
            terminate_self(4)
    while True:
        time.sleep(0.5)
        if handle and kernel.WaitForSingleObject(handle, 0) == 0:
            terminate_self(4)
        if time.monotonic() - state["activity"] > (45 if state["busy"] else 120):
            print("Worker operation/idle deadline exceeded", file=sys.stderr, flush=True)
            terminate_self(5)


def run(args):
    session = args.session.resolve(strict=True)
    if not session.is_dir():
        raise ValueError("Session must be an existing private directory")
    state = {"activity": time.monotonic(), "busy": True}
    threading.Thread(target=watch_lifetime, args=(state, args.parent_pid), daemon=True).start()
    lib, handles = load_bridge()
    error = ctypes.create_string_buffer(4096)
    if not lib.dlss5nr_init(args.gpu, str(args.runtime.resolve(strict=True)), error, len(error)):
        raise RuntimeError(error.value.decode("utf-8", errors="replace"))
    print("READY\t" + encoded(lib.dlss5nr_gpu_name().decode()), flush=True)
    state.update(activity=time.monotonic(), busy=False)
    fp = ctypes.POINTER(ctypes.c_float)
    for line in sys.stdin:
        if line.strip() == "QUIT":
            break
        ident = -1
        state.update(activity=time.monotonic(), busy=True)
        try:
            fields = line.strip().split("\t")
            source_alpha = None
            coverage = None
            if args.transport in ("rgb", "rgba"):
                if len(fields) != 10:
                    raise ValueError("Raw transport expects settings plus width and height")
                width, height = map(int, fields[8:])
                if not (1 <= width <= 4096 and 1 <= height <= 4096):
                    raise ValueError("Invalid RGB frame dimensions")
                ident, style, preset, tone, structure, skin, mask, blend = request("\t".join(fields[:8]))
                channels = 4 if args.transport == "rgba" else 3
                raw_path = session / ("frame.rgba" if channels == 4 else "frame.rgb")
                expected_bytes = width * height * channels
                if raw_path.stat().st_size != expected_bytes:
                    raise ValueError("Raw frame byte count differs from dimensions")
                pixels = np.fromfile(raw_path, dtype=np.uint8, count=expected_bytes).reshape(height, width, channels)
                src = np.ascontiguousarray(pixels[..., :3], dtype=np.float32) / 255.0
                metadata = {"format": "packed RGBA8" if channels == 4 else "packed RGB8", "size": [width, height],
                            "color_conversion": "sRGB supplied by Daz pane", "alpha_handling": "opaque viewport"}
                if channels == 4:
                    source_alpha = pixels[..., 3].copy()
                    coverage = np.clip((source_alpha.astype(np.float32) / 255.0 - 0.90) / 0.10, 0, 1)
                    mask_path = session / "coverage.alpha"
                    if mask_path.exists():
                        if mask_path.stat().st_size != width * height:
                            raise ValueError("Coverage mask byte count differs from dimensions")
                        supplied = np.fromfile(mask_path, dtype=np.uint8, count=width*height).reshape(height, width)
                        coverage = np.minimum(coverage, supplied.astype(np.float32) / 255.0)
                    metadata["alpha_handling"] = "alpha preserved; transparent/shadow pixels protected; neutral-gray model composite"
            else:
                ident, style, preset, tone, structure, skin, mask, blend = request(line)
                src, metadata = read_image(session / "frame.png")
            out = np.full_like(src, np.nan)
            inference_src = src
            if source_alpha is not None:
                opacity = source_alpha.astype(np.float32)[..., None] / 255.0
                inference_src = np.ascontiguousarray(src * opacity + 0.5 * (1 - opacity), dtype=np.float32)
            height, width, _ = src.shape
            started = time.perf_counter()
            okay = lib.dlss5nr_process(inference_src.ctypes.data_as(fp), out.ctypes.data_as(fp),
                width, height, style, preset, 1.0, tone, structure, skin, mask,
                1, 0, error, len(error))  # Reset: no renderer motion/depth buffers available.
            milliseconds = (time.perf_counter() - started) * 1000
            if not okay:
                raise RuntimeError(error.value.decode("utf-8", errors="replace"))
            if not np.isfinite(out).all():
                raise RuntimeError("Native output contains NaN/Inf")
            result = blend_preview(src, out, blend)
            if coverage is not None:
                result = np.ascontiguousarray(src + coverage[..., None] * (result - src), dtype=np.float32)
            if args.transport in ("rgb", "rgba"):
                extension = args.transport
                temporary = session / ("enhanced.tmp." + extension)
                exported = np.rint(np.clip(result, 0, 1) * 255).astype(np.uint8)
                if source_alpha is not None:
                    exported = np.concatenate((exported, source_alpha[..., None]), axis=2)
                exported.tofile(temporary)
                temporary.replace(session / ("enhanced." + extension))
            else:
                temporary = session / "enhanced.tmp.png"
                save_rgb(result, temporary)
                temporary.replace(session / "enhanced.png")
            report = {"request_id": ident, "processing_ms": milliseconds,
                      "input_decode": metadata, "reset": 1, "temporal": 0,
                      "native_intensity": 1.0, "tone": tone, "structure": structure,
                      "skin": skin, "auto_mask": mask, "blend": blend,
                      "style": style, "preset": preset, "transport": args.transport,
                      "quality": "unassessed"}
            (session / "latest-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"OK\t{ident}\t{milliseconds:.3f}\t{width}\t{height}", flush=True)
        except Exception as exc:
            print(f"ERROR\t{ident}\t{encoded(type(exc).__name__ + ': ' + str(exc))}", flush=True)
        finally:
            state.update(activity=time.monotonic(), busy=False)
    # Do not call native shutdown or ExitProcess DLL detach (known runtime hang).
    terminate_self(0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True, help="Already staged runtime directory")
    parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--gpu", type=int, choices=range(16), default=0)
    parser.add_argument("--transport", choices=("png", "rgb", "rgba"), default="png")
    args = parser.parse_args()
    try:
        run(args)
    except Exception as exc:
        print("ERROR\t-1\t" + encoded(type(exc).__name__ + ": " + str(exc)), flush=True)
        terminate_self(1)


if __name__ == "__main__":
    main()
