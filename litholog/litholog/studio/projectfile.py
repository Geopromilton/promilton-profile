"""LithoLog project files (.llproj): JSON with data paths and settings.

Paths are stored relative to the project file when possible, so a project
folder can be copied to another computer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

FORMAT = "litholog-project"
VERSION = 1


def _rel(p, base: Path):
    if not p:
        return None
    try:
        return os.path.relpath(Path(p).resolve(), base)
    except ValueError:  # different drive on Windows
        return str(Path(p).resolve())


def save(path, name, data, legend=None, boundary=None, settings=None):
    path = Path(path)
    base = path.resolve().parent
    doc = {"format": FORMAT, "version": VERSION, "name": name, "data": _rel(data, base),
           "legend": _rel(legend, base), "boundary": _rel(boundary, base), "settings": settings or {}}
    path.write_text(json.dumps(doc, indent=2))
    return path


def load(path) -> dict:
    path = Path(path)
    doc = json.loads(path.read_text())
    if doc.get("format") != FORMAT:
        raise ValueError(f"{path.name} is not a LithoLog project file")
    base = path.resolve().parent
    for k in ("data", "legend", "boundary"):
        if doc.get(k):
            p = Path(doc[k])
            doc[k] = str(p if p.is_absolute() else (base / p).resolve())
    if not doc.get("data") or not Path(doc["data"]).exists():
        raise FileNotFoundError(f"Borehole data not found: {doc.get('data')}")
    doc.setdefault("settings", {})
    return doc
