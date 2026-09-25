"""Build the LithoLog tutorial dataset (litholog/data/tutorial/).

SYNTHETIC data for learning the software. It imitates a hard-rock (gneiss) terrain with a
weathered zone and two water-bearing fracture zones; it is not a real site.

Files:
  tutorial_boreholes.xlsx   24 boreholes: lithology, well construction, water level, resistivity log,
                            fractures, legend
  tutorial_water_levels.csv 30 observation wells, pre- and post-monsoon depth to water
  tutorial_chemistry.csv    18 groundwater samples (major ions, EC, pH)
  tutorial_boundary.geojson study-area polygon (latitude/longitude)
  tutorial_constraints.csv  an area where the lower fracture zone is absent (interpretation)
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

OUT = Path(__file__).resolve().parents[1] / "litholog" / "data" / "tutorial"
rng = np.random.default_rng(2026)
E0, N0 = 700000.0, 1350000.0          # UTM zone 43N (EPSG:32643), synthetic site


def ground(x, y):
    """Gentle slope to the east with a low hill in the south-west."""
    return 540 - (x - E0) / 120 + 18 * np.exp(-(((x - E0 - 900) / 900) ** 2 + ((y - N0 - 600) / 800) ** 2))


def profile(x, y):
    """Depths (m bgl) of the contacts at (x, y): smooth in space plus a little noise."""
    u, v = (x - E0) / 4500, (y - N0) / 3200
    soil = 1.2 + 1.5 * u + rng.normal(0, 0.3)
    weath = 12 + 9 * (1 - u) * (1 - v) + 4 * np.sin(3 * u) + rng.normal(0, 1.2)
    fz1 = weath + 10 + 8 * v + rng.normal(0, 1.5)
    fz1_t = 3.0 + 2.0 * u + rng.normal(0, 0.5)
    fz2 = 58 + 10 * u - 6 * v + rng.normal(0, 2.0)
    fz2_t = max(0.0, 4.0 - 7.0 * max(0.0, u + v - 1.05)) + rng.normal(0, 0.4)   # pinches out to the NE
    return soil, weath, fz1, fz1_t, fz2, max(fz2_t, 0.0)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    xs, ys = np.meshgrid(np.linspace(E0 + 300, E0 + 4200, 6), np.linspace(N0 + 300, N0 + 2900, 4))
    xs = xs.ravel() + rng.normal(0, 180, xs.size)
    ys = ys.ravel() + rng.normal(0, 180, ys.size)
    holes, lith, cons, wl, logs, frac = [], [], [], [], [], []
    for k, (x, y) in enumerate(zip(xs, ys), start=1):
        bid = f"TB-{k:02d}"
        g = round(float(ground(x, y)), 1)
        soil, weath, f1, t1, f2, t2 = profile(x, y)
        td = float(np.clip(round(95 + 15 * rng.random()), 90, 120))
        holes.append((bid, round(x, 1), round(y, 1), g, td, "Tutorial site", f"2025-{1 + k % 5:02d}-{5 + k:02d}",
                      "DTH"))
        rows = [(0, soil, "TOP", "Red sandy soil"),
                (soil, weath, "WGN", "Weathered gneiss, sandy clay with relict foliation"),
                (weath, f1, "GN", "Hard biotite gneiss"),
                (f1, f1 + t1, "FGN", "Fractured gneiss, water struck (upper fracture zone)"),
                (f1 + t1, f2, "GN", "Massive gneiss")]
        if t2 > 0.3:
            rows += [(f2, f2 + t2, "FGN", "Fractured gneiss, iron-stained joints (lower fracture zone)"),
                     (f2 + t2, td, "GN", "Massive gneiss")]
        else:
            rows += [(f2, td, "GN", "Massive gneiss")]
        rows = [(round(a, 1), round(b, 1), c, d) for a, b, c, d in rows]
        rows[-1] = (rows[-1][0], td, rows[-1][2], rows[-1][3])
        lith += [(bid, a, b, c, d) for a, b, c, d in rows if b > a]
        cons += [(bid, 0, round(weath + 1, 1), "casing", 180, "PVC"), (bid, round(weath + 1, 1), td, "open hole", 165, "")]
        wl.append((bid, "2025-05-15", round(float(np.clip(weath * 0.7 + rng.normal(0, 1.5), 3, 30)), 2)))
        for d in np.arange(1, td, 1.0):
            if d < soil:
                r = 60
            elif d < weath:
                r = 90
            elif (f1 <= d < f1 + t1) or (t2 > 0.3 and f2 <= d < f2 + t2):
                r = 250
            else:
                r = 3000
            logs.append((bid, float(d), "Resistivity", round(float(r * np.exp(rng.normal(0, 0.25))), 1), "ohm.m"))
        for top, th, yl in ((f1, t1, 0.8), (f2, t2, 1.5)):
            for _ in range(int(max(th, 0) * 1.5)):
                dd = 110 + rng.normal(0, 15) if rng.random() < 0.6 else 20 + rng.normal(0, 12)
                frac.append((bid, round(float(top + rng.random() * max(th, 0.5)), 1), round(float(rng.uniform(50, 85)), 0),
                             round(float(dd % 360), 0), round(float(rng.uniform(0.5, 4)), 1),
                             round(float(yl * rng.uniform(0.3, 1.2)), 2) if rng.random() < 0.5 else None, ""))
    legend = pd.DataFrame([("TOP", "Top soil", "#A67C52", "roots+fine_dots", "Soil & cover"),
                           ("WGN", "Weathered gneiss", "#E8C9A6", "waves+diag", "Weathering profile"),
                           ("GN", "Gneiss", "#D9CFEA", "waves", "Crystalline"),
                           ("FGN", "Fractured gneiss (water-bearing)", "#7FB7E6", "waves+fractures", "Aquifer")],
                          columns=["Code", "Name", "Color", "Pattern", "Group"])
    about = pd.DataFrame({"Note": ["SYNTHETIC tutorial data for learning LithoLog. Not a real site. "
                                   "Coordinates: WGS 84 / UTM zone 43N (EPSG:32643)."]})
    with pd.ExcelWriter(OUT / "tutorial_boreholes.xlsx") as xw:
        about.to_excel(xw, sheet_name="About", index=False)
        pd.DataFrame(holes, columns=["Borehole ID", "Easting (m)", "Northing (m)", "Elevation (m amsl)",
                                     "Total depth (m)", "Location", "Date", "Drilling method"]).to_excel(xw, sheet_name="Boreholes", index=False)
        pd.DataFrame(lith, columns=["Borehole ID", "From (m)", "To (m)", "Code", "Description"]).to_excel(xw, sheet_name="Lithology", index=False)
        pd.DataFrame(cons, columns=["Borehole ID", "From (m)", "To (m)", "Element", "Diameter (mm)",
                                    "Material"]).to_excel(xw, sheet_name="Construction", index=False)
        pd.DataFrame(wl, columns=["Borehole ID", "Date", "Depth to water (m bgl)"]).to_excel(xw, sheet_name="WaterLevels", index=False)
        pd.DataFrame(logs, columns=["Borehole ID", "Depth (m)", "Parameter", "Value", "Unit"]).to_excel(xw, sheet_name="Downhole", index=False)
        pd.DataFrame(frac, columns=["Borehole ID", "Depth (m)", "Dip (deg)", "Dip direction (deg)",
                                    "Aperture (mm)", "Yield (lps)", "Remarks"]).to_excel(xw, sheet_name="Fractures", index=False)
        legend.to_excel(xw, sheet_name="Legend", index=False)

    # observation wells (village-style names, pre / post monsoon)
    names = ["Arasur", "Belur", "Chettipalayam", "Devanur", "Elanthur", "Gudalur", "Hosur", "Idayapatti",
             "Jagir", "Kalipatti", "Laxmipuram", "Melur", "Nallur", "Odaipatti", "Palayam", "Ramapuram",
             "Sevur", "Thenur", "Udayapatti", "Vadakkur", "Alampatti", "Kovilur", "Mettur", "Pudur",
             "Sankarapuram", "Tiruvur", "Valayapatti", "Ayyampatti", "Karadipatti", "Siruvalur"]
    wx = rng.uniform(E0 + 150, E0 + 4350, len(names))
    wy = rng.uniform(N0 + 150, N0 + 3050, len(names))
    pre, post = [], []
    for x, y in zip(wx, wy):
        _, weath, *_ = profile(x, y)
        p = float(np.clip(0.8 * weath + (ground(x, y) - 520) * 0.15 + rng.normal(0, 1.5), 4, 30))
        pre.append(round(p, 2))
        post.append(round(float(np.clip(p - rng.uniform(4, 11), 0.8, None)), 2))
    pd.DataFrame({"Well": names, "Easting": wx.round(1), "Northing": wy.round(1),
                  "Elevation": [round(float(ground(x, y)), 1) for x, y in zip(wx, wy)],
                  "Pre-monsoon": pre, "Post-monsoon": post}).to_csv(OUT / "tutorial_water_levels.csv", index=False)

    # hydrochemistry: fresh Ca-HCO3 water up-gradient, more mineralised Na-Cl water down-gradient
    chem = []
    for i in range(18):
        s = i / 17
        ca, mg = 40 + 60 * s + rng.normal(0, 8), 18 + 30 * s + rng.normal(0, 4)
        na, k = 30 + 220 * s ** 1.5 + rng.normal(0, 10), 2 + 6 * s
        hco3, cl = 220 + 120 * s + rng.normal(0, 15), 35 + 330 * s ** 1.5 + rng.normal(0, 12)
        so4 = 20 + 90 * s + rng.normal(0, 6)
        meq = ca / 20.04 + mg / 12.15 + na / 22.99 + k / 39.1
        chem.append((f"TW-{i + 1:02d}", "Up-gradient" if s < 0.5 else "Down-gradient", *(round(v, 1) for v in
                     (ca, mg, na, k, hco3, cl, so4)), round(meq * 100, 0), round(7.1 + 0.6 * s, 2)))
    pd.DataFrame(chem, columns=["Sample", "Group", "Ca", "Mg", "Na", "K", "HCO3", "Cl", "SO4", "EC", "pH"]).to_csv(
        OUT / "tutorial_chemistry.csv", index=False)

    # study-area boundary (lat/lon) and a constraint (UTM)
    t = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
    ring = [(E0 - 100, N0 - 50), (E0 + 2400, N0 - 200), (E0 + 4700, N0 + 100), (E0 + 4600, N0 + 1800),
            (E0 + 4300, N0 + 3300), (E0 + 1800, N0 + 3450), (E0 - 200, N0 + 3100), (E0 - 300, N0 + 1500)]
    ll = [list(t.transform(x, y)) for x, y in ring]
    ll.append(ll[0])
    (OUT / "tutorial_boundary.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "Tutorial study area"},
                                                    "geometry": {"type": "Polygon", "coordinates": [ll]}}]}))
    pd.DataFrame([("code FGN", "absent", E0 + 3700, N0 + 2500, "", "A"), ("code FGN", "absent", E0 + 4500, N0 + 2500, "", "A"),
                  ("code FGN", "absent", E0 + 4500, N0 + 3300, "", "A"), ("code FGN", "absent", E0 + 3700, N0 + 3300, "", "A")],
                 columns=["Horizon", "Type", "X", "Y", "Value", "Feature"]).to_csv(OUT / "tutorial_constraints.csv",
                                                                                   index=False)
    print(f"Tutorial data written to {OUT}")


if __name__ == "__main__":
    main()
