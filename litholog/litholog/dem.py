"""Digital elevation models (GeoTIFF, ESRI ASCII grid) and sampling onto model grids.

A DEM in any coordinate system (e.g. SRTM in latitude/longitude) is sampled at
the model's grid points by transforming them into the DEM's system and
interpolating bilinearly, so no separate reprojection step is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class DEM:
    z: np.ndarray        # (rows, cols), row 0 = north; NaN = no data
    x0: float            # x of the centre of column 0
    y0: float            # y of the centre of row 0 (north edge row)
    dx: float
    dy: float            # positive; rows go south
    crs: object = None   # pyproj CRS or None (= same as the boreholes)
    name: str = "DEM"

    @property
    def bounds(self):
        rows, cols = self.z.shape
        return (self.x0 - self.dx / 2, self.x0 + (cols - 0.5) * self.dx,
                self.y0 - (rows - 0.5) * self.dy, self.y0 + self.dy / 2)


def load_dem(path) -> DEM:
    path = Path(path)
    if path.suffix.lower() in (".asc", ".txt"):
        return _load_ascii(path)
    if path.suffix.lower() in (".tif", ".tiff"):
        return _load_geotiff(path)
    raise ValueError(f"{path.name}: DEM must be a GeoTIFF (.tif) or ESRI ASCII grid (.asc)")


def _load_ascii(path: Path) -> DEM:
    head = {}
    with open(path) as f:
        for _ in range(6):
            pos = f.tell()
            line = f.readline().split()
            if len(line) == 2 and line[0].replace("_", "").isalpha():
                head[line[0].lower()] = float(line[1])
            else:
                f.seek(pos)
                break
        z = np.loadtxt(f, dtype=float)
    nd = head.get("nodata_value", -9999)
    z[z == nd] = np.nan
    cs = head["cellsize"]
    x0 = head.get("xllcenter", head.get("xllcorner", 0) + cs / 2)
    yll = head.get("yllcenter", head.get("yllcorner", 0) + cs / 2)
    y0 = yll + (z.shape[0] - 1) * cs
    crs = None
    prj = path.with_suffix(".prj")
    if prj.exists():
        from pyproj import CRS

        crs = CRS.from_wkt(prj.read_text())
    return DEM(z, x0, y0, cs, cs, crs, path.stem)


def _load_geotiff(path: Path) -> DEM:
    import tifffile
    from pyproj import CRS

    with tifffile.TiffFile(path) as tf:
        page = tf.pages[0]
        z = page.asarray().astype(float)
        if z.ndim == 3:
            z = z[..., 0]
        tags = {t.code: t.value for t in page.tags.values()}
    scale = tags.get(33550)
    tie = tags.get(33922)
    if scale is None or tie is None:
        raise ValueError(f"{path.name}: not a georeferenced GeoTIFF (no pixel scale / tie point)")
    sx, sy = float(scale[0]), float(scale[1])
    i, j, _, X, Y, _ = (float(v) for v in tie[:6])
    geokeys = tags.get(34735, ())
    keys = {geokeys[k]: geokeys[k + 3] for k in range(4, len(geokeys) - 3, 4)} if len(geokeys) >= 4 else {}
    pixel_is_point = keys.get(1025) == 2
    # centre of pixel (0, 0)
    x0 = X - i * sx + (0 if pixel_is_point else sx / 2)
    y0 = Y + j * sy - (0 if pixel_is_point else sy / 2)
    nod = tags.get(42113)
    if nod is not None:
        try:
            z[z == float(str(nod).strip("\x00 "))] = np.nan
        except ValueError:
            pass
    z[z < -1e4] = np.nan  # common SRTM/ASTER voids
    crs = None
    epsg = keys.get(3072) or keys.get(2048)
    if epsg and epsg != 32767:
        crs = CRS.from_epsg(int(epsg))
    return DEM(z, x0, y0, sx, sy, crs, path.stem)


def sample(dem: DEM, xs, ys, crs=None) -> np.ndarray:
    """Bilinear DEM values at points (in ``crs``; default: the DEM's own system)."""
    xs = np.asarray(xs, float)
    ys = np.asarray(ys, float)
    if dem.crs is not None and crs is not None:
        from pyproj import CRS, Transformer

        t = Transformer.from_crs(CRS.from_user_input(crs), dem.crs, always_xy=True)
        xs, ys = t.transform(xs, ys)
    c = (xs - dem.x0) / dem.dx
    r = (dem.y0 - ys) / dem.dy
    rows, cols = dem.z.shape
    c0 = np.floor(c).astype(int)
    r0 = np.floor(r).astype(int)
    ok = (c0 >= 0) & (r0 >= 0) & (c0 < cols - 1) & (r0 < rows - 1)
    out = np.full(xs.shape, np.nan)
    c0, r0, fc, fr = c0[ok], r0[ok], c[ok] - c0[ok], r[ok] - r0[ok]
    z = dem.z
    out[ok] = (z[r0, c0] * (1 - fc) * (1 - fr) + z[r0, c0 + 1] * fc * (1 - fr)
               + z[r0 + 1, c0] * (1 - fc) * fr + z[r0 + 1, c0 + 1] * fc * fr)
    return out


# The coordinate system of the model grid (set by the caller when it is known).
MODEL_CRS = {"crs": None}


def sample_on_grid(dem: DEM, gx, gy, crs=None) -> np.ndarray:
    X, Y = np.meshgrid(gx, gy)
    crs = crs or MODEL_CRS["crs"]
    if dem.crs is not None and crs is None and dem.crs.is_geographic:
        # model grid in metres but DEM in degrees: assume the UTM zone of the DEM centre
        from .aquifer import utm_epsg

        lon = dem.x0 + dem.z.shape[1] * dem.dx / 2
        lat = dem.y0 - dem.z.shape[0] * dem.dy / 2
        crs = f"EPSG:{utm_epsg(lon, lat)}"
    return sample(dem, X.ravel(), Y.ravel(), crs).reshape(X.shape)


def rectify_collars(project, dem: DEM, crs=None, replace: bool = True) -> "pd.DataFrame":
    """Compare (and optionally replace) collar elevations with the DEM."""
    import pandas as pd

    b = project.boreholes
    ok = b["x"].notna() & b["y"].notna()
    z = np.full(len(b), np.nan)
    z[ok.to_numpy()] = sample(dem, b.loc[ok, "x"], b.loc[ok, "y"], crs or MODEL_CRS["crs"])
    rep = pd.DataFrame({"borehole_id": b["borehole_id"], "collar": b["elevation"], "dem": z,
                        "difference": b["elevation"] - z})
    if replace:
        project.boreholes["elevation"] = np.where(np.isfinite(z), z, b["elevation"])
    return rep
