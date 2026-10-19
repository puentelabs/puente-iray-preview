"""Añade una distribución exacta ya instalada a un candidato local, sin pip."""
import argparse
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distribution", required=True)
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve(strict=True)
    destination = package / "plugins" / "PuenteIrayPreview" / "_internal"
    assert destination.is_dir()
    distribution = metadata.distribution(args.distribution)
    count = 0
    for relative in distribution.files or ():
        if ".." in relative.parts or relative.suffix == ".pyc" or "__pycache__" in relative.parts:
            continue
        source = Path(distribution.locate_file(relative))
        if not source.is_file():
            continue
        target = destination / relative
        if target.exists():
            assert target.read_bytes() == source.read_bytes(), f"No se reemplaza un componente distinto: {relative}"
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        count += 1
    pins_path = package / "runtime-dependencies.json"
    pins = json.loads(pins_path.read_text(encoding="utf-8-sig"))
    pins[args.distribution] = distribution.version
    pins_path.write_text(json.dumps(pins, indent=2), encoding="utf-8")
    print(json.dumps({"distribution": args.distribution, "version": distribution.version, "files": count}))


if __name__ == "__main__":
    main()
