"""Real-GPU regression check: preserve alpha, shadows, protected UI and zero blend."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

import numpy as np

from prototype import ROOT, sha256


def run(runtime, output):
    output.mkdir(parents=True, exist_ok=False)
    height, width = 360, 640
    y, x = np.mgrid[:height, :width]
    source = np.empty((height, width, 4), dtype=np.uint8)
    source[..., 0] = x % 256
    source[..., 1] = y % 256
    source[..., 2] = (x // 8 + y // 8) % 2 * 160 + 40
    source[..., 3] = 255
    source[:, :128, 3] = 0
    source[:, 128:256, 3] = 96
    source[:, 256:384, 3] = 229
    mask = np.full((height, width), 255, dtype=np.uint8)
    mask[:32] = 0
    mask[100:140, 500:] = 0
    source.tofile(output / "frame.rgba")
    mask.tofile(output / "coverage.alpha")
    before = sha256(output / "frame.rgba")
    child = subprocess.Popen([sys.executable, "-B", str(ROOT / "viewport_worker.py"),
        "--session", str(output.resolve()), "--runtime", str(runtime.resolve()),
        "--transport", "rgba", "--parent-pid", str(os.getpid())], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    lines = queue.Queue()
    def reader():
        for line in child.stdout:
            lines.put(line.rstrip())
        lines.put("EOF")
    threading.Thread(target=reader, daemon=True).start()
    report = {"status": "failed", "worker_pid": child.pid, "responses": []}
    try:
        ready = lines.get(timeout=45)
        assert ready.startswith("READY\t"), ready
        images = []
        for ident, blend in ((1, 1), (2, 1), (3, 0)):
            child.stdin.write(f"{ident}\t1\t3\t0\t1\t-1\t0\t{blend}\t{width}\t{height}\n")
            child.stdin.flush()
            response = lines.get(timeout=45)
            assert response.startswith(f"OK\t{ident}\t"), response
            report["responses"].append(response)
            image = np.fromfile(output / "enhanced.rgba", dtype=np.uint8).reshape(source.shape)
            assert np.array_equal(image[..., 3], source[..., 3]), "Alpha changed"
            protected = (mask == 0) | (source[..., 3] <= 229)
            assert np.array_equal(image[protected], source[protected]), "Protected UI/background/shadow pixels changed"
            images.append(image.copy())
        assert np.array_equal(images[0], images[1]), "Repeat changed pixels"
        assert np.array_equal(images[2], source), "Zero blend changed source RGBA"
        assert before == sha256(output / "frame.rgba"), "Input changed"
        child.stdin.write("QUIT\n"); child.stdin.flush()
        assert child.wait(timeout=10) == 0
        report.update(status="passed", alpha_exact=True, protected_pixels_exact=True,
                      zero_blend_rgba_exact=True, repeated_rgba_exact=True, input_unchanged=True,
                      enhanced_pixels=int(np.any(images[0] != source, axis=2).sum()), exit_code=child.returncode)
    finally:
        if child.poll() is None:
            child.kill(); child.wait(timeout=10)
        report["stderr"] = child.stderr.read()
        (output / "alpha-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.runtime, args.output)
