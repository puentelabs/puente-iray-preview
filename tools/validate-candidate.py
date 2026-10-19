"""Verifica el paquete real desde un cwd vacío y sin Python externo en PATH."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from PIL import Image


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate(args):
    package = args.package.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    working = output / "empty-cwd"
    working.mkdir()
    worker = package / "plugins" / "PuenteIrayPreview" / "puente-worker.exe"
    environment = dict(os.environ)
    environment["PATH"] = str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32")
    environment["PYTHONHOME"] = str(working / "no-python-installed")
    environment["PYTHONPATH"] = str(working / "no-site-packages")
    environment["TEMP"] = environment["TMP"] = str(working)
    result = {"status": "failed", "checks": [], "external_python_removed_from_path": True,
              "invalid_pythonhome_and_pythonpath": True}
    result["provenance"] = {"worker_sha256": digest(worker),
        "plugin_sha256": digest(package / "plugins" / "dsp_PuenteIrayPreview.dll"),
        "input_sha256": digest(args.input)}
    if args.runtime:
        result["provenance"]["nr_runtime_sha256"] = digest(args.runtime / "nvngx_dlssnr.dll")
        result["provenance"]["caller_sha256"] = digest(args.runtime / "caller" / "nvngx.dll_comfy.dll")
        result["provenance"]["bridge_sha256"] = digest(worker.parent / "backend" / "dlss5nr_bridge.dll")

    def invoke(options, success=True, timeout=120):
        process = subprocess.run([str(worker)] + options, cwd=working, env=environment,
                                 capture_output=True, text=True, timeout=timeout,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert (process.returncode == 0) == success, (process.returncode, process.stdout[-3000:], process.stderr[-3000:])
        return process

    try:
        check = json.loads(invoke(["check"]).stdout)
        assert check["frozen"] and check["status"] == "passed"
        result["runtime"] = check
        rejected = json.loads(invoke(["check", "--nr", "--runtime", str(working / "missing")], False).stdout)
        assert rejected["errors"]
        result["checks"].append("Runtime NR ausente rechazado antes del render")
        if args.neural:
            for scale in (2, 4):
                data = json.loads(invoke(["check", "--upscale", "--scale", str(scale)]).stdout)
                assert data["status"] == "passed"
            result["checks"].append("CUDA, spandrel y pesos oficiales 2x/4x incluidos")
        else:
            rejected = json.loads(invoke(["check", "--upscale", "--scale", "2"], False).stdout)
            assert rejected["errors"]
            result["checks"].append("Perfil Core rechaza Real-ESRGAN ausente")
        before = digest(args.input)
        jobs = [("baseline-2x", 2, False, "lanczos")]
        if args.runtime:
            jobs += [("nr-1x-a", 1, True, "lanczos"), ("nr-1x-b", 1, True, "lanczos")]
        if args.neural:
            jobs += [(f"neural-{scale}x", scale, bool(args.runtime), "realesrgan") for scale in (2, 4)]
        result["jobs"] = {}
        for name, scale, enhance, method in jobs:
            folder = output / name
            folder.mkdir()
            job = {"input": str(args.input.resolve()), "output_dir": str(folder), "scale": scale,
                   "method": method, "enhance": enhance, "upscale_strength": 0.5,
                   "model_dir": str(worker.parent / "runtime" / "upscale")}
            if args.runtime:
                job["runtime"] = str(args.runtime.resolve())
            request = folder / "request.json"
            request.write_text(json.dumps(job), encoding="utf-8")
            started = time.monotonic()
            process = invoke(["render", "--job", str(request)])
            report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
            assert report["status"] == "passed" and report["source_unchanged"] and report["alpha_matches_baseline"]
            assert Path(report["python_executable"]).resolve() == worker.resolve()
            assert report["output_size"] == [side * scale for side in report["input_size"]]
            result["jobs"][name] = {"seconds": round(time.monotonic() - started, 3), "report": report}
        assert digest(args.input) == before
        result["checks"].append("Render original conservado por SHA-256; dimensiones y alfa correctos")
        if args.runtime:
            # Los perfiles ICC generados pueden incluir fechas distintas; comparar píxeles.
            with Image.open(output / "nr-1x-a" / "enhanced.png") as a, Image.open(output / "nr-1x-b" / "enhanced.png") as b:
                assert a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes()
            result["checks"].append("Dos procesos NR independientes producen píxeles idénticos y terminan")
        result["status"] = "passed"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        (output / "validation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": result["checks"]}, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--neural", action="store_true")
    validate(parser.parse_args())
