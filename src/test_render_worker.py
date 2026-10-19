"""Real input/real CUDA evaluation for still-render processing."""
import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from PIL import Image
from render_worker import load_render, resize_rgba, run, upscale_neural, ROOT
from prototype import sha256


class Preservation(unittest.TestCase):
    def test_rgba_baseline_and_original(self):
        with tempfile.TemporaryDirectory(prefix="PuenteRenderTest-") as folder:
            root = Path(folder)
            pixels = np.zeros((29, 41, 4), dtype=np.uint8)
            pixels[..., :3] = [213, 78, 52]
            pixels[:, 10:31, 3] = np.arange(21, dtype=np.uint8) * 12
            source = root / "source.png"; Image.fromarray(pixels).save(source)
            digest = sha256(source)
            for scale in (1, 2, 4):
                output = root / str(scale); output.mkdir()
                report = run({"input": str(source), "output_dir": str(output), "scale": scale, "enhance": False})
                self.assertTrue(report["source_unchanged"])
                self.assertTrue(report["alpha_matches_baseline"])
                result = np.asarray(Image.open(output / "enhanced.png"))
                self.assertTrue(np.array_equal(result, np.asarray(Image.open(output / "baseline.png"))))
                if scale == 1: self.assertTrue(np.array_equal(result, pixels))
                with Image.open(output / "enhanced.png") as exported:
                    self.assertEqual(exported.size, (41 * scale, 29 * scale))
            self.assertEqual(digest, sha256(source))
            with self.assertRaisesRegex(ValueError, "fresh output"):
                run({"input": str(source), "output_dir": str(root / "2"), "enhance": False})

    def test_hdr_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "hdr.png"
            Image.fromarray(np.arange(300, dtype=np.uint16).reshape(15, 20)).save(source)
            with self.assertRaises(ValueError): load_render(source)

    def test_invalid_scale(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.png"; Image.new("RGB", (10, 10)).save(source)
            with self.assertRaises(ValueError): run({"input": str(source), "output_dir": folder, "scale": 3})


def gpu_probe():
    import torch
    output = ROOT / "artifacts" / "render-validation"
    original_path = ROOT / "artifacts" / "daz6-validation" / "stress" / "iray-input.png"
    if not original_path.is_file():
        original_path = ROOT / "artifacts" / "daz6-validation" / "alpha" / "original.png"
    if not original_path.is_file():
        original_path = ROOT / "artifacts" / "daz6-validation" / "release" / "original.png"
    source, _ = load_render(original_path)
    source.thumbnail((384, 384))
    # Real-render content plus a transparent border checks the neural edge path.
    source = source.crop((0, 0, min(251, source.width), min(193, source.height)))
    pixels = np.asarray(source).copy(); pixels[:5, :, 3] = 0; pixels[5:10, :, 3] = 128
    source = Image.fromarray(pixels)
    source_path = output / "gpu-input.png"; source.save(source_path)
    digest = sha256(source_path)
    report = {"torch": torch.__version__, "checks": []}
    for scale in (2, 4):
        destination = output / f"gpu-{scale}x"; destination.mkdir(exist_ok=False)
        result = run({"input": str(source_path), "output_dir": str(destination), "scale": scale,
                      "method": "realesrgan", "upscale_strength": 0.5, "enhance": False})
        inferred = np.asarray(Image.open(destination / "enhanced.png"))
        baseline = np.asarray(Image.open(destination / "baseline.png"))
        protected = baseline[..., 3] <= 229
        assert np.array_equal(inferred[protected], baseline[protected])
        assert np.array_equal(inferred[..., 3], baseline[..., 3])
        assert np.any(inferred[..., :3] != baseline[..., :3])
        assert sha256(source_path) == digest
        # Odd size and a tile boundary exercise x2 pixel-unshuffle alignment.
        report["checks"].append({"scale": scale, "protected_pixels_exact": True, "alpha_exact": True,
                                  "actual_model_effect": True, "source_unchanged": True, "report": result})
    # NR + upscale together, using the configured runtime, in an isolated child.
    destination = output / "combined"; destination.mkdir(exist_ok=False)
    result = run({"input": str(source_path), "output_dir": str(destination), "scale": 2,
                  "method": "realesrgan", "enhance": True, "runtime": str(ROOT / "runtime" / "viewport")})
    assert result["alpha_matches_baseline"] and result["source_unchanged"]
    report["combined"] = result
    (output / "gpu-checks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import sys
    if "--gpu" in sys.argv: gpu_probe()
    else: unittest.main()
