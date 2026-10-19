"""Real-GPU integration check for persistent requests and bounded worker exit."""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time

import numpy as np
from PIL import Image

from prototype import ROOT, sha256, read_image


def run(source, runtime, output, transport="png"):
    output.mkdir(parents=True, exist_ok=False)
    original_hash = sha256(source)
    shutil.copyfile(source, output / "frame.png")
    decoded, _ = read_image(source)
    expected = np.rint(np.clip(decoded, 0, 1) * 255).astype(np.uint8)
    height, width, _ = expected.shape
    expected.tofile(output / "frame.rgb")
    suffix = f"\t{width}\t{height}" if transport == "rgb" else ""
    child = subprocess.Popen([sys.executable, "-B", str(ROOT / "viewport_worker.py"),
        "--session", str(output), "--runtime", str(runtime), "--parent-pid", str(os.getpid()),
        "--transport", transport],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    lines = queue.Queue()
    def read_lines():
        for line in child.stdout:
            lines.put(line.rstrip())
        lines.put("EOF")
    threading.Thread(target=read_lines, daemon=True).start()
    report = {"worker_pid": child.pid, "transport": transport, "responses": [], "status": "failed"}
    try:
        ready = lines.get(timeout=45)
        report["ready"] = ready
        assert ready.startswith("READY\t"), ready
        outputs = []
        for ident, params in enumerate([
                "1\t3\t0\t1\t-1\t0\t1",
                "1\t3\t0\t1\t-1\t0\t1",
                "1\t3\t1\t1.5\t1.5\t1\t1",
                "1\t3\t0\t1\t-1\t0\t0"], 1):
            started = time.perf_counter()
            child.stdin.write(f"{ident}\t{params}{suffix}\n")
            child.stdin.flush()
            response = lines.get(timeout=45)
            report["responses"].append({"line": response, "round_trip_ms": (time.perf_counter()-started)*1000})
            assert response.startswith(f"OK\t{ident}\t"), response
            if transport == "rgb":
                pixels = np.fromfile(output / "enhanced.rgb", dtype=np.uint8).reshape(height, width, 3)
                Image.fromarray(pixels).save(output / f"result-{ident}.png")
                outputs.append(pixels.copy())
            else:
                result = output / "enhanced.png"
                shutil.copyfile(result, output / f"result-{ident}.png")
                with Image.open(result) as image:
                    outputs.append(np.array(image.convert("RGB")))
        assert np.array_equal(outputs[0], outputs[1]), "Repeated input changed"
        assert np.array_equal(expected, outputs[3]), "Blend=0 changed original preview"
        assert not np.array_equal(outputs[0], outputs[2]), "Strong settings had no effect"
        child.stdin.write("5\t1\t3\tnan\t1\t-1\t0\t1" + suffix + "\n")
        child.stdin.flush()
        response = lines.get(timeout=5)
        assert response.startswith("ERROR\t-1\t"), response
        child.stdin.write("6\t1\t3\t0\t1\t-1\t0\t1" + suffix + "\n")
        child.stdin.flush()
        assert lines.get(timeout=45).startswith("OK\t6\t"), "Worker did not recover from invalid settings"
        if transport == "rgb":
            smaller = expected[:360, :640].copy()
            smaller.tofile(output / "frame.rgb")
            child.stdin.write("7\t1\t3\t0\t1\t-1\t0\t1\t640\t360\n")
            child.stdin.flush()
            resized = lines.get(timeout=45)
            assert resized.startswith("OK\t7\t") and resized.endswith("\t640\t360"), resized
            expected.tofile(output / "frame.rgb")
            child.stdin.write("8\t1\t3\t0\t1\t-1\t0\t1" + suffix + "\n")
            child.stdin.flush()
            assert lines.get(timeout=45).startswith("OK\t8\t")
            restored = np.fromfile(output / "enhanced.rgb", dtype=np.uint8).reshape(height, width, 3)
            assert np.array_equal(restored, outputs[0]), "Size change altered reset-frame output"
            report["resize_and_restore_identical"] = True
            report["appearance_responses"] = []
            for ident, style in ((9, 0), (10, 2), (11, 1)):
                child.stdin.write(f"{ident}\t{style}\t3\t0\t1\t-1\t0\t1" + suffix + "\n")
                child.stdin.flush()
                response = lines.get(timeout=45)
                assert response.startswith(f"OK\t{ident}\t"), response
                report["appearance_responses"].append(response)
            final = np.fromfile(output / "enhanced.rgb", dtype=np.uint8).reshape(height, width, 3)
            assert np.array_equal(final, outputs[0]), "Restoring Natural style changed reset-frame output"
            report["appearance_switch_restore_identical"] = True
        child.stdin.write("QUIT\n")
        child.stdin.flush()
        assert child.wait(timeout=10) == 0
        assert sha256(source) == original_hash, "Source image changed"
        report.update(status="passed", repeated_pixels_identical=True,
                      zero_blend_pixels_identical=True, settings_change_pixels=True,
                      invalid_request_recovered=True, source_unchanged=True,
                      exit_code=child.returncode, persistent_process=True)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        report["stderr"] = child.stderr.read()
        (output / "integration-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--transport", choices=("png", "rgb"), default="png")
    args = parser.parse_args()
    run(args.input, args.runtime, args.output, args.transport)
