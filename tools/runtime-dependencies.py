"""Fija la clausura de dependencias declaradas, excluyendo el resto del entorno."""
import argparse
import importlib.metadata as metadata
import json
import sys
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("Core", "Full"), required=True)
    args = parser.parse_args()
    pending = ["numpy", "Pillow", "packaging"]
    if args.profile == "Full":
        # optree es importado por el pytree de este PyTorch aunque no aparezca
        # como dependencia obligatoria en sus metadatos de distribución.
        pending += ["torch", "spandrel", "optree"]
    allowed = {}
    while pending:
        name = canonicalize_name(pending.pop())
        if name in allowed:
            continue
        distribution = metadata.distribution(name)
        allowed[name] = distribution.version
        for raw in distribution.requires or ():
            requirement = Requirement(raw)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    excluded = set()
    for module, distributions in metadata.packages_distributions().items():
        if module in sys.stdlib_module_names or not module.isidentifier():
            continue
        if not any(canonicalize_name(name) in allowed for name in distributions):
            excluded.add(module)
    # No forma parte de nuestro código de inferencia. En instalaciones antiguas
    # puede existir una copia incompatible con Python 3.12 aunque setuptools sea nuevo.
    excluded.add("pkg_resources")
    print(json.dumps({"profile": args.profile, "pins": dict(sorted(allowed.items())), "exclude_modules": sorted(excluded)}))


if __name__ == "__main__":
    main()
