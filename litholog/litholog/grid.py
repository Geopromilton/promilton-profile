"""Per-borehole attributes and 2D gridding (IDW, linear, ordinary kriging).

Attributes are given as short strings:

    ground            collar (ground) elevation
    top:CODE          elevation of the first occurrence of CODE
    base:CODE         elevation of the last base of CODE
    depth:CODE        depth (m bgl) to the first occurrence of CODE
    thickness:CODE    total thickness of CODE in the hole (0 where absent)
    water             water-table elevation (latest measurement)
    dtw               depth to water (m bgl, latest measurement)
    total_depth       drilled depth
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .correlate import units
from .project import Project


def attribute_label(attr: str, legend=None) -> tuple[str, str]:
    """(title, unit) for an attribute string."""
    kind, _, code = attr.partition(":")
    name = legend.get(code).name if (legend is not None and code) else code
    return {
        "ground": ("Ground elevation", "m amsl"),
        "top": (f"Top of {name}", "m amsl"),
        "base": (f"Base of {name}", "m amsl"),
        "depth": (f"Depth to {name}", "m bgl"),
        "thickness": (f"Thickness of {name}", "m"),
        "water": ("Water-table elevation", "m amsl"),
        "dtw": ("Depth to water", "m bgl"),
        "total_depth": ("Drilled depth", "m"),
    }.get(kind, (attr, ""))


def borehole_values(project: Project, attr: str) -> pd.DataFrame:
    """Table borehole_id, x, y, value for one attribute (NaN where undefined)."""
    kind, _, code = attr.partition(":")
    code = code.strip().upper() if code else ""
    if kind in ("top", "base", "depth", "thickness") and not code:
        raise ValueError(f"'{attr}': give a lithology code, e.g. {kind}:GRA")
    if kind not in ("ground", "top", "base", "depth", "thickness", "water", "dtw", "total_depth"):
        raise ValueError(f"Unknown attribute '{attr}'")
    rows = []
    for bh in project:
        v = np.nan
        us = units(bh)
        hit = [u for u in us if u.code.upper() == code]
        ground = us[0].top if us else (bh.elevation if bh.has_elevation else np.nan)
        wl = bh.water_levels.dropna(subset=["depth"])
        if kind == "ground":
            v = bh.elevation
        elif kind == "top" and hit:
            v = hit[0].top
        elif kind == "base" and hit:
            v = hit[-1].bot
        elif kind == "depth" and hit:
            v = ground - hit[0].top
        elif kind == "thickness" and us:
            v = sum(u.thick for u in hit)
        elif kind == "water" and len(wl) and bh.has_elevation:
            v = bh.elevation - wl.iloc[-1]["depth"]
        elif kind == "dtw" and len(wl):
            v = wl.iloc[-1]["depth"]
        elif kind == "total_depth":
            v = bh.depth
        rows.append({"borehole_id": bh.id, "x": bh.x, "y": bh.y, "value": v})
    return pd.DataFrame(rows)


@dataclass
class Grid:
    x: np.ndarray       # cell-centre x (nx,)
    y: np.ndarray       # cell-centre y (ny,)
    z: np.ndarray       # values (ny, nx); NaN = masked
    cell: float
    inside: np.ndarray | None = None   # exact study-area cells (for volumes/export)
    boundary: object = None            # Boundary used for clipping, if any
    coverage: float | None = None      # fraction of the study area inside the boreholes' hull

    @property
    def valid(self):
        return np.isfinite(self.z) if self.inside is None else (self.inside & np.isfinite(self.z))

    @property
    def extent(self):
        h = self.cell / 2
        return (self.x[0] - h, self.x[-1] + h, self.y[0] - h, self.y[-1] + h)

    def mesh(self):
        return np.meshgrid(self.x, self.y)


def make_axes(xs, ys, cell: float | None = None, margin: float = 0.05, target: int = 150):
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    span = max(x1 - x0, y1 - y0) or 100.0
    pad = span * margin
    x0, x1, y0, y1 = x0 - pad, x1 + pad, y0 - pad, y1 + pad
    if not cell:
        raw = span * (1 + 2 * margin) / target
        mag = 10 ** np.floor(np.log10(raw))
        # nearest "round" size (log scale) to the target
        cell = float(min((m * mag for m in (1, 2, 2.5, 5, 10)), key=lambda c: abs(np.log(c / raw))))
    gx = np.arange(np.floor(x0 / cell) * cell + cell / 2, x1 + cell, cell)
    gy = np.arange(np.floor(y0 / cell) * cell + cell / 2, y1 + cell, cell)
    return gx, gy, cell


def hull_mask(px, py, gx, gy, buffer: float = 0.0):
    """True inside the convex hull of the points, or within ``buffer`` m of its edge."""
    from matplotlib.path import Path as MplPath
    from scipy.spatial import ConvexHull

    X, Y = np.meshgrid(gx, gy)
    q = np.column_stack([X.ravel(), Y.ravel()])
    pts = np.column_stack([px, py]).astype(float)
    hull = pts[ConvexHull(pts).vertices]
    inside = MplPath(hull).contains_points(q)
    if buffer > 0:
        a, b = hull, np.roll(hull, -1, axis=0)
        d = b - a
        L2 = np.maximum((d ** 2).sum(1), 1e-12)
        t = np.clip(((q[:, None, :] - a[None]) * d[None]).sum(2) / L2[None], 0, 1)
        nearest = a[None] + t[..., None] * d[None]
        dist = np.hypot(*(q[:, None, :] - nearest).transpose(2, 0, 1)).min(1)
        inside |= dist <= buffer
    return inside.reshape(X.shape)


@dataclass
class Interp:
    """How strongly, and how far, each borehole influences an interpolated surface (as in GMS).

    method: "idw", "kriging", "linear" (TIN) or "smooth" (Clough-Tocher smooth TIN).
    power: IDW exponent - higher keeps each borehole's influence local, lower spreads it.
    neighbours: use only the N nearest boreholes for each point (None = all).
    radius: search radius (m); boreholes farther away have no influence (the nearest one is
        used where none is within the radius).
    variogram: "spherical", "exponential" or "gaussian"; range/sill/nugget None = fitted to the data.
    """

    method: str = "idw"
    power: float = 2.0
    neighbours: int | None = None
    radius: float | None = None
    variogram: str = "spherical"
    range: float | None = None
    sill: float | None = None
    nugget: float | None = None

    def label(self) -> str:
        m = {"idw": f"IDW (power {self.power:g})", "kriging": f"kriging ({self.variogram})",
             "linear": "linear TIN", "smooth": "smooth TIN"}.get(self.method, self.method)
        extra = []
        if self.neighbours:
            extra.append(f"{self.neighbours} nearest")
        if self.radius:
            extra.append(f"radius {self.radius:g} m")
        if self.method == "kriging" and self.range:
            extra.append(f"range {self.range:g} m")
        return m + (f", {', '.join(extra)}" if extra else "")


def as_interp(method, power: float = 2.0) -> Interp:
    return method if isinstance(method, Interp) else Interp(str(method), power)


def interpolate(px, py, pv, gx, gy, method="idw", power: float = 2.0):
    """Interpolate point values onto the grid gx × gy. ``method`` is a name or an ``Interp``."""
    o = as_interp(method, power)
    px, py, pv = (np.asarray(a, float) for a in (px, py, pv))
    X, Y = np.meshgrid(gx, gy)
    tx, ty = X.ravel(), Y.ravel()
    if len(pv) == 1:
        return np.full(X.shape, pv[0])
    if o.method == "idw":
        out = _idw(px, py, pv, tx, ty, o)
    elif o.method in ("linear", "smooth"):
        from scipy.interpolate import griddata

        out = griddata((px, py), pv, (tx, ty), method="linear" if o.method == "linear" else "cubic")
        near = griddata((px, py), pv, (tx, ty), method="nearest")
        out = np.where(np.isnan(out), near, out)
    elif o.method == "kriging":
        out = _ordinary_kriging(px, py, pv, tx, ty, o)
    else:
        raise ValueError(f"Unknown gridding method '{o.method}' (idw, kriging, linear, smooth)")
    return out.reshape(X.shape)


def _neighbourhood(px, py, tx, ty, o, k_default=None):
    """Indices and distances of the boreholes that influence each target point."""
    from scipy.spatial import cKDTree

    n = len(px)
    k = min(o.neighbours or k_default or n, n)
    tree = cKDTree(np.column_stack([px, py]))
    d, i = tree.query(np.column_stack([tx, ty]), k=k)
    d, i = np.atleast_2d(d.T).T if k == 1 else d, np.atleast_2d(i.T).T if k == 1 else i
    if o.radius:
        far = d > o.radius
        far[:, 0] = False            # always keep the nearest borehole
        d = np.where(far, np.inf, d)
    return d, i


def _idw(px, py, pv, tx, ty, o):
    if not o.neighbours and not o.radius:
        d = np.hypot(tx[:, None] - px[None, :], ty[:, None] - py[None, :])
        exact = d < 1e-9
        w = 1.0 / np.maximum(d, 1e-9) ** o.power
        out = (w @ pv) / w.sum(1)
        hit = exact.any(1)
        out[hit] = pv[exact[hit].argmax(1)]
        return out
    d, i = _neighbourhood(px, py, tx, ty, o)
    w = np.where(np.isfinite(d), 1.0 / np.maximum(d, 1e-9) ** o.power, 0.0)
    out = (w * pv[i]).sum(1) / w.sum(1)
    exact = d[:, 0] < 1e-9
    out[exact] = pv[i[exact, 0]]
    return out


def _spherical(h, nugget, sill, rng):
    h = np.asarray(h, float)
    g = np.where(h < rng, nugget + (sill - nugget) * (1.5 * h / rng - 0.5 * (h / rng) ** 3), sill)
    return np.where(h == 0, 0.0, g)


def _exponential(h, nugget, sill, rng):   # practical range: 95 % of the sill at h = range
    h = np.asarray(h, float)
    return np.where(h == 0, 0.0, nugget + (sill - nugget) * (1 - np.exp(-3 * h / rng)))


def _gaussian(h, nugget, sill, rng):
    h = np.asarray(h, float)
    return np.where(h == 0, 0.0, nugget + (sill - nugget) * (1 - np.exp(-3 * (h / rng) ** 2)))


VARIOGRAMS = {"spherical": _spherical, "exponential": _exponential, "gaussian": _gaussian}


def experimental_variogram(px, py, pv, n_lags: int = 12):
    """(lag distance, semivariance, pair count) of the data, up to half the largest separation."""
    px, py, pv = (np.asarray(a, float) for a in (px, py, pv))
    d = np.hypot(px[:, None] - px[None, :], py[:, None] - py[None, :])
    g = 0.5 * (pv[:, None] - pv[None, :]) ** 2
    iu = np.triu_indices(len(pv), 1)
    d, g = d[iu], g[iu]
    maxd = d.max() / 2 if len(d) else 1.0
    edges = np.linspace(0, maxd, n_lags + 1)
    lag, gam, cnt = [], [], []
    for a, b in zip(edges[:-1], edges[1:]):
        sel = (d > a) & (d <= b)
        if sel.sum() >= 3:
            lag.append(d[sel].mean())
            gam.append(g[sel].mean())
            cnt.append(int(sel.sum()))
    return np.array(lag), np.array(gam), np.array(cnt)


def fit_variogram(px, py, pv, n_lags: int = 12, model: str = "spherical"):
    """Fit a variogram model (nugget, sill, range) to the experimental one."""
    from scipy.optimize import curve_fit

    d = np.hypot(px[:, None] - px[None, :], py[:, None] - py[None, :])
    g = 0.5 * (pv[:, None] - pv[None, :]) ** 2
    iu = np.triu_indices(len(pv), 1)
    d, g = d[iu], g[iu]
    var = float(np.var(pv)) or 1.0
    maxd = d.max() / 2 if len(d) else 1.0
    edges = np.linspace(0, maxd, n_lags + 1)
    lag, gam = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        sel = (d > a) & (d <= b)
        if sel.sum() >= 3:
            lag.append(d[sel].mean())
            gam.append(g[sel].mean())
    if len(lag) < 3:
        return 0.0, var, maxd
    try:
        (n, s, r), _ = curve_fit(VARIOGRAMS[model], lag, gam, p0=[0.1 * var, var, maxd / 2],
                                 bounds=([0, 1e-9, maxd / 50], [var * 2, var * 4, maxd * 4]))
        return float(n), float(s), float(r)
    except Exception:  # noqa: BLE001 - fall back to a sensible default model
        return 0.0, var, maxd / 2


def variogram_params(px, py, pv, o=None):
    """(model function, nugget, sill, range): the user's values where given, fitted otherwise."""
    o = o or Interp("kriging")
    f = VARIOGRAMS.get(o.variogram, _spherical)
    nug, sill, rng = fit_variogram(px, py, pv, model=o.variogram if o.variogram in VARIOGRAMS else "spherical")
    return (f, nug if o.nugget is None else o.nugget, sill if o.sill is None else o.sill,
            rng if o.range is None else o.range)


def _ordinary_kriging(px, py, pv, tx, ty, o=None):
    o = o or Interp("kriging")
    f, nug, sill, rng = variogram_params(px, py, pv, o)
    n = len(pv)
    if o.neighbours and o.neighbours < n or o.radius:
        # local kriging: a small system per point with its nearest boreholes only
        k = min(o.neighbours or 16, n)
        d, idx = _neighbourhood(px, py, tx, ty, Interp(neighbours=k, radius=o.radius))
        out = np.empty(len(tx))
        for s in range(0, len(tx), 5000):
            ii = idx[s:s + 5000]
            valid = np.isfinite(d[s:s + 5000])
            xs, ys = px[ii], py[ii]
            dd = np.hypot(xs[:, :, None] - xs[:, None, :], ys[:, :, None] - ys[:, None, :])
            m = len(ii)
            K = np.ones((m, k + 1, k + 1))
            K[:, :k, :k] = f(dd, nug, sill, rng)
            K[:, k, k] = 0.0
            # boreholes outside the search radius: decouple them (weight forced to zero)
            off = ~valid
            K[:, :k, :k][np.broadcast_to(off[:, :, None], (m, k, k)) | np.broadcast_to(off[:, None, :], (m, k, k))] = 0
            K[:, :k, :k][:, np.arange(k), np.arange(k)] = np.where(off, 1.0, 0.0)
            K[:, :k, k] = np.where(off, 0.0, 1.0)
            K[:, k, :k] = np.where(off, 0.0, 1.0)
            rhs = np.concatenate([np.where(off, 0.0, f(np.where(valid, d[s:s + 5000], 0), nug, sill, rng)),
                                  np.ones((m, 1))], axis=1)
            try:
                w = np.linalg.solve(K, rhs[..., None])[..., 0]
            except np.linalg.LinAlgError:
                w = np.stack([np.linalg.lstsq(K[j], rhs[j], rcond=None)[0] for j in range(m)])
            out[s:s + 5000] = (w[:, :k] * pv[ii]).sum(1)
        return out
    dmat = np.hypot(px[:, None] - px[None, :], py[:, None] - py[None, :])
    K = np.ones((n + 1, n + 1))
    K[:n, :n] = f(dmat, nug, sill, rng)
    K[n, n] = 0.0
    out = np.empty(len(tx))
    for s in range(0, len(tx), 20000):  # chunk to bound memory
        dt = np.hypot(px[:, None] - tx[None, s:s + 20000], py[:, None] - ty[None, s:s + 20000])
        rhs = np.vstack([f(dt, nug, sill, rng), np.ones((1, dt.shape[1]))])
        w = np.linalg.lstsq(K, rhs, rcond=None)[0]
        out[s:s + 20000] = w[:n].T @ pv
    return out


def grid_attribute(project: Project, attr: str, method: str = "idw", cell: float | None = None,
                   mask: str = "hull", buffer: float = 0.0, boundary=None):
    """Grid one attribute. Returns (Grid, borehole value table).

    With a ``boundary`` the grid covers and is clipped to the study area
    (values outside the boreholes' hull are extrapolated).
    """
    vals = borehole_values(project, attr)
    allxy = project.boreholes.dropna(subset=["x", "y"])
    good = vals.dropna(subset=["x", "y", "value"])
    if len(good) < 2:
        raise ValueError(f"'{attr}': fewer than two boreholes have a value")
    if boundary is not None:
        x0, x1, y0, y1 = boundary.bbox
        gx, gy, cell = make_axes(np.r_[allxy["x"], x0, x1], np.r_[allxy["y"], y0, y1], cell, margin=0.02)
        z = interpolate(good["x"], good["y"], good["value"], gx, gy, method)
        inside = boundary.mask(gx, gy)
        z = np.where(boundary.mask(gx, gy, 2 * cell), z, np.nan)  # margin keeps edge contours smooth
        cov = coverage(allxy["x"], allxy["y"], gx, gy, inside)
        return Grid(gx, gy, z, cell, inside, boundary, cov), vals
    gx, gy, cell = make_axes(allxy["x"], allxy["y"], cell)
    z = interpolate(good["x"], good["y"], good["value"], gx, gy, method)
    if mask == "hull" and len(good) >= 3 and not _nearly_collinear(good["x"], good["y"]):
        # A two-cell margin keeps contours smooth up to the hull; maps clip to the exact hull.
        z = np.where(hull_mask(good["x"], good["y"], gx, gy, buffer or 2 * cell), z, np.nan)
    return Grid(gx, gy, z, cell), vals


def coverage(px, py, gx, gy, inside) -> float | None:
    """Share of the study-area cells that lie inside the boreholes' convex hull."""
    if len(px) < 3 or _nearly_collinear(px, py) or not inside.any():
        return None
    return float((hull_mask(px, py, gx, gy) & inside).sum() / inside.sum())


def _nearly_collinear(px, py) -> bool:
    """True when the points' hull is a thin sliver (hull area < 10 % of its bounding box)."""
    from scipy.spatial import ConvexHull

    pts = np.column_stack([px, py]).astype(float)
    try:
        area = ConvexHull(pts).volume
    except Exception:  # noqa: BLE001 - exactly collinear points
        return True
    span = np.ptp(pts, axis=0)
    return area < 0.1 * max(span[0] * span[1], 1e-9)


def write_ascii_grid(grid: Grid, path, nodata: float = -9999.0) -> Path:
    """ESRI ASCII grid (.asc): opens in QGIS, ArcGIS, Surfer, GRASS."""
    path = Path(path)
    x0, _, y0, _ = grid.extent
    data = np.where(grid.valid, grid.z, nodata)[::-1]  # north row first
    with open(path, "w") as f:
        f.write(f"ncols {len(grid.x)}\nnrows {len(grid.y)}\n")
        f.write(f"xllcorner {x0:.3f}\nyllcorner {y0:.3f}\ncellsize {grid.cell:g}\n")
        f.write(f"NODATA_value {nodata:g}\n")
        for row in data:
            f.write(" ".join(f"{v:.3f}" for v in row) + "\n")
    return path
