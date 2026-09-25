"""Study-area boundaries from polygon shapefiles (with reprojection).

Boreholes carry no coordinate system of their own, so the boundary is
brought into theirs: either an explicit EPSG code (``crs=``) or, when the
boundary is in UTM and does not overlap the boreholes, the neighbouring UTM
zone of the same datum that does (a common mix-up near zone edges).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Boundary:
    rings: list                      # list of (n, 2) arrays: outer rings and holes
    name: str = "Study area"
    crs_note: str = ""
    source_crs: object = None
    info: dict = field(default_factory=dict)

    @property
    def bbox(self):
        allp = np.vstack(self.rings)
        return allp[:, 0].min(), allp[:, 0].max(), allp[:, 1].min(), allp[:, 1].max()

    @property
    def path(self):
        """Compound matplotlib Path (even-odd: holes and multiple parts work)."""
        from matplotlib.path import Path as MplPath

        verts, codes = [], []
        for r in self.rings:
            verts += [tuple(p) for p in r] + [tuple(r[0])]
            codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(r) - 1) + [MplPath.CLOSEPOLY]
        return MplPath(verts, codes)

    @property
    def area(self) -> float:
        """Area in map units²; rings lying inside an odd number of others are holes."""
        total = 0.0
        for i, r in enumerate(self.rings):
            depth = sum(int(_ring_contains(o, r[:1])[0]) for j, o in enumerate(self.rings) if j != i)
            total += _ring_area(r) if depth % 2 == 0 else -_ring_area(r)
        return total

    def contains(self, xy) -> np.ndarray:
        xy = np.atleast_2d(np.asarray(xy, float))
        hits = np.zeros(len(xy), int)
        for r in self.rings:
            hits += _ring_contains(r, xy)
        return hits % 2 == 1

    def mask(self, gx, gy, buffer: float = 0.0) -> np.ndarray:
        """Grid mask: cell centre inside the boundary, or within ``buffer`` of its edge."""
        X, Y = np.meshgrid(gx, gy)
        q = np.column_stack([X.ravel(), Y.ravel()])
        m = self.contains(q)
        if buffer > 0:
            m |= self.distance(q) <= buffer
        return m.reshape(X.shape)

    def distance(self, q) -> np.ndarray:
        q = np.asarray(q, float)
        best = np.full(len(q), np.inf)
        for r in self.rings:
            a, b = r, np.roll(r, -1, axis=0)
            d = b - a
            L2 = np.maximum((d ** 2).sum(1), 1e-12)
            for s in range(0, len(q), 5000):
                qq = q[s:s + 5000]
                t = np.clip(((qq[:, None, :] - a[None]) * d[None]).sum(2) / L2[None], 0, 1)
                near = a[None] + t[..., None] * d[None]
                best[s:s + 5000] = np.minimum(best[s:s + 5000],
                                              np.hypot(*(qq[:, None, :] - near).transpose(2, 0, 1)).min(1))
        return best

    def patch(self, ax, **kw):
        from matplotlib.patches import PathPatch

        return PathPatch(self.path, transform=ax.transData, **kw)


def _ring_area(r):
    x, y = r[:, 0], r[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def _ring_contains(ring, xy):
    from matplotlib.path import Path as MplPath

    xy = np.atleast_2d(xy)
    return MplPath(ring).contains_points(xy).astype(int)


def load_boundary(path, crs: str | None = None, near=None) -> Boundary:
    """Read polygon(s) from a shapefile (.shp with .prj).

    ``crs``: EPSG code / CRS string of the borehole coordinates. ``near``:
    (xmin, xmax, ymin, ymax) of the boreholes, used to auto-pick the UTM zone
    when ``crs`` is not given.
    """
    import shapefile  # pyshp

    path = Path(path)
    reader = shapefile.Reader(str(path))
    rings = []
    for shp in reader.shapes():
        if shp.shapeType not in (shapefile.POLYGON, shapefile.POLYGONZ, shapefile.POLYGONM):
            continue
        pts = np.asarray(shp.points, float)[:, :2]
        parts = list(shp.parts) + [len(pts)]
        for a, b in zip(parts[:-1], parts[1:]):
            if b - a >= 3:
                rings.append(pts[a:b])
    if not rings:
        raise ValueError(f"{path.name}: no polygons found (the boundary must be a polygon shapefile)")
    b = Boundary(rings, name=path.stem)

    prj = path.with_suffix(".prj")
    src = None
    if prj.exists():
        try:
            from pyproj import CRS

            src = CRS.from_wkt(prj.read_text())
        except Exception:  # noqa: BLE001 - pyproj missing or unreadable .prj
            src = None
    b.source_crs = src
    if crs:
        _reproject(b, src, crs)
        b.crs_note = f"reprojected {_crs_name(src)} → {crs}"
    elif near is not None and not _overlaps(b.bbox, near):
        zone = _auto_utm(b, src, near)
        if zone is None:
            raise ValueError(
                f"The boundary ({_crs_name(src)}) does not overlap the boreholes. Give the boreholes' "
                "coordinate system with --crs, e.g. --crs EPSG:32643 for WGS 84 / UTM zone 43N.")
        b.crs_note = f"boundary was in {_crs_name(src)}; reprojected to {zone} to match the boreholes"
    return b


def _crs_name(src):
    if src is None:
        return "an unknown coordinate system"
    if src.is_compound:  # e.g. UTM + vertical datum: name the horizontal part
        src = src.sub_crs_list[0]
    epsg = src.to_epsg()
    return f"EPSG:{epsg} ({src.name})" if epsg else src.name


def _reproject(b: Boundary, src, dst):
    from pyproj import CRS, Transformer

    if src is None:
        raise ValueError("The shapefile has no .prj, so it cannot be reprojected; "
                         "save it in the boreholes' coordinate system instead")
    t = Transformer.from_crs(src, CRS.from_user_input(dst), always_xy=True)
    b.rings = [np.column_stack(t.transform(r[:, 0], r[:, 1])) for r in b.rings]


def _overlaps(a, b):
    return not (a[1] < b[0] or b[1] < a[0] or a[3] < b[2] or b[3] < a[2])


def _auto_utm(b: Boundary, src, near):
    """Try neighbouring UTM zones (same datum/hemisphere); keep the best overlap."""
    try:
        from pyproj import CRS
    except ImportError:
        return None
    if src is None or not src.utm_zone:
        return None
    zone, hemi = int(src.utm_zone[:-1]), src.utm_zone[-1]
    base = 32600 if hemi == "N" else 32700  # WGS 84 / UTM zones
    best = None
    orig = [r.copy() for r in b.rings]
    for dz in (-1, 1, -2, 2):
        z = zone + dz
        if not 1 <= z <= 60:
            continue
        dst = f"EPSG:{base + z}"
        b.rings = [r.copy() for r in orig]
        _reproject(b, src, CRS.from_user_input(dst))
        bx = b.bbox
        if _overlaps(bx, near):
            ov = (min(bx[1], near[1]) - max(bx[0], near[0])) * (min(bx[3], near[3]) - max(bx[2], near[2]))
            if best is None or ov > best[0]:
                best = (ov, dst, [r.copy() for r in b.rings])
    if best is None:
        b.rings = orig
        return None
    b.rings = best[2]
    return best[1]
