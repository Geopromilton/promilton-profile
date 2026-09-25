"""Build examples/sample_project.xlsx.

SYNTHETIC data for demonstration only. The logs imitate typical hard-rock
(granite-gneiss with a schist belt) and river-alluvium profiles; they are not
real boreholes.
"""

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
rng = np.random.default_rng(7)

boreholes = pd.DataFrame([
    # id, easting, northing, elevation, td, location, date, method, diameter
    ("BW-01", 651200, 1688450, 486.2, 90, "Granite upland", "2025-02-11", "DTH", 165),
    ("BW-02", 652150, 1688600, 481.7, 80, "Granite upland", "2025-02-14", "DTH", 165),
    ("BW-03", 651700, 1687800, 476.9, 100, "Valley fill", "2025-02-18", "DTH", 165),
    ("BW-04", 652650, 1687550, 472.3, 75, "Gneiss / dyke", "2025-02-21", "DTH", 165),
    ("BW-05", 651250, 1687050, 468.8, 120, "Schist belt margin", "2025-02-25", "DTH", 165),
    ("TW-06", 652450, 1686750, 459.4, 30, "River alluvium", "2025-03-03", "Rotary", 300),
], columns=["Borehole ID", "Easting (m)", "Northing (m)", "Elevation (m amsl)", "Total depth (m)",
            "Location", "Date", "Drilling method", "Diameter"])

L = [
    ("BW-01", 0, 1.2, "RSOIL", "Red sandy loam with roots"),
    ("BW-01", 1.2, 4.5, "LAT", "Ferruginous laterite, pisolitic"),
    ("BW-01", 4.5, 13.0, "WGRA", "Highly weathered pink granite, grus"),
    ("BW-01", 13.0, 19.5, "FGRA", "Fractured granite; water struck at 17 m (~0.8 lps)"),
    ("BW-01", 19.5, 52.0, "GRA", "Massive pink-grey granite"),
    ("BW-01", 52.0, 55.0, "FGRA", "Fracture zone, iron-stained joints; yield increased (~2.5 lps)"),
    ("BW-01", 55.0, 90.0, "GRA", "Massive granite"),

    ("BW-02", 0, 1.0, "RSOIL", "Red soil"),
    ("BW-02", 1.0, 3.0, "KANK", "Kankar nodules in sandy matrix"),
    ("BW-02", 3.0, 15.0, "WGRA", "Weathered granite, clay-rich near top"),
    ("BW-02", 15.0, 21.0, "FGRA", "Fractured granite, water struck 18 m"),
    ("BW-02", 21.0, 80.0, "GRA", "Massive granite, dry"),

    ("BW-03", 0, 2.5, "BCS", "Black cotton soil, sticky when wet"),
    ("BW-03", 2.5, 6.0, "SCLAY", "Sandy clay, calcareous"),
    ("BW-03", 6.0, 18.0, "SAPR", "Saprolite, weathered gneiss with relict foliation"),
    ("BW-03", 18.0, 26.0, "FGN", "Fractured gneiss, first water 20 m"),
    ("BW-03", 26.0, 64.0, "GN", "Hard banded gneiss"),
    ("BW-03", 64.0, 68.0, "FGN", "Fractured gneiss, good yield (~3 lps)"),
    ("BW-03", 68.0, 100.0, "GN", "Hard gneiss"),

    ("BW-04", 0, 1.5, "RSOIL", "Red soil"),
    ("BW-04", 1.5, 11.0, "WGN", "Weathered gneiss"),
    ("BW-04", 11.0, 16.0, "FGN", "Fractured gneiss"),
    ("BW-04", 16.0, 31.0, "GN", "Gneiss"),
    ("BW-04", 31.0, 38.0, "DOL", "Dolerite dyke, dark, fine grained; contact fractured"),
    ("BW-04", 38.0, 75.0, "GN", "Gneiss"),

    ("BW-05", 0, 1.0, "RSOIL", "Red soil"),
    ("BW-05", 1.0, 5.0, "LAT", "Laterite"),
    ("BW-05", 5.0, 9.0, "LITHO", "Lithomarge, mottled kaolinitic clay"),
    ("BW-05", 9.0, 22.0, "SCH", "Weathered chlorite schist"),
    ("BW-05", 22.0, 40.0, "PHY", "Phyllite with quartz veins"),
    ("BW-05", 40.0, 58.0, "BIF", "Banded iron formation (magnetite-quartzite bands)"),
    ("BW-05", 58.0, 70.0, "QTZ", "Quartzite, fractured at 62-66 m"),
    ("BW-05", 70.0, 120.0, "SCH", "Hard schist"),

    ("TW-06", 0, 1.5, "SILT", "Silty overbank deposit"),
    ("TW-06", 1.5, 6.0, "CLAY", "Grey clay"),
    ("TW-06", 6.0, 14.0, "SAND", "Medium to coarse sand, well sorted"),
    ("TW-06", 14.0, 19.0, "GRAV", "Sandy gravel, rounded pebbles"),
    ("TW-06", 19.0, 23.0, "SAPR", "Weathered bedrock"),
    ("TW-06", 23.0, 30.0, "GN", "Gneiss bedrock"),
]
lithology = pd.DataFrame(L, columns=["Borehole ID", "From (m)", "To (m)", "Code", "Description"])

C = []
for bid, casing_to, td in [("BW-01", 20, 90), ("BW-02", 22, 80), ("BW-03", 27, 100),
                           ("BW-04", 17, 75), ("BW-05", 23, 120)]:
    C += [(bid, 0, 3, "grout", None, "Cement seal"),
          (bid, 0, casing_to, "casing", 165, "PVC 6 inch"),
          (bid, casing_to, td, "open hole", 150, "")]
C += [("TW-06", 0, 4, "grout", None, "Bentonite-cement"),
      ("TW-06", 4, 6, "bentonite", None, "Bentonite plug"),
      ("TW-06", 6, 20, "gravel pack", None, "2-4 mm pea gravel"),
      ("TW-06", 0, 7, "casing", 200, "PVC 8 inch"),
      ("TW-06", 7, 18, "screen", 200, "Slotted PVC, 1 mm"),
      ("TW-06", 18, 20, "casing", 200, "Sump")]
construction = pd.DataFrame(C, columns=["Borehole ID", "From (m)", "To (m)", "Element",
                                        "Diameter (mm)", "Material"])

wl = pd.DataFrame([
    ("BW-01", "2025-02-12", 14.6), ("BW-01", "2025-05-20", 18.9), ("BW-01", "2025-10-15", 9.8),
    ("BW-02", "2025-02-15", 16.2), ("BW-03", "2025-02-19", 11.4), ("BW-03", "2025-10-15", 6.9),
    ("BW-04", "2025-02-22", 12.8), ("BW-05", "2025-02-26", 19.5), ("TW-06", "2025-03-04", 4.1),
], columns=["Borehole ID", "Date", "Depth to water (m bgl)"])

# Simple synthetic downhole resistivity: low in weathered/fractured zones, high in massive rock.
RES = {"RSOIL": 60, "LAT": 150, "WGRA": 90, "FGRA": 180, "GRA": 1400, "KANK": 120,
       "BCS": 12, "SCLAY": 25, "SAPR": 70, "FGN": 200, "GN": 1100, "WGN": 80, "DOL": 2200,
       "LITHO": 30, "SCH": 160, "PHY": 220, "BIF": 45, "QTZ": 1600, "SILT": 30, "CLAY": 15,
       "SAND": 110, "GRAV": 200}
rows = []
for bid in ["BW-01", "BW-03", "BW-05", "TW-06"]:
    sub = lithology[lithology["Borehole ID"] == bid]
    td = sub["To (m)"].max()
    for d in np.arange(1.0, td, 1.0):
        code = sub[(sub["From (m)"] <= d) & (sub["To (m)"] > d)]["Code"].iloc[0]
        rows.append((bid, d, "Resistivity", round(RES[code] * rng.lognormal(0, 0.12), 1), "ohm-m"))
# Cumulative airlift yield during drilling for two wells.
for bid, steps in {"BW-01": [(17, 0.8), (53, 3.3)], "BW-03": [(20, 0.6), (65, 3.6)]}.items():
    td = boreholes.loc[boreholes["Borehole ID"] == bid, "Total depth (m)"].iloc[0]
    for d in np.arange(3, td + 0.1, 3.0):
        q = sum(v - (steps[i - 1][1] if i else 0) for i, (s, v) in enumerate(steps) if d >= s)
        rows.append((bid, d, "Yield", round(q, 2), "lps"))
downhole = pd.DataFrame(rows, columns=["Borehole ID", "Depth (m)", "Parameter", "Value", "Unit"])

# Fractures: steep NE-SW joint set, gentle sheet joints, water strikes in fractured zones.
fr = []
for bid in ["BW-01", "BW-02", "BW-03", "BW-04", "BW-05"]:
    sub = lithology[lithology["Borehole ID"] == bid]
    for _, r in sub.iterrows():
        if r["Code"] in ("FGRA", "FGN", "DOL", "QTZ", "WGRA", "WGN"):
            n = max(2, int((r["To (m)"] - r["From (m)"]) / 1.5))
            for d in np.linspace(r["From (m)"] + 0.3, r["To (m)"] - 0.3, n):
                if rng.random() < 0.6:
                    dip, ddir = rng.normal(72, 8), rng.normal(135, 12)
                else:
                    dip, ddir = abs(rng.normal(12, 6)), rng.normal(200, 40)
                strike = r["Code"].startswith("F") and rng.random() < 0.25
                fr.append((bid, round(d, 1), round(min(dip, 89), 0), round(ddir % 360, 0),
                           round(rng.uniform(0.5, 5), 1), round(rng.uniform(0.3, 2.5), 1) if strike else None,
                           "Water strike" if strike else "Joint"))
fractures = pd.DataFrame(fr, columns=["Borehole ID", "Depth (m)", "Dip (deg)", "Dip direction (deg)",
                                      "Aperture (mm)", "Yield (lps)", "Remarks"])

out = HERE / "sample_project.xlsx"
with pd.ExcelWriter(out, engine="openpyxl") as xw:
    pd.DataFrame({"Note": ["SYNTHETIC demonstration data - not real boreholes."]}).to_excel(
        xw, sheet_name="About", index=False)
    boreholes.to_excel(xw, sheet_name="Boreholes", index=False)
    lithology.to_excel(xw, sheet_name="Lithology", index=False)
    construction.to_excel(xw, sheet_name="Construction", index=False)
    wl.to_excel(xw, sheet_name="WaterLevels", index=False)
    downhole.to_excel(xw, sheet_name="Downhole", index=False)
    fractures.to_excel(xw, sheet_name="Fractures", index=False)
print("wrote", out)
