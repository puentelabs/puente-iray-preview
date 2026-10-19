"""Actualiza DLL/documentación y revalida el manifiesto de un candidato local."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--plugin", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    package = args.package.resolve(strict=True)
    path = package / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    assert manifest["public_release_ready"] is False, "Solo candidatos locales"
    shutil.copyfile(args.plugin, package / "plugins" / "dsp_PuenteIrayPreview.dll")
    shutil.copyfile(root / "docs" / "installation-draft.md", package / "LEEME.md")
    manifest.pop("nvidia_runtime_included", None)
    manifest["nvidia_nr_runtime_included"] = False
    files = []
    for file in sorted(package.rglob("*")):
        if not file.is_file() or file == path:
            continue
        assert not re.fullmatch(r"(?:_nvngx|nvngx_dlss(?:nr|d|g)?|nvofapi64|nvcuda)\.dll", file.name, re.I), file
        digest = hashlib.sha256()
        with file.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        files.append({"path": file.relative_to(package).as_posix(), "bytes": file.stat().st_size, "sha256": digest.hexdigest()})
    manifest["files"] = files
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"profile": manifest["profile"], "files": len(files), "bytes": sum(f["bytes"] for f in files), "nvidia_nr_runtime_included": False}))


if __name__ == "__main__":
    main()
