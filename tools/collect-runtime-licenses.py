"""Recoge avisos de las versiones instaladas exactas incluidas en la beta."""
import argparse
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import shutil


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package",type=Path,required=True)
    args=parser.parse_args()
    package=args.package.resolve(strict=True)
    pins=json.loads((package/"runtime-dependencies.json").read_text(encoding="utf-8-sig"))
    target=package/"plugins"/"PuenteIrayPreview"/"licenses"/"runtime"
    inventory=[]
    for name,version in sorted(pins.items()):
        distribution=metadata.distribution(name)
        if distribution.version!=version:raise ValueError(f"Versión distinta de {name}: {distribution.version} != {version}")
        entries=[]
        for relative in distribution.files or ():
            if ".." in relative.parts or not re.search(r"licen[cs]e|copying|notice|copyright",str(relative),re.I):continue
            source=Path(distribution.locate_file(relative))
            if not source.is_file() or source.suffix.lower() in (".pyc",".pyd",".dll"):continue
            destination=target/name/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,destination)
            entries.append(destination.relative_to(package).as_posix())
        inventory.append({"distribution":name,"version":version,"license_files":entries,
                          "license_metadata":distribution.metadata.get("License-Expression") or distribution.metadata.get("License")})
    (package/"third-party-license-inventory.json").write_text(json.dumps(inventory,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"distributions":len(inventory),"without_license_file":[x["distribution"] for x in inventory if not x["license_files"]],
                      "copied_files":sum(len(x["license_files"]) for x in inventory)}))


if __name__=="__main__":main()
