"""Ejecutable privado del plugin: diagnóstico, preview y postprocesamiento."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys

from packaged_runtime import application_root, frozen


def check(argv):
    parser = argparse.ArgumentParser(description="Comprueba el runtime incluido antes de renderizar")
    parser.add_argument("--nr", action="store_true")
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--upscale", action="store_true")
    parser.add_argument("--scale", type=int, choices=(1, 2, 4), default=1)
    args = parser.parse_args(argv)
    result = {"status": "failed", "frozen": frozen(), "packages": {}, "errors": []}
    try:
        import numpy
        from PIL import Image, ImageCms
        for name in ("numpy", "Pillow"):
            result["packages"][name] = importlib.metadata.version(name)
        if args.nr:
            from prototype import BRIDGE, SHIM
            required = [BRIDGE, SHIM]
            if args.runtime is None:
                result["errors"].append("Selecciona la carpeta de tu runtime NR compatible.")
            else:
                required += [args.runtime / "nvngx_dlssnr.dll", args.runtime / "caller" / "nvngx.dll_comfy.dll"]
            for path in required:
                if not path.is_file():
                    result["errors"].append(f"Falta el componente: {path}")
        if args.upscale:
            if args.scale not in (2, 4):
                raise ValueError("Real-ESRGAN requiere escala 2 o 4")
            import torch
            import spandrel
            from prototype import sha256
            from render_worker import MODELS
            result["packages"]["torch"] = torch.__version__
            result["packages"]["spandrel"] = importlib.metadata.version("spandrel")
            if not torch.cuda.is_available():
                result["errors"].append("El runtime incluido no puede usar CUDA en esta GPU/controlador.")
            else:
                result["gpu"] = torch.cuda.get_device_name()
            name, expected, _ = MODELS[args.scale]
            weights = application_root() / "runtime" / "upscale" / name
            if not weights.is_file() or sha256(weights) != expected:
                result["errors"].append(f"Modelo ausente o checksum incorrecto: {name}")
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    result["status"] = "passed" if not result["errors"] else "failed"
    result["error"] = "\n".join(result["errors"])
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return 0 if result["status"] == "passed" else 2


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("check", "viewport", "render"):
        print("Uso: puente-worker check|viewport|render [opciones]", file=sys.stderr)
        return 2
    operation = sys.argv.pop(1)
    if operation == "check":
        return check(sys.argv[1:])
    if operation == "viewport":
        from viewport_worker import main as run
    else:
        from render_worker import main as run
    return run()


if __name__ == "__main__":
    sys.exit(main())
