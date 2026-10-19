"""Standalone still-image experiment. Does not import ComfyUI, Torch, or Daz."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageOps

from packaged_runtime import application_root, frozen

ROOT = application_root()
BACKEND = ROOT / "vendor" / "ComfyUI-DLSS5-NR"
PIN = "41dcdfa593cb61b6a98c65bb8ed27606260bb598"
BRIDGE = BACKEND / "native" / "bin" / "dlss5nr_bridge.dll"
SHIM = BACKEND / "runtime" / "caller" / "nvngx.dll_comfy.dll"
if frozen():
    BRIDGE = ROOT / "backend" / "dlss5nr_bridge.dll"
    SHIM = ROOT / "backend" / "nvngx.dll_comfy.dll"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_info(path):
    path = Path(path).resolve()
    if not path.is_file():
        return {"path": str(path), "present": False}
    return {"path": str(path), "present": True, "bytes": path.stat().st_size,
            "sha256": sha256(path)}


def gpu_info():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10, check=True)
        return {"nvidia_smi": result.stdout.strip()}
    except (OSError, subprocess.SubprocessError) as error:
        return {"error": str(error)}


def load_bridge():
    # Directory handles must remain alive until shutdown.
    handles = [os.add_dll_directory(str(BRIDGE.parent))]
    lib = ctypes.CDLL(str(BRIDGE))
    lib.dlss5nr_version.argtypes = []
    lib.dlss5nr_version.restype = ctypes.c_char_p
    lib.dlss5nr_gpu_name.argtypes = []
    lib.dlss5nr_gpu_name.restype = ctypes.c_char_p
    lib.dlss5nr_init.argtypes = [ctypes.c_int, ctypes.c_wchar_p, ctypes.c_char_p, ctypes.c_int]
    lib.dlss5nr_init.restype = ctypes.c_int
    fp = ctypes.POINTER(ctypes.c_float)
    lib.dlss5nr_process.argtypes = [fp, fp, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_float, ctypes.c_float,
        ctypes.c_float, ctypes.c_float, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.dlss5nr_process.restype = ctypes.c_int
    lib.dlss5nr_shutdown.argtypes = []
    lib.dlss5nr_shutdown.restype = None
    return lib, handles


def read_image(path, alpha_mode="reject"):
    """Use display-referred 8-bit input only; never silently reduce an HDR master."""
    path = Path(path)
    with Image.open(path) as source:
        if source.format not in ("PNG", "TIFF"):
            raise ValueError("First pilot accepts PNG or TIFF only.")
        if getattr(source, "n_frames", 1) != 1:
            raise ValueError("Use a single still image, not a multipage/animated file.")
        if source.format == "PNG":
            with path.open("rb") as stream:
                header = stream.read(29)
            if len(header) < 29 or header[24] != 8:
                raise ValueError("Use an 8-bit PNG preview; keep the higher-depth original separately.")
        if source.format == "TIFF":
            bits = source.tag_v2.get(258, (8,))
            if isinstance(bits, int):
                bits = (bits,)
            if any(value != 8 for value in bits):
                raise ValueError("Use an 8-bit TIFF preview; HDR/16-bit input is not supported in this pilot.")
        if source.mode not in ("RGB", "RGBA", "P"):
            raise ValueError(f"Unsupported color mode {source.mode}; supply an RGB/RGBA preview.")
        if max(source.size) > 4096 or source.width * source.height > 4096 * 4096:
            raise ValueError("Pilot is capped at 4096 pixels per side; supply a smaller preview.")
        rgba = ImageOps.exif_transpose(source).convert("RGBA")
        alpha = np.array(rgba.getchannel("A"), dtype=np.uint8)
        has_alpha = bool(np.any(alpha != 255))
        if has_alpha and alpha_mode != "gray":
            raise ValueError("Use an opaque render for this first pilot; transparent edges need separate evaluation.")
        rgb = rgba.convert("RGB")
        metadata = {"format": source.format, "source_mode": source.mode,
                    "size": list(rgb.size), "color_conversion": "assumed sRGB (no ICC)"}
        if source.info.get("icc_profile"):
            profile = ImageCms.ImageCmsProfile(io.BytesIO(source.info["icc_profile"]))
            rgb = ImageCms.profileToProfile(rgb, profile, ImageCms.createProfile("sRGB"), outputMode="RGB")
            metadata["color_conversion"] = "embedded ICC converted to sRGB"
        elif "gamma" in source.info and abs(source.info["gamma"] - 0.45455) > 0.002:
            raise ValueError("Non-sRGB PNG gamma; convert a preview to sRGB before the pilot.")
        metadata["alpha_handling"] = "opaque input"
        if has_alpha:
            rgba_srgb = rgb.convert("RGBA")
            rgba_srgb.putalpha(Image.fromarray(alpha))
            background = Image.new("RGBA", rgba_srgb.size, (128, 128, 128, 255))
            rgb = Image.alpha_composite(background, rgba_srgb).convert("RGB")
            metadata["alpha_handling"] = "composited over sRGB #808080; enhanced output is opaque"
            metadata["source_alpha_extrema"] = [int(alpha.min()), int(alpha.max())]
        return np.ascontiguousarray(np.asarray(rgb), dtype=np.float32) / 255.0, metadata


def save_rgb(array, path):
    pixels = np.rint(np.clip(array, 0, 1) * 255).astype(np.uint8)
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    Image.fromarray(pixels).save(path, icc_profile=profile)


def preview(left, right, path):
    panels = []
    for array, label in [(left, "Original sRGB preview"), (right, "DLSS NR - assess visually")]:
        panel = Image.fromarray(np.rint(np.clip(array, 0, 1) * 255).astype(np.uint8))
        panel.thumbnail((960, 960))
        tile = Image.new("RGB", (panel.width, panel.height + 32), "#202020")
        tile.paste(panel, (0, 32))
        ImageDraw.Draw(tile).text((10, 9), label, fill="white")
        panels.append(tile)
    sheet = Image.new("RGB", (sum(p.width for p in panels), max(p.height for p in panels)), "#202020")
    sheet.paste(panels[0], (0, 0))
    sheet.paste(panels[1], (panels[0].width, 0))
    sheet.save(path)


def worker(job_path):
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    report_path = Path(job["output"]) / "worker-report.json"
    report = {"status": "failed", "backend_commit": PIN, "processing": "1x still, reset=1, temporal=0"}
    lib = None
    try:
        src, metadata = read_image(job["input"], job.get("alpha_mode", "reject"))
        report["input_decode"] = metadata
        lib, handles = load_bridge()
        report["bridge_version"] = lib.dlss5nr_version().decode()
        err = ctypes.create_string_buffer(4096)
        started = time.perf_counter()
        if not lib.dlss5nr_init(job["gpu"], job["staged_runtime"], err, len(err)):
            raise RuntimeError(err.value.decode("utf-8", errors="replace"))
        report["initialization_seconds"] = time.perf_counter() - started
        report["selected_gpu"] = lib.dlss5nr_gpu_name().decode()
        fp = ctypes.POINTER(ctypes.c_float)
        h, w, _ = src.shape
        outputs, timings = [], []
        for _ in range(2):
            out = np.full_like(src, np.nan)
            started = time.perf_counter()
            okay = lib.dlss5nr_process(src.ctypes.data_as(fp), out.ctypes.data_as(fp), w, h,
                job["style"], job["preset"], job["intensity"], job["tone"], job["structure"],
                job["skin"], int(job["auto_mask"]), 1, 0, err, len(err))
            timings.append(time.perf_counter() - started)
            if not okay:
                raise RuntimeError(err.value.decode("utf-8", errors="replace"))
            if not np.isfinite(out).all():
                raise RuntimeError("Native output contains NaN/Inf or unwritten values.")
            outputs.append(out)
        report["processing_seconds_including_transfers"] = timings
        report["repeat_float_identical"] = bool(np.array_equal(outputs[0], outputs[1]))
        report["repeat_max_abs_delta"] = float(np.max(np.abs(outputs[0] - outputs[1])))
        out = outputs[0]
        if job["channel_order"] == "BGRA":
            out = out[..., [2, 1, 0]]
        report["channel_order"] = job["channel_order"]
        # Changes quantify effect magnitude, not improvement or preservation of quality.
        report["mean_abs_change_srgb"] = float(np.mean(np.abs(out - src)))
        report["max_abs_change_srgb"] = float(np.max(np.abs(out - src)))
        report["quality_verdict"] = "unassessed; requires visual comparison"
        output_dir = Path(job["output"])
        if job.get("save_float", True):
            np.save(output_dir / "enhanced-float32.npy", out, allow_pickle=False)
        save_rgb(src, output_dir / "original-preview.png")
        save_rgb(out, output_dir / "enhanced.png")
        preview(src, out, output_dir / "comparison.png")
        report["status"] = "enhancement_completed"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        report["cleanup_status"] = "not_started"
        # Persist inference evidence before entering any third-party shutdown code.
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        if lib is not None and job.get("shutdown_mode", "graceful") == "graceful":
            report["cleanup_status"] = "started"
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            cleanup_errors = []
            def cleanup():
                try:
                    lib.dlss5nr_shutdown()
                except Exception as error:
                    cleanup_errors.append(str(error))
            cleanup_thread = threading.Thread(target=cleanup, daemon=True)
            cleanup_thread.start()
            cleanup_thread.join(10)
            if cleanup_thread.is_alive():
                report["cleanup_status"] = "native_shutdown_timed_out"
            elif cleanup_errors:
                report["cleanup_status"] = "native_shutdown_error"
                report["cleanup_error"] = cleanup_errors[0]
            else:
                report["cleanup_status"] = "completed"
        elif lib is not None:
            report["cleanup_status"] = "native_cleanup_skipped_disposable_worker"
        report["worker_exit_strategy"] = "TerminateProcess current worker on Windows"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    exit_code = 0 if report["status"] == "enhancement_completed" else 1
    if report["cleanup_status"] not in ("completed", "not_started", "native_cleanup_skipped_disposable_worker"):
        exit_code = 3
    # Windows _exit still reaches ExitProcess DLL detach notifications. A vendor
    # DLL can deadlock there too, so terminate ONLY this disposable current worker.
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.argtypes = []
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel.TerminateProcess.restype = ctypes.c_int
        kernel.TerminateProcess(kernel.GetCurrentProcess(), exit_code)
    os._exit(exit_code)


def probe(runtime):
    result = {"gpu": gpu_info(), "backend_commit_expected": PIN,
              "bridge": file_info(BRIDGE), "caller_shim": file_info(SHIM),
              "runtime": file_info(runtime) if runtime else {"present": False, "path": None},
              "preflight_performs_inference": False}
    try:
        revision = subprocess.run(["git", "-C", str(BACKEND), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        result["backend_commit_actual"] = revision
    except (OSError, subprocess.SubprocessError) as error:
        result["backend_error"] = str(error)
    if BRIDGE.is_file():
        try:
            lib, handles = load_bridge()
            result["bridge_load_test"] = lib.dlss5nr_version().decode()
            lib.dlss5nr_shutdown()
        except Exception as error:
            result["bridge_load_error"] = str(error)
    result["ready_to_attempt"] = bool(result["runtime"]["present"] and SHIM.is_file()
        and result.get("bridge_load_test") and result.get("backend_commit_actual") == PIN)
    return result


def enhance(args):
    input_path, runtime_path, output_dir = args.input.resolve(), args.runtime.resolve(), args.output.resolve()
    if not input_path.is_file():
        raise ValueError(f"Input render does not exist: {input_path}")
    if not runtime_path.is_file():
        raise ValueError(f"NR runtime does not exist: {runtime_path}")
    if output_dir.exists():
        raise ValueError("Use a new output directory; existing results are never overwritten.")
    state = probe(runtime_path)
    if not state["ready_to_attempt"]:
        raise ValueError(f"Preflight failed: {json.dumps(state)}")
    read_image(input_path)  # Validate before creating any output.
    output_dir.mkdir(parents=True)
    job = vars(args).copy()
    job.pop("command")
    for key in ("input", "runtime", "output"):
        job[key] = str({"input": input_path, "runtime": runtime_path, "output": output_dir}[key])
    report = {"status": "started", "preflight": state, "input": file_info(input_path),
              "runtime_origin_user_supplied": args.runtime_origin, "configuration": job.copy(),
              "quality_verdict": "unassessed", "render_time_savings_tested": False}
    stage = output_dir / "_runtime"
    (stage / "caller").mkdir(parents=True)
    shutil.copy2(runtime_path, stage / "nvngx_dlssnr.dll")
    if sha256(stage / "nvngx_dlssnr.dll") != state["runtime"]["sha256"]:
        raise RuntimeError("Runtime changed during staging.")
    shutil.copy2(SHIM, stage / "caller" / SHIM.name)
    job["staged_runtime"] = str(stage)
    job_path = output_dir / "job.json"
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    started = time.perf_counter()
    try:
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), "_worker", str(job_path)],
            capture_output=True, timeout=args.timeout)
        report["worker_exit_code"] = child.returncode
        report["worker_exit_confirmed"] = True
        (output_dir / "worker.log").write_bytes(child.stdout + b"\n" + child.stderr)
        worker_report = output_dir / "worker-report.json"
        if worker_report.is_file():
            report["worker"] = json.loads(worker_report.read_text(encoding="utf-8"))
        report["status"] = ("enhancement_completed" if child.returncode == 0
                            and report.get("worker", {}).get("status") == "enhancement_completed"
                            else "enhancement_completed_cleanup_failed" if child.returncode == 3
                            and report.get("worker", {}).get("status") == "enhancement_completed" else "failed")
    except subprocess.TimeoutExpired as error:
        report["status"] = "timed_out_worker_terminated"
        (output_dir / "worker.log").write_bytes((error.stdout or b"") + b"\n" + (error.stderr or b""))
    finally:
        report["total_test_seconds"] = time.perf_counter() - started
        report["original_sha256_after"] = sha256(input_path)
        report["original_unchanged"] = report["original_sha256_after"] == report["input"]["sha256"]
        report["artifacts"] = [file_info(path) for path in output_dir.glob("*.png")]
        (output_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "enhancement_completed" and report["original_unchanged"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("probe", help="Check bridge and dependencies; does not run enhancement.")
    p.add_argument("--runtime", type=Path)
    e = commands.add_parser("enhance", help="Run an opaque sRGB still twice in a timeout-controlled worker.")
    e.add_argument("--input", type=Path, required=True)
    e.add_argument("--runtime", type=Path, required=True, help="User-supplied compatible nvngx_dlssnr.dll")
    e.add_argument("--runtime-origin", required=True, help="Record the source and applicable runtime agreement")
    e.add_argument("--output", type=Path, required=True)
    e.add_argument("--gpu", type=int, default=0, choices=range(16))
    e.add_argument("--style", type=int, default=1, choices=range(7))
    e.add_argument("--preset", type=int, default=3, choices=range(4))
    e.add_argument("--intensity", type=float, default=1.0)
    e.add_argument("--tone", type=float, default=0.0)
    e.add_argument("--structure", type=float, default=1.0)
    e.add_argument("--skin", type=float, default=-1)
    e.add_argument("--auto-mask", action="store_true")
    e.add_argument("--channel-order", choices=("RGBA", "BGRA"), default="RGBA")
    e.add_argument("--timeout", type=int, default=180)
    e.add_argument("--shutdown-mode", choices=("process", "graceful"), default="process",
                   help="Dispose the private worker without DLL detach; graceful is a teardown diagnostic.")
    w = commands.add_parser("_worker", help=argparse.SUPPRESS)
    w.add_argument("job", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "probe":
            result = probe(args.runtime)
            print(json.dumps(result, indent=2))
            return 0 if result["ready_to_attempt"] else 2
        if args.command == "_worker":
            return worker(args.job)
        for name in ("intensity", "tone", "structure"):
            if not 0 <= getattr(args, name) <= 2:
                raise ValueError(f"{name} must be between 0 and 2.")
        if not -1 <= args.skin <= 2 or not 1 <= args.timeout <= 300:
            raise ValueError("skin must be -1..2; timeout must be 1..300 seconds.")
        return enhance(args)
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
