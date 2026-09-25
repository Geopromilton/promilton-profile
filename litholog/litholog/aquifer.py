"""Aquifer model: water table from observation wells, saturated volumes and storage.

Observation-well tables are read in the forms government data usually come in:

* long:  Well, X/Y (or Lat/Lon), Date, Depth to water (m bgl)
* wide:  Well, X/Y (or Lat/Lon), then one column per season/date
         (e.g. "Pre-monsoon 2023", "Post-monsoon 2023", "May-2024")

Latitude/longitude are converted to the project's metric coordinate system
(given, or the UTM zone of the wells). Ground elevation is taken from the table
if present, otherwise from the model's ground surface at the well.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .grid import Grid, interpolate
from .io import normalize

ALIASES = {
    "well_id": ["well_id", "well", "well_no", "station", "station_name", "site", "site_name", "name", "id",
                "borehole_id", "borehole", "location", "village"],
    "x": ["x", "easting", "utm_x", "east"],
    "y": ["y", "northing", "utm_y", "north"],
    "lat": ["lat", "latitude", "lat_dd", "y_lat"],
    "lon": ["lon", "long", "longitude", "lon_dd", "x_lon"],
    "date": ["date", "measured_on", "date_measured", "season", "period", "month"],
    "dtw": ["depth_to_water", "dtw", "water_level", "wl", "swl", "depth", "mbgl", "water_level_mbgl",
            "depth_to_water_level", "dtwl", "gw_level"],
    "ground": ["ground_elevation", "elevation", "rl", "gl", "msl", "altitude", "mp_elevation", "ground_level"],
}


@dataclass
class Wells:
    table: pd.DataFrame      # well_id, x, y, ground, then one column per reading date/season
    readings: list           # names of the reading columns (chronological as given)
    note: str = ""

    def values(self, reading=None) -> pd.DataFrame:
        """well_id, x, y, ground, dtw for one reading (default: the latest)."""
        reading = reading or self.readings[-1]
        if reading not in self.readings:
            raise KeyError(f"No reading '{reading}'. Available: {', '.join(map(str, self.readings))}")
        t = self.table[["well_id", "x", "y", "ground"]].copy()
        t["dtw"] = pd.to_numeric(self.table[reading], errors="coerce")
        return t.dropna(subset=["x", "y", "dtw"]).reset_index(drop=True)


def _find(cols, key):
    for alt in ALIASES[key]:
        for c in cols:
            if normalize(c) == alt:
                return c
    return None


def utm_epsg(lon: float, lat: float) -> int:
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def load_wells(path, crs: str | None = None) -> Wells:
    """Read observation wells (CSV/Excel, long or wide format)."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path, sep=None, engine="python")
    df = df.dropna(how="all")
    cols = list(df.columns)
    c_id, c_x, c_y = _find(cols, "well_id"), _find(cols, "x"), _find(cols, "y")
    c_lat, c_lon = _find(cols, "lat"), _find(cols, "lon")
    c_date, c_dtw, c_g = _find(cols, "date"), _find(cols, "dtw"), _find(cols, "ground")
    if c_id is None:
        df.insert(0, "_well", [f"W{i + 1}" for i in range(len(df))])
        c_id = "_well"
    note = ""
    out = pd.DataFrame({"well_id": df[c_id].astype(str).str.strip()})
    if c_x is not None and c_y is not None:
        out["x"] = pd.to_numeric(df[c_x], errors="coerce")
        out["y"] = pd.to_numeric(df[c_y], errors="coerce")
    elif c_lat is not None and c_lon is not None:
        from pyproj import Transformer

        lat = pd.to_numeric(df[c_lat], errors="coerce")
        lon = pd.to_numeric(df[c_lon], errors="coerce")
        target = crs or f"EPSG:{utm_epsg(float(lon.median()), float(lat.median()))}"
        t = Transformer.from_crs("EPSG:4326", target, always_xy=True)
        out["x"], out["y"] = t.transform(lon.to_numpy(), lat.to_numpy())
        note = f"latitude/longitude converted to {target}"
    else:
        raise ValueError(f"{path.name}: needs X/Y (easting/northing) or Latitude/Longitude columns")
    out["ground"] = pd.to_numeric(df[c_g], errors="coerce") if c_g is not None else np.nan

    used = {c for c in (c_id, c_x, c_y, c_lat, c_lon, c_g, c_date, c_dtw) if c is not None}
    if c_dtw is not None and c_date is not None:  # long format: pivot readings into columns
        long = out.copy()
        long["date"] = df[c_date].astype(str).str.strip()
        long["dtw"] = pd.to_numeric(df[c_dtw], errors="coerce")
        order = list(dict.fromkeys(long["date"]))
        wide = long.pivot_table(index="well_id", columns="date", values="dtw", aggfunc="mean")
        base = long.groupby("well_id")[["x", "y", "ground"]].first()
        table = base.join(wide[order]).reset_index()
        readings = order
    elif c_dtw is not None:
        table = out.copy()
        table["latest"] = pd.to_numeric(df[c_dtw], errors="coerce")
        readings = ["latest"]
    else:  # wide format: every remaining mostly-numeric column is a reading
        readings = []
        table = out.copy()
        for c in cols:
            if c in used:
                continue
            v = pd.to_numeric(df[c], errors="coerce")
            if v.notna().mean() >= 0.3:
                name = str(c).strip()
                table[name] = v
                readings.append(name)
        if not readings:
            raise ValueError(f"{path.name}: no depth-to-water column found")
    return Wells(table.reset_index(drop=True), readings, note)


def wells_from_project(project) -> Wells | None:
    """Latest water level at each borehole (WaterLevels sheet) as Wells."""
    rows = []
    for bh in project:
        wl = bh.water_levels.dropna(subset=["depth"])
        if len(wl) and pd.notna(bh.x):
            rows.append({"well_id": bh.id, "x": bh.x, "y": bh.y,
                         "ground": bh.elevation if bh.has_elevation else np.nan, "latest": wl.iloc[-1]["depth"]})
    if not rows:
        return None
    return Wells(pd.DataFrame(rows), ["latest"], "borehole water levels")


def _sample(grid_x, grid_y, z, px, py):
    """Nearest-cell values of a (ny, nx) grid at points."""
    i = np.clip(np.searchsorted(grid_x, px) - 1, 0, len(grid_x) - 1)
    j = np.clip(np.searchsorted(grid_y, py) - 1, 0, len(grid_y) - 1)
    i2 = np.clip(i + 1, 0, len(grid_x) - 1)
    j2 = np.clip(j + 1, 0, len(grid_y) - 1)
    i = np.where(np.abs(grid_x[i2] - px) < np.abs(grid_x[i] - px), i2, i)
    j = np.where(np.abs(grid_y[j2] - py) < np.abs(grid_y[j] - py), j2, j)
    return z[j, i]


@dataclass
class WaterTable:
    grid: Grid                 # water-table elevation on the model's XY grid
    dtw: Grid                  # depth to water
    wells: pd.DataFrame        # well_id, x, y, ground, dtw, wt (elevation)
    reading: str


def water_table(model, wells: Wells, reading=None, method: str = "idw") -> WaterTable:
    """Water-table surface on the block model's grid (never above ground)."""
    w = wells.values(reading)
    g_at = _sample(model.x, model.y, model.ground, w["x"].to_numpy(), w["y"].to_numpy())
    w["ground"] = w["ground"].fillna(pd.Series(g_at, index=w.index))
    w["wt"] = w["ground"] - w["dtw"]
    w = w.dropna(subset=["wt"])
    if len(w) < 2:
        raise ValueError("Fewer than two wells have a usable water level")
    dtw = interpolate(w["x"], w["y"], w["dtw"], model.x, model.y, method)
    wt = model.ground - np.maximum(dtw, 0)  # depth-to-water follows the ground surface
    mask = model.inside
    wt = np.where(mask, wt, np.nan)
    return WaterTable(Grid(model.x, model.y, wt, model.cell, mask, model.boundary, model.coverage),
                      Grid(model.x, model.y, np.where(mask, dtw, np.nan), model.cell, mask, model.boundary,
                           model.coverage),
                      w, reading or wells.readings[-1])


def saturated_volumes(model, wt: WaterTable, sy: dict | None = None) -> pd.DataFrame:
    """Total and saturated (below water table) volume of each unit, with storage."""
    sy = sy or {}
    filled = model.lith >= 0
    below = model.z[:, None, None] < wt.grid.z[None]
    below &= np.isfinite(wt.grid.z)[None]
    v = model.voxel_volume
    rows = []
    for k, code in enumerate(model.codes):
        p = model.prob[..., k] if model.prob is not None else (model.lith == k).astype(float)
        total = float(p[filled].sum()) * v
        sat = float(p[filled & below].sum()) * v
        row = {"code": code, "volume_mcm": total / 1e6, "saturated_mcm": sat / 1e6,
               "saturated_pct": 100 * sat / total if total else 0.0}
        if code in sy:
            row["specific_yield"] = sy[code]
            row["storage_mcm"] = sat * sy[code] / 1e6
        rows.append(row)
    return pd.DataFrame(rows)


def saturated_thickness(model, wt: WaterTable, code: str) -> Grid:
    """Saturated thickness (m) of one unit in each column (vote-weighted)."""
    k = model.codes.index(code)
    p = model.prob[..., k] if model.prob is not None else (model.lith == k).astype(float)
    below = (model.z[:, None, None] < wt.grid.z[None]) & (model.lith >= 0)
    th = (p * below).sum(0) * model.dz
    return Grid(model.x, model.y, np.where(model.inside, th, np.nan), model.cell, model.inside,
                model.boundary, model.coverage)


def reading_label(name: str) -> str:
    return re.sub(r"\s+", " ", str(name)).strip()
