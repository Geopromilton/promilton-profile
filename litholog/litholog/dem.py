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
    name = path.name.lower()
    if name.endswith((".hgt", ".hgt.gz", ".hgt.zip")):
        return _load_hgt(path)
    if path.suffix.lower() in (".asc", ".txt"):
        return _load_ascii(path)
    if path.suffix.lower() in (".tif", ".tiff"):
        return _load_geotiff(path)
    raise ValueError(f"{path.name}: DEM must be a GeoTIFF (.tif), SRTM tile (.hgt, .hgt.gz, .zip) or ESRI ASCII "
                     "grid (.asc)")


def _load_hgt(path: Path) -> DEM:
    """SRTM .hgt tile (1 or 3 arc-second, big-endian int16, named after its SW corner, e.g. N08E077)."""
    import gzip
    import re
    import zipfile

    name = path.name.lower()
    if name.endswith(".gz"):
        data = gzip.open(path).read()
    elif name.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            data = z.read(next(n for n in z.namelist() if n.lower().endswith(".hgt")))
    else:
        data = path.read_bytes()
    raw = np.frombuffer(data, ">i2")
    n = int(round(np.sqrt(raw.size)))
    if n * n != raw.size:
        raise ValueError(f"{path.name}: not an SRTM .hgt tile")
    m = re.search(r"([ns])(\d{2})([ew])(\d{3})", name)
    if not m:
        raise ValueError(f"{path.name}: SRTM tiles must keep their name (e.g. N08E077.hgt)")
    lat = int(m.group(2)) * (1 if m.group(1) == "n" else -1)
    lon = int(m.group(4)) * (1 if m.group(3) == "e" else -1)
    z = raw.reshape(n, n).astype(float)
    z[z <= -32768] = np.nan
    from pyproj import CRS

    step = 1.0 / (n - 1)
    return DEM(z, float(lon), float(lat + 1), step, step, CRS.from_epsg(4326), path.name.split(".")[0])


COPERNICUS = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
              "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif")


def download_copernicus(lon0, lon1, lat0, lat1, folder, progress=None) -> Path:
    """Download the Copernicus GLO-30 DEM (30 m, free; ESA / AWS open data) for a lon/lat box and save it as
    one GeoTIFF clipped to the box. Returns the file path."""
    import math
    import urllib.request

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    tiles = []
    for la in range(math.floor(lat0), math.floor(lat1) + 1):
        for lo in range(math.floor(lon0), math.floor(lon1) + 1):
            url = COPERNICUS.format(ns="N" if la >= 0 else "S", lat=abs(la), ew="E" if lo >= 0 else "W", lon=abs(lo))
            dst = folder / url.rsplit("/", 1)[1]
            if not dst.exists():
                if progress:
                    progress(f"Downloading {dst.name} …")
                try:
                    urllib.request.urlretrieve(url, dst)
                except Exception as e:  # noqa: BLE001 - sea-only tiles do not exist
                    if progress:
                        progress(f"  tile {dst.name} not available ({e})")
                    continue
            tiles.append(load_dem(dst))
    if not tiles:
        raise RuntimeError("No DEM tiles could be downloaded (check the internet connection)")
    step = tiles[0].dx
    xs = np.arange(lon0, lon1 + step, step)
    ys = np.arange(lat1, lat0 - step, -step)
    X, Y = np.meshgrid(xs, ys)
    z = np.full(X.shape, np.nan)
    for t in tiles:
        v = sample(t, X.ravel(), Y.ravel()).reshape(X.shape)
        z = np.where(np.isfinite(v), v, z)
    out = folder / f"copernicus_dem_{lat0:.2f}_{lon0:.2f}.tif"
    write_geotiff(out, z, xs[0], ys[0], step, step, 4326)
    return out


def write_geotiff(path, z, x0, y0, dx, dy, epsg: int):
    """Minimal GeoTIFF writer (float32, pixel centres x0/y0 of the first column/row, north up)."""
    import tifffile

    geokeys = (1, 1, 0, 4, 1024, 0, 1, 2 if epsg == 4326 else 1, 1025, 0, 1, 1,
               2048 if epsg == 4326 else 3072, 0, 1, epsg, 4096, 0, 1, 5773)
    tifffile.imwrite(path, np.where(np.isfinite(z), z, -9999).astype(np.float32), compression="zlib",
                     extratags=[(33550, "d", 3, (dx, dy, 0.0)),
                                (33922, "d", 6, (0, 0, 0, x0 - dx / 2, y0 + dy / 2, 0)),
                                (34735, "H", len(geokeys), geokeys), (42113, "s", 0, "-9999")])
    return path


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
    if crs is None and dem.crs is not None and dem.crs.is_geographic and np.nanmax(np.abs(xs), initial=0) > 360:
        crs = MODEL_CRS["crs"] or _utm_of(dem)   # projected points on a lat/lon DEM: UTM zone of the DEM
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


def _utm_of(dem: DEM) -> str:
    from .aquifer import utm_epsg

    lon = dem.x0 + dem.z.shape[1] * dem.dx / 2
    lat = dem.y0 - dem.z.shape[0] * dem.dy / 2
    return f"EPSG:{utm_epsg(lon, lat)}"


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
