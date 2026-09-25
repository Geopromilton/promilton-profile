"""Horizon constraints: the geologist's interpretation added to the borehole data (as GMS horizon
coverages).

Three kinds, each for one horizon (by its number, as listed in the model, e.g. 4) or for every
horizon of a unit (by its code, e.g. code 4 = all fracture zones):

* pinchout  – a line along which the layer thins to zero (e.g. the edge of a fracture zone);
* absent    – a polygon where the layer does not exist (eroded, not deposited, dyke …);
* thickness – points of known thickness (from geophysics, a dug well, an outcrop …).

File formats
------------
CSV / Excel: columns ``Horizon, Type, X, Y`` and optionally ``Value`` (thickness, m) and ``Feature``
(an id grouping the vertices of one line or polygon, in order).

KML / KMZ / GeoJSON (e.g. drawn in Google Earth or QGIS): lines, polygons and points whose name is
``<horizon> <type> [value]``, for example ``H4 pinchout``, ``code 4 absent``, ``H7 thickness 6``.
GeoJSON may instead carry ``horizon``, ``type`` and ``value`` properties.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

KINDS = ("pinchout", "absent", "thickness")


@dataclass
class Constraint:
    target: str            # "h4" (horizon number 4, 1-based) or "c:4" (every horizon of code 4)
    kind: str              # pinchout | absent | thickness
    xy: np.ndarray         # (n, 2) vertices (one point for a thickness point)
    value: float = 0.0     # thickness for "thickness" points
    name: str = ""

    def applies_to(self, k: int, code: str) -> bool:
        return self.target == f"h{k + 1}" or self.target == f"c:{str(code).upper()}"


@dataclass
class Constraints:
    items: list = field(default_factory=list)
    source: str = ""
    crs_note: str = ""

    def __len__(self):
        return len(self.items)

    def for_horizon(self, k: int, code: str):
        return [c for c in self.items if c.applies_to(k, code)]

    def summary(self) -> str:
        if not self.items:
            return "no constraints"
        kinds = pd.Series([c.kind for c in self.items]).value_counts()
        return ", ".join(f"{n} {k}" for k, n in kinds.items())

    # -------------------------------------------------------------- effect on a horizon
    def extra_points(self, k: int, code: str, spacing: float):
        """Pseudo-boreholes (x, y, thickness) this horizon gets from pinch-out lines, thickness points
        and the edges of 'absent' polygons."""
        pts = []
        for c in self.for_horizon(k, code):
            if c.kind == "thickness":
                pts += [(x, y, c.value) for x, y in c.xy]
            elif c.kind == "pinchout":
                # spaced like boreholes, so a line counts about as much as the holes along it
                pts += [(x, y, 0.0) for x, y in _densify(c.xy, spacing)]
            # "absent" areas are applied as a mask (absent_mask), not as data points
        return np.array(pts, float).reshape(-1, 3)

    def absent_mask(self, k: int, code: str, gx, gy) -> np.ndarray | None:
        polys = [c.xy for c in self.for_horizon(k, code) if c.kind == "absent" and len(c.xy) >= 3]
        if not polys:
            return None
        from matplotlib.path import Path as MplPath

        X, Y = np.meshgrid(gx, gy)
        q = np.column_stack([X.ravel(), Y.ravel()])
        m = np.zeros(len(q), bool)
        for p in polys:
            m |= MplPath(p).contains_points(q)
        return m.reshape(X.shape)


def _densify(line, spacing):
    out = [line[0]]
    for a, b in zip(line[:-1], line[1:]):
        n = max(1, int(np.ceil(np.hypot(*(b - a)) / max(spacing, 1e-6))))
        for t in np.linspace(0, 1, n + 1)[1:]:
            out.append(a + (b - a) * t)
    return np.array(out)


# ---------------------------------------------------------------------------- reading
_NAME = re.compile(r"^\s*(?:(h|horizon)\s*#?\s*(\d+)|(?:code|c|unit)\s*[:=]?\s*([\w\-]+))\s*[:,\-]?\s*"
                   r"(pinch-?out|absent|missing|thickness)\s*[:=]?\s*([\d.]+)?", re.I)


def _parse_name(name: str):
    m = _NAME.match(name or "")
    if not m:
        return None
    target = f"h{int(m.group(2))}" if m.group(2) else f"c:{m.group(3).upper()}"
    kind = m.group(4).lower().replace("-", "")
    kind = "absent" if kind == "missing" else kind
    return target, kind, float(m.group(5)) if m.group(5) else 0.0


def _target(value) -> str:
    v = str(value).strip()
    m = re.match(r"^(?:h|horizon)\s*#?\s*(\d+)$", v, re.I)
    if m:
        return f"h{int(m.group(1))}"
    m = re.match(r"^(?:code|c|unit)\s*[:=]?\s*(.+)$", v, re.I)
    if m:
        return f"c:{m.group(1).strip().upper()}"
    return f"h{int(float(v))}" if re.match(r"^\d+(\.0)?$", v) else f"c:{v.upper()}"


def load_constraints(path, crs: str | None = None, near=None) -> Constraints:
    """Read constraints (CSV/Excel table, KML/KMZ or GeoJSON) into the boreholes' coordinates."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in (".csv", ".txt", ".xlsx", ".xls"):
        items = _read_table(path)
        src = None
    elif ext in (".kml", ".kmz"):
        items, src = _read_kml(path), "EPSG:4326"
    elif ext in (".geojson", ".json"):
        items, src = _read_geojson(path), "EPSG:4326"
    else:
        raise ValueError(f"{path.name}: constraints must be CSV/Excel, KML/KMZ or GeoJSON")
    if not items:
        raise ValueError(f"{path.name}: no constraints found (names like 'H4 pinchout', 'code 4 absent', "
                         "'H7 thickness 6')")
    note = ""
    if src:
        dst = crs or _utm_for(items, near)
        from pyproj import Transformer

        t = Transformer.from_crs(src, dst, always_xy=True)
        for c in items:
            c.xy = np.column_stack(t.transform(c.xy[:, 0], c.xy[:, 1]))
        note = f"latitude/longitude → {dst}"
    for c in items:
        if c.kind not in KINDS:
            raise ValueError(f"Unknown constraint type '{c.kind}' (use pinchout, absent or thickness)")
    return Constraints(items, path.name, note)


def _utm_for(items, near):
    from .aquifer import utm_epsg

    allp = np.vstack([c.xy for c in items])
    lon, lat = allp[:, 0].mean(), allp[:, 1].mean()
    zone = utm_epsg(lon, lat)
    if near is None:
        return f"EPSG:{zone}"
    from pyproj import Transformer

    for dz in (0, -1, 1, -2, 2):
        z = zone + dz
        x, y = Transformer.from_crs("EPSG:4326", f"EPSG:{z}", always_xy=True).transform(lon, lat)
        if near[0] - 50_000 < x < near[1] + 50_000 and near[2] - 50_000 < y < near[3] + 50_000:
            return f"EPSG:{z}"
    return f"EPSG:{zone}"


def _read_table(path: Path):
    from .io import normalize

    df = pd.read_excel(path) if path.suffix.lower() in (".xlsx", ".xls") else \
        pd.read_csv(path, sep=None, engine="python")
    df.columns = [normalize(c) for c in df.columns]
    df = df.rename(columns={"layer": "horizon", "kind": "type", "thickness": "value", "id": "feature",
                            "easting": "x", "northing": "y"})
    need = {"horizon", "type", "x", "y"} - set(df.columns)
    if need:
        raise ValueError(f"{path.name}: constraint table needs columns Horizon, Type, X, Y "
                         f"(missing: {', '.join(sorted(need))})")
    if "feature" not in df.columns:
        df["feature"] = np.nan
    blank = df["feature"].isna() | (df["feature"].astype(str).str.strip() == "")
    df.loc[blank, "feature"] = [f"_row{i}" for i in df.index[blank]]    # every such row its own point
    df["feature"] = df["feature"].astype(str)
    items = []
    for _, g in df.groupby(["feature", "horizon", "type"], sort=False):
        kind = str(g["type"].iloc[0]).strip().lower().replace("-", "").replace(" ", "")
        kind = "absent" if kind == "missing" else kind
        val = float(g["value"].iloc[0]) if "value" in g and pd.notna(g["value"].iloc[0]) else 0.0
        xy = g[["x", "y"]].to_numpy(float)
        if kind == "thickness":
            items += [Constraint(_target(g["horizon"].iloc[0]), kind, xy[i:i + 1], float(v) if pd.notna(v) else val)
                      for i, v in enumerate(g["value"] if "value" in g else [val] * len(g))]
        else:
            items.append(Constraint(_target(g["horizon"].iloc[0]), kind, xy, val))
    return items


def _coords(text):
    pts = [tuple(map(float, t.split(",")[:2])) for t in text.split() if "," in t]
    return np.array(pts, float)


def _read_kml(path: Path):
    import xml.etree.ElementTree as ET
    import zipfile

    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path) as z:
            data = z.read(next(n for n in z.namelist() if n.lower().endswith(".kml")))
    else:
        data = path.read_bytes()
    tag = lambda e: e.tag.rsplit("}", 1)[-1]  # noqa: E731
    items = []
    for pm in ET.fromstring(data).iter():
        if tag(pm) != "Placemark":
            continue
        name = next((e.text for e in pm if tag(e) == "name"), "")
        parsed = _parse_name(name or "")
        if not parsed:
            continue
        target, kind, value = parsed
        for g in pm.iter():
            if tag(g) in ("Point", "LineString", "LinearRing"):
                c = next((e.text for e in g.iter() if tag(e) == "coordinates" and e.text), None)
                if c is None:
                    continue
                xy = _coords(c)
                if kind == "absent" and len(xy) > 3 and np.allclose(xy[0], xy[-1]):
                    xy = xy[:-1]
                if tag(g) == "LinearRing" and kind != "absent":
                    continue
                items.append(Constraint(target, kind, xy, value, name))
    return items


def _read_geojson(path: Path):
    import json

    gj = json.loads(path.read_text())
    feats = gj.get("features", [gj]) if gj.get("type") in ("FeatureCollection", "Feature") else []
    items = []
    for f in feats:
        pr = f.get("properties") or {}
        if "horizon" in pr and "type" in pr:
            target, kind, value = _target(pr["horizon"]), str(pr["type"]).lower().replace("-", ""), \
                float(pr.get("value") or 0)
        else:
            parsed = _parse_name(pr.get("name", ""))
            if not parsed:
                continue
            target, kind, value = parsed
        g = f.get("geometry") or {}
        t, co = g.get("type"), g.get("coordinates")
        parts = {"Point": [[co]], "MultiPoint": [co], "LineString": [co], "MultiLineString": co,
                 "Polygon": co[:1] if co else [], "MultiPolygon": [p[0] for p in co] if co else []}.get(t, [])
        for part in parts:
            xy = np.asarray(part, float)[:, :2]
            if t in ("Polygon", "MultiPolygon") and len(xy) > 3 and np.allclose(xy[0], xy[-1]):
                xy = xy[:-1]
            if t in ("Point", "MultiPoint"):
                items += [Constraint(target, kind, p[None], value, pr.get("name", "")) for p in xy]
            else:
                items.append(Constraint(target, kind, xy, value, pr.get("name", "")))
    return items
