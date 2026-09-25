"""Read projects from Excel workbooks or CSV folders, and write the input template.

Headers are matched loosely: case, spaces, units in brackets and common
synonyms are ignored, so "Borehole ID", "BH_ID" and "Well" all work.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .patterns import DEFAULT_LEGEND, PATTERNS, Legend
from .project import TABLE_COLUMNS, Project, empty_table

SHEET_ALIASES = {
    "boreholes": ["boreholes", "borehole", "collars", "collar", "locations", "wells", "sites"],
    "lithology": ["lithology", "litho", "strata", "lithologs", "litholog", "geology"],
    "construction": ["construction", "well_construction", "casing", "completion"],
    "water_levels": ["water_levels", "water_level", "waterlevels", "wl", "swl"],
    "downhole": ["downhole", "downhole_data", "geophysics", "logs", "measurements"],
    "fractures": ["fractures", "fracture", "joints", "structures", "structural", "discontinuities"],
    "legend": ["legend", "lithology_legend", "codes", "lithology_codes"],
}

COLUMN_ALIASES = {
    "boreholes": {
        "borehole_id": ["borehole_id", "borehole", "bh_id", "bh", "well_id", "well", "id", "hole_id", "name"],
        "x": ["x", "easting", "longitude", "lon", "long"],
        "y": ["y", "northing", "latitude", "lat"],
        "elevation": ["elevation", "elev", "rl", "ground_level", "ground_elevation", "gl", "z"],
        "total_depth": ["total_depth", "td", "depth", "drilled_depth", "total_drilled_depth"],
    },
    "lithology": {
        "borehole_id": ["borehole_id", "borehole", "bh_id", "bh", "well_id", "well", "id", "hole_id"],
        "from": ["from", "depth_from", "top", "from_depth", "top_depth"],
        "to": ["to", "depth_to", "bottom", "to_depth", "bottom_depth", "base"],
        "code": ["code", "lithology_code", "litho_code", "lith_code", "rock_code", "lithology"],
        "description": ["description", "desc", "remarks", "log_description"],
    },
    "construction": {
        "borehole_id": ["borehole_id", "borehole", "bh_id", "bh", "well_id", "well", "id", "hole_id"],
        "from": ["from", "depth_from", "top"],
        "to": ["to", "depth_to", "bottom"],
        "element": ["element", "type", "component", "item"],
        "diameter": ["diameter", "dia", "size"],
        "material": ["material", "remarks"],
    },
    "water_levels": {
        "borehole_id": ["borehole_id", "borehole", "bh_id", "bh", "well_id", "well", "id", "hole_id"],
        "date": ["date", "measured_on", "date_measured"],
        "depth": ["depth", "depth_to_water", "dtw", "swl", "water_level", "wl"],
    },
    "downhole": {
        "borehole_id": ["borehole_id", "borehole", "bh_id", "bh", "well_id", "well", "id", "hole_id"],
        "depth": ["depth", "md"],
        "parameter": ["parameter", "param", "variable", "log", "curve"],
        "value": ["value", "reading", "val"],
        "unit": ["unit", "units"],
    },
}

COLUMN_ALIASES["fractures"] = {
    "borehole_id": ["borehole_id", "borehole", "bh_id", "bh", "well_id", "well", "id", "hole_id"],
    "depth": ["depth", "md", "depth_m"],
    "dip": ["dip", "dip_angle", "inclination"],
    "dip_direction": ["dip_direction", "dip_dir", "dipdir", "azimuth", "dip_azimuth", "direction"],
    "aperture": ["aperture", "opening", "width"],
    "yield": ["yield", "discharge", "water_strike", "flow"],
    "remarks": ["remarks", "type", "description", "comment"],
}

NUMERIC = {
    "boreholes": ["x", "y", "elevation", "total_depth"],
    "lithology": ["from", "to"],
    "construction": ["from", "to", "diameter"],
    "water_levels": ["depth"],
    "downhole": ["depth", "value"],
    "fractures": ["depth", "dip", "dip_direction", "aperture", "yield"],
}


def normalize(name) -> str:
    s = re.sub(r"[\(\[].*?[\)\]]", "", str(name)).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _match_table(sheet_name: str):
    n = normalize(sheet_name)
    for table, aliases in SHEET_ALIASES.items():
        if n in aliases:
            return table
    return None


def _standardize(df: pd.DataFrame, table: str) -> pd.DataFrame:
    df = df.dropna(how="all").copy()
    aliases = COLUMN_ALIASES.get(table, {})
    rename, used = {}, set()
    norm = {c: normalize(c) for c in df.columns}
    # Exact canonical names first, then synonyms in priority order.
    for canon, alts in aliases.items():
        for alt in alts:
            hit = next((c for c, n in norm.items() if n == alt and c not in used), None)
            if hit is not None:
                rename[hit] = canon
                used.add(hit)
                break
    for c, n in norm.items():
        if c not in used:
            rename[c] = n
    df = df.rename(columns=rename)
    df = df.loc[:, ~df.columns.duplicated()]
    for col in TABLE_COLUMNS.get(table, []):
        if col not in df.columns:
            df[col] = np.nan
    if "borehole_id" in df.columns:
        df = df[df["borehole_id"].notna()]
        df["borehole_id"] = df["borehole_id"].map(_clean_id)
    for col in NUMERIC.get(table, []):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if table == "lithology":
        df["code"] = df["code"].map(lambda v: "" if pd.isna(v) else str(v).strip().upper())
    if table == "construction":
        df["element"] = df["element"].map(canonical_element)
    if table == "water_levels":
        df["date"] = df["date"].map(parse_date)
    return df.reset_index(drop=True)


def parse_date(v):
    """ISO dates (2025-03-13) as-is; otherwise Indian/European day-first (13-03-2025)."""
    if pd.isna(v) or str(v).strip() == "":
        return pd.NaT
    if isinstance(v, (pd.Timestamp, np.datetime64)) or hasattr(v, "year"):
        return pd.Timestamp(v)
    text = str(v).strip()
    iso = re.match(r"^\d{4}[-/]", text) is not None
    return pd.to_datetime(text, errors="coerce", dayfirst=not iso, yearfirst=iso)


def _clean_id(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


ELEMENTS = {
    "casing": ["casing", "plain_casing", "blank_casing", "blank", "plain", "pipe", "riser"],
    "screen": ["screen", "slotted", "slotted_pipe", "slotted_casing", "filter", "strainer"],
    "gravel_pack": ["gravel_pack", "gravel", "filter_pack", "pack", "shrouding"],
    "seal": ["seal", "grout", "cement", "bentonite", "clay_seal", "sanitary_seal"],
    "open_hole": ["open_hole", "open", "openhole", "uncased"],
}


def canonical_element(v) -> str:
    n = normalize(v) if pd.notna(v) else ""
    for canon, alts in ELEMENTS.items():
        if n in alts:
            return canon
    return n or "casing"


GMS_SUFFIXES = (".txt", ".dat", ".tsv", ".bor")


def load_project(path, name: str | None = None, legend=None) -> Project:
    """Load an Excel workbook, a folder of CSV files, or a GMS borehole text file.

    ``legend`` (a file path or Legend) overrides/extends the lithology codes.
    """
    path = Path(path)
    if path.is_file() and (path.suffix.lower() in GMS_SUFFIXES or _looks_like_gms(path)):
        project = load_gms(path, name=name)
    else:
        project = _load_tables(path, name)
    if legend is not None:
        project.legend = legend if isinstance(legend, Legend) else load_legend(legend, project.legend)
    return project


def load_legend(path, base: Legend | None = None) -> Legend:
    """Read a legend table (CSV or Excel): Code, Name, Color, Pattern[, Group]."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        sheets = pd.read_excel(path, sheet_name=None)
        df = next((d for n, d in sheets.items() if _match_table(n) == "legend"), next(iter(sheets.values())))
    else:
        df = pd.read_csv(path, sep=None, engine="python")
    df = df.dropna(how="all").copy()
    df.columns = [normalize(c) for c in df.columns]
    df = df.rename(columns={"colour": "color", "fill": "color", "lithology": "name",
                            "material": "code", "material_id": "code", "id": "code"})
    df["code"] = df["code"].map(_clean_id)
    return (base or Legend()).updated(df.to_dict("records"))


def save_legend(legend: Legend, path, codes=None) -> Path:
    """Write a legend table (Code, Name, Color, Pattern, Group) that load_legend reads back."""
    codes = list(codes) if codes is not None else [t.code for t in legend]
    rows = [{"Code": c, "Name": legend.get(c).name, "Color": legend.get(c).color,
             "Pattern": legend.get(c).pattern, "Group": legend.get(c).group} for c in codes]
    path = Path(path)
    df = pd.DataFrame(rows)
    df.to_excel(path, index=False, sheet_name="Legend") if path.suffix.lower() == ".xlsx" \
        else df.to_csv(path, index=False)
    return path


def _looks_like_gms(path: Path) -> bool:
    if path.suffix.lower() != ".csv":
        return False
    head = {normalize(c) for c in pd.read_csv(path, sep=None, engine="python", nrows=0).columns}
    return {"x", "y", "z"} <= head and bool(head & {"material", "mat", "material_id", "matid"})


def load_gms(path, name: str | None = None) -> Project:
    """Read a GMS borehole file (columns Name, X, Y, Z, Material).

    Each row is the top elevation of a contact and the material below it; the
    last row of a hole marks its bottom. Depths are converted to m below the
    first (collar) elevation, and material IDs become lithology codes.
    """
    path = Path(path)
    df = pd.read_csv(path, sep=None, engine="python")
    df.columns = [normalize(c) for c in df.columns]
    alias = {"hole_id": "name", "hid": "name", "borehole": "name", "borehole_id": "name", "id": "name",
             "elev": "z", "elevation": "z", "mat": "material", "material_id": "material",
             "matid": "material"}
    df = df.rename(columns={c: alias.get(c, c) for c in df.columns})
    missing = {"name", "x", "y", "z", "material"} - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: GMS borehole file needs columns Name, X, Y, Z, Material "
                         f"(missing: {', '.join(sorted(missing))})")
    df = df.dropna(subset=["name", "z"])
    df["name"] = df["name"].map(_clean_id)
    for c in ("x", "y", "z"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    collars, liths = [], []
    for bid, g in df.groupby("name", sort=False):
        g = g.sort_values("z", ascending=False, kind="stable")
        top = g["z"].iloc[0]
        zs, mats = list(g["z"]), [_clean_id(m) if pd.notna(m) else "" for m in g["material"]]
        collars.append({"borehole_id": bid, "x": g["x"].iloc[0], "y": g["y"].iloc[0],
                        "elevation": top, "total_depth": round(top - zs[-1], 3)})
        for i in range(len(zs) - 1):
            f, t = round(top - zs[i], 3), round(top - zs[i + 1], 3)
            if t <= f:
                continue
            if liths and liths[-1]["borehole_id"] == bid and liths[-1]["code"] == mats[i] \
                    and abs(liths[-1]["to"] - f) < 1e-9:
                liths[-1]["to"] = t  # merge repeated material rows
            else:
                liths.append({"borehole_id": bid, "from": f, "to": t, "code": mats[i], "description": ""})

    tables = {t: empty_table(t) for t in TABLE_COLUMNS}
    tables["boreholes"] = pd.DataFrame(collars, columns=TABLE_COLUMNS["boreholes"])
    tables["lithology"] = pd.DataFrame(liths, columns=TABLE_COLUMNS["lithology"])
    return Project(**tables, name=name or path.stem)


def write_project(project: Project, path) -> Path:
    """Save a project as a LithoLog workbook (e.g. after importing GMS data)."""
    path = Path(path)
    heads = {
        "boreholes": {"borehole_id": "Borehole ID", "x": "X", "y": "Y", "elevation": "Elevation (m amsl)",
                      "total_depth": "Total depth (m)"},
        "lithology": {"borehole_id": "Borehole ID", "from": "From (m)", "to": "To (m)", "code": "Code",
                      "description": "Description"},
        "construction": {"borehole_id": "Borehole ID", "from": "From (m)", "to": "To (m)",
                         "element": "Element", "diameter": "Diameter (mm)", "material": "Material"},
        "water_levels": {"borehole_id": "Borehole ID", "date": "Date", "depth": "Depth to water (m bgl)"},
        "downhole": {"borehole_id": "Borehole ID", "depth": "Depth (m)", "parameter": "Parameter",
                     "value": "Value", "unit": "Unit"},
        "fractures": {"borehole_id": "Borehole ID", "depth": "Depth (m)", "dip": "Dip (deg)",
                      "dip_direction": "Dip direction (deg)", "aperture": "Aperture (mm)",
                      "yield": "Yield (lps)", "remarks": "Remarks"},
    }
    sheet = {"boreholes": "Boreholes", "lithology": "Lithology", "construction": "Construction",
             "water_levels": "WaterLevels", "downhole": "Downhole", "fractures": "Fractures"}
    used = set(project.lithology["code"])
    legend = pd.DataFrame([{"Code": t.code, "Name": t.name, "Color": t.color, "Pattern": t.pattern,
                            "Group": t.group} for t in project.legend if t.code in used]
                          + [{"Code": t.code, "Name": t.name, "Color": t.color, "Pattern": t.pattern,
                              "Group": t.group} for t in project.legend if t.code not in used])
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        pd.DataFrame(_INSTRUCTIONS, columns=["Topic", "Notes"]).to_excel(xw, sheet_name="Instructions", index=False)
        for table, cols in heads.items():
            df = getattr(project, table)
            extra = [c for c in df.columns if c not in cols]
            df[list(cols) + extra].rename(columns=cols).to_excel(xw, sheet_name=sheet[table], index=False)
        legend.to_excel(xw, sheet_name="Legend", index=False)
        _style_workbook(xw.book)
    return path


def _load_tables(path: Path, name: str | None) -> Project:
    raw: dict[str, pd.DataFrame] = {}
    if path.is_dir():
        for f in sorted(path.glob("*.csv")):
            table = _match_table(f.stem)
            if table:
                raw[table] = pd.read_csv(f)
    elif path.suffix.lower() == ".csv":
        raise ValueError("Give the folder that holds the CSV files, not a single CSV")
    else:
        for sheet, df in pd.read_excel(path, sheet_name=None).items():
            table = _match_table(sheet)
            if table and table not in raw:
                raw[table] = df
    if "boreholes" not in raw and "lithology" not in raw:
        raise ValueError(
            f"No 'Boreholes' or 'Lithology' sheet found in {path}. "
            "Run `litholog template` to get a correctly laid-out workbook."
        )

    tables = {t: _standardize(raw[t], t) if t in raw else empty_table(t) for t in TABLE_COLUMNS}

    # Boreholes present only in data tables still get a (location-less) collar row.
    known = set(tables["boreholes"]["borehole_id"])
    extra = []
    for t in ("lithology", "construction", "water_levels", "downhole"):
        for bid in tables[t]["borehole_id"]:
            if bid not in known:
                known.add(bid)
                extra.append({"borehole_id": bid})
    if extra:
        tables["boreholes"] = pd.concat([tables["boreholes"], pd.DataFrame(extra)], ignore_index=True)

    legend = Legend()
    if "legend" in raw:
        leg = raw["legend"].dropna(how="all").copy()
        leg.columns = [normalize(c) for c in leg.columns]
        leg = leg.rename(columns={"colour": "color", "fill": "color", "lithology": "name"})
        legend = legend.updated(leg.to_dict("records"))

    return Project(**tables, legend=legend, name=name or path.stem)


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

_INSTRUCTIONS = [
    ("LithoLog input workbook", ""),
    ("", ""),
    ("How to use", "Fill in the sheets below (keep the sheet names), save, then run:"),
    ("", "litholog striplog this_file.xlsx"),
    ("", ""),
    ("Boreholes", "One row per borehole. Borehole ID is required; any extra columns you add "
                  "(Location, Date, Drilling method, Logged by, ...) are printed in the log header."),
    ("Lithology", "One row per interval: Borehole ID, From (m), To (m), Code, Description. "
                  "Codes come from the Legend sheet; add your own codes there."),
    ("Construction", "Optional. Element = casing, screen, gravel pack, seal (grout) or open hole; "
                     "Diameter in mm."),
    ("WaterLevels", "Optional. Depth to water in m below ground level, with date."),
    ("Downhole", "Optional. Long format: one row per reading (Depth, Parameter, Value, Unit), "
                 "e.g. resistivity, gamma, EC, yield."),
    ("Fractures", "Optional. Depth, dip (0-90 deg), dip direction (0-360 deg), aperture, yield of "
                  "water strikes. Drawn on strip logs; rose diagrams and stereonets."),
    ("Legend", "Code, Name, Color (hex like #F3E196), Pattern. Patterns can be combined with '+', "
               "e.g. crosses+fractures. Available patterns: " + ", ".join(PATTERNS)),
    ("", ""),
    ("Depths", "All depths are metres below ground level (m bgl). Elevation in m above mean sea level."),
]

_EXAMPLE = {
    "Boreholes": pd.DataFrame([
        {"Borehole ID": "BH-01", "Easting": 650120.0, "Northing": 1689340.0, "Elevation (m amsl)": 482.5,
         "Total depth (m)": 60.0, "Location": "Example site", "Date": "2025-03-12",
         "Drilling method": "DTH", "Logged by": ""},
        {"Borehole ID": "BH-02", "Easting": 650410.0, "Northing": 1689105.0, "Elevation (m amsl)": 479.0,
         "Total depth (m)": 45.0, "Location": "Example site", "Date": "2025-03-14",
         "Drilling method": "DTH", "Logged by": ""},
    ]),
    "Lithology": pd.DataFrame([
        ("BH-01", 0, 1.5, "RSOIL", "Red sandy soil"),
        ("BH-01", 1.5, 9, "WGRA", "Highly weathered pink granite"),
        ("BH-01", 9, 14, "FGRA", "Fractured granite, water struck at 12 m"),
        ("BH-01", 14, 60, "GRA", "Massive grey granite"),
        ("BH-02", 0, 2, "RSOIL", "Red soil"),
        ("BH-02", 2, 11, "WGN", "Weathered gneiss"),
        ("BH-02", 11, 45, "GN", "Hard gneiss"),
    ], columns=["Borehole ID", "From (m)", "To (m)", "Code", "Description"]),
    "Construction": pd.DataFrame([
        ("BH-01", 0, 15, "casing", 165, "PVC"),
        ("BH-01", 15, 60, "open hole", 150, ""),
        ("BH-02", 0, 12, "casing", 165, "MS"),
        ("BH-02", 12, 45, "open hole", 150, ""),
    ], columns=["Borehole ID", "From (m)", "To (m)", "Element", "Diameter (mm)", "Material"]),
    "WaterLevels": pd.DataFrame([
        ("BH-01", "2025-03-13", 11.2),
        ("BH-02", "2025-03-15", 9.8),
    ], columns=["Borehole ID", "Date", "Depth to water (m bgl)"]),
    "Downhole": pd.DataFrame(columns=["Borehole ID", "Depth (m)", "Parameter", "Value", "Unit"]),
    "Fractures": pd.DataFrame([
        ("BH-01", 12.0, 35, 120, 2, 0.8, "Open joint, water strike"),
        ("BH-01", 13.5, 70, 300, 1, None, "Iron-stained joint"),
    ], columns=["Borehole ID", "Depth (m)", "Dip (deg)", "Dip direction (deg)", "Aperture (mm)",
                "Yield (lps)", "Remarks"]),
}


def write_template(path, example: bool = True) -> Path:
    """Write an empty (or example-filled) input workbook."""
    path = Path(path)
    sheets = {k: (v if example else v.iloc[0:0]) for k, v in _EXAMPLE.items()}
    legend = pd.DataFrame([
        {"Code": t.code, "Name": t.name, "Color": t.color, "Pattern": t.pattern, "Group": t.group}
        for t in DEFAULT_LEGEND.values()
    ])
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        pd.DataFrame(_INSTRUCTIONS, columns=["Topic", "Notes"]).to_excel(xw, sheet_name="Instructions", index=False)
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
        legend.to_excel(xw, sheet_name="Legend", index=False)
        _style_workbook(xw.book)
    return path


def _style_workbook(book):
    from openpyxl.styles import Font, PatternFill

    head_fill = PatternFill("solid", fgColor="1F3A5F")
    for ws in book.worksheets:
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = head_fill
        ws.freeze_panes = "A2"
        for col in ws.columns:
            width = max(len(str(c.value or "")) for c in col)
            ws.column_dimensions[col[0].column_letter].width = min(max(12, width + 2), 90)
    legend = book["Legend"]
    for row in legend.iter_rows(min_row=2):
        color = str(row[2].value or "").lstrip("#")
        if re.fullmatch(r"[0-9A-Fa-f]{6}", color):
            row[2].fill = PatternFill("solid", fgColor=color.upper())
