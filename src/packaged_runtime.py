"""Rutas del ejecutable autocontenido y de los workers en desarrollo."""
from pathlib import Path
import sys


def frozen():
    return bool(getattr(sys, "frozen", False))


def application_root():
    return Path(sys.executable).resolve().parent if frozen() else Path(__file__).resolve().parent


def worker_command(operation):
    if frozen():
        return [sys.executable, operation]
    scripts = {"viewport": "viewport_worker.py", "render": "render_worker.py"}
    return [sys.executable, "-B", str(application_root() / scripts[operation])]
