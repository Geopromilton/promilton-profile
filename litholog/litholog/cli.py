"""Command line: ``litholog template | validate | striplog | legend``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="litholog", description="Open-source borehole logs.")
    p.add_argument("--version", action="version", version=f"litholog {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("template", help="write an input Excel workbook to fill in")
    t.add_argument("file", nargs="?", default="litholog_input.xlsx")
    t.add_argument("--empty", action="store_true", help="no example rows")

    v = sub.add_parser("validate", help="check a workbook / CSV folder for data errors")
    v.add_argument("data")
    v.add_argument("-l", "--legend", help="legend file (CSV/Excel: Code, Name, Color, Pattern)")

    c = sub.add_parser("convert", help="convert GMS borehole text (or any input) to a LithoLog workbook")
    c.add_argument("data")
    c.add_argument("out", nargs="?", help="output .xlsx (default: <input>.xlsx)")
    c.add_argument("-l", "--legend", help="legend file for material IDs / codes")

    s = sub.add_parser("striplog", help="draw strip logs for every (or selected) borehole")
    s.add_argument("data", help="Excel workbook, folder of CSV files, or GMS borehole .txt")
    s.add_argument("-l", "--legend", help="legend file (CSV/Excel: Code, Name, Color, Pattern)")
    s.add_argument("-o", "--out", default="striplogs", help="output folder (default: striplogs)")
    s.add_argument("-b", "--boreholes", nargs="+", help="only these borehole IDs")
    s.add_argument("-f", "--format", default="pdf", choices=["pdf", "png", "svg"])
    s.add_argument("-m", "--metres-per-page", type=float, default=None,
                   help="split long holes into pages of this many metres (default: whole hole on one page)")
    s.add_argument("--title", default=None, help="project name printed in the header")
    s.add_argument("--no-combined", action="store_true", help="skip the all-boreholes PDF")

    sc = sub.add_parser("section", help="draw geological cross-sections through boreholes")
    sc.add_argument("data")
    sc.add_argument("-b", "--boreholes", nargs="+", help="boreholes in order along the section")
    sc.add_argument("--line", nargs="+", metavar="X,Y", help="section line vertices, e.g. 778000,943000 790000,935000")
    sc.add_argument("--buffer", type=float, default=500.0, help="include holes within this distance of --line (m)")
    sc.add_argument("-s", "--sections", help="CSV/Excel of sections: Section + Borehole ID (in order), or Section + X + Y")
    sc.add_argument("-n", "--name", default="A-A'", help="section name (default A-A')")
    sc.add_argument("-o", "--out", default="sections", help="output folder (default: sections)")
    sc.add_argument("-f", "--format", default="pdf", choices=["pdf", "png", "svg"])
    sc.add_argument("--ve", type=float, help="vertical exaggeration (default: fit the page)")
    sc.add_argument("--page", default="A3", choices=["A3", "A4"])
    sc.add_argument("--datum", default="elevation", choices=["elevation", "depth"],
                    help="hang holes by elevation (default) or from a flat ground surface")
    sc.add_argument("--title", help="project name printed in the title bar")
    sc.add_argument("-l", "--legend", help="legend file (CSV/Excel)")
    sc.add_argument("--style", default="section", choices=["section", "logs"],
                    help="'logs' draws a log section (strip logs along the line)")
    sc.add_argument("--curve", help="downhole parameter to plot beside each log (log sections)")

    fe = sub.add_parser("fence", help="draw a 3D fence diagram")
    fe.add_argument("data")
    fe.add_argument("-b", "--boreholes", nargs="+", help="only these boreholes (default: all)")
    fe.add_argument("--network", default="mst", choices=["mst", "delaunay", "sections"],
                    help="how holes are joined: mst (default), delaunay, or the lines in --sections")
    fe.add_argument("-s", "--sections", help="sections file (used with --network sections)")
    fe.add_argument("-o", "--out", default="fence.pdf", help="output file (pdf/png/svg)")
    fe.add_argument("--ve", type=float, help="vertical exaggeration")
    fe.add_argument("--azim", type=float, default=-60, help="view direction in degrees (default -60)")
    fe.add_argument("--elev", type=float, default=28, help="view height in degrees (default 28)")
    fe.add_argument("--views", type=int, help="save N views around the model instead of one")
    fe.add_argument("--datum", default="elevation", choices=["elevation", "depth"])
    fe.add_argument("--title", help="project name")
    fe.add_argument("-l", "--legend", help="legend file (CSV/Excel)")

    mp = sub.add_parser("map", help="contour maps: ground, top/base/depth/thickness of a unit, water table")
    mp.add_argument("data")
    mp.add_argument("-a", "--attributes", nargs="+", required=True, metavar="ATTR",
                    help="ground, top:CODE, base:CODE, depth:CODE, thickness:CODE, water, dtw, total_depth")
    mp.add_argument("-m", "--method", default="idw", choices=["idw", "linear", "kriging"])
    mp.add_argument("--cell", type=float, help="grid cell size in m (default: ~150 cells across)")
    mp.add_argument("--no-mask", action="store_true", help="grid the full rectangle, not just the borehole area")
    mp.add_argument("--boundary", help="study-area polygon (.shp, zipped .shp, .kml, .kmz, .geojson) to clip the maps to")
    mp.add_argument("--crs", help="coordinate system of the borehole X/Y, e.g. EPSG:32643 "
                                  "(default: match the boundary automatically)")
    mp.add_argument("-o", "--out", default="maps", help="output folder (default: maps)")
    mp.add_argument("-f", "--format", default="pdf", choices=["pdf", "png", "svg"])
    mp.add_argument("--page", default="A3", choices=["A3", "A4"])
    mp.add_argument("--title", help="project name")
    mp.add_argument("-l", "--legend", help="legend file (CSV/Excel)")

    md = sub.add_parser("model", help="3D lithology block model, volumes and groundwater storage")
    md.add_argument("data")
    md.add_argument("--cell", type=float, help="horizontal voxel size (m)")
    md.add_argument("--dz", type=float, help="vertical voxel size (m)")
    md.add_argument("--method", default="horizons", choices=["horizons", "voxel"],
                    help="horizons: layers correlated between holes and stacked (continuous layers, default); voxel: indicator interpolation")
    md.add_argument("--grid-method", default="idw", choices=["idw", "linear", "kriging"],
                    help="interpolation of horizon thickness (horizons method)")
    md.add_argument("--dem", help="DEM (GeoTIFF .tif or ESRI .asc) used as the ground surface")
    md.add_argument("--rectify", action="store_true", help="replace collar elevations with the DEM")
    md.add_argument("--datum", default="depth", choices=["depth", "elevation"],
                    help="correlate at equal depth below ground (default; weathered/fractured "
                         "hard-rock aquifers) or equal elevation (flat-lying sediments)")
    md.add_argument("--only", nargs="+", metavar="CODE", help="also draw these units on their own")
    md.add_argument("--sy", nargs="+", metavar="CODE=SY", help="specific yield per unit, e.g. 4=0.015")
    md.add_argument("--boundary", help="study-area polygon (.shp, zipped .shp, .kml, .kmz, .geojson) to clip to")
    md.add_argument("--crs", help="coordinate system of the borehole X/Y, e.g. EPSG:32643")
    md.add_argument("--ve", type=float, help="vertical exaggeration")
    md.add_argument("--azim", type=float, default=-60)
    md.add_argument("--elev", type=float, default=30)
    md.add_argument("--style", default="smooth", choices=["smooth", "blocks", "both"],
                    help="smooth solids (interactive HTML + standard views; default), voxel blocks, or both")
    md.add_argument("--views", nargs="+", metavar="VIEW",
                    help="views for smooth solids: oblique_sw oblique_se oblique_ne oblique_nw top front "
                         "back left right (default: all main views)")
    md.add_argument("--cutaway", default="sw", choices=["sw", "se", "ne", "nw", "none"],
                    help="quadrant removed in oblique views of the smooth model (default sw)")
    md.add_argument("-o", "--out", default="model", help="output folder (default: model)")
    md.add_argument("-f", "--format", default="pdf", choices=["pdf", "png", "svg"])
    md.add_argument("--title", help="project name")
    md.add_argument("-l", "--legend", help="legend file (CSV/Excel)")

    aq = sub.add_parser("aquifer", help="water table from observation wells, saturated volume and storage")
    aq.add_argument("data")
    aq.add_argument("-w", "--wells", help="observation wells (CSV/Excel; X/Y or Lat/Lon; long or per-season "
                                          "columns). Default: water levels in the borehole data")
    aq.add_argument("-r", "--reading", nargs="+", help="which readings/seasons (default: all)")
    aq.add_argument("--sy", nargs="+", metavar="CODE=SY", help="specific yield per unit, e.g. 4=0.015")
    aq.add_argument("--crs", help="coordinate system of borehole X/Y (for lat/lon wells), e.g. EPSG:32643")
    aq.add_argument("--boundary", help="study-area polygon (.shp, .kml, .kmz, .geojson)")
    aq.add_argument("--datum", default="depth", choices=["depth", "elevation"])
    aq.add_argument("--model", default="horizons", choices=["horizons", "voxel"])
    aq.add_argument("--dem", help="DEM used as the ground surface")
    aq.add_argument("-m", "--method", default="idw", choices=["idw", "linear", "kriging"])
    aq.add_argument("-o", "--out", default="aquifer")
    aq.add_argument("--title")
    aq.add_argument("-l", "--legend")

    pr = sub.add_parser("property", help="3D model of a downhole parameter (resistivity, EC, yield, ...)")
    pr.add_argument("data")
    pr.add_argument("-p", "--parameter", help="downhole parameter (default: list them)")
    pr.add_argument("--anisotropy", type=float, help="horizontal/vertical range ratio (default: automatic)")
    pr.add_argument("--scale", choices=["auto", "log", "linear"], default="auto")
    pr.add_argument("--below", type=float, help="report the volume with values at or below this")
    pr.add_argument("--above", type=float, help="report the volume with values at or above this")
    pr.add_argument("--boundary")
    pr.add_argument("--crs")
    pr.add_argument("--datum", default="depth", choices=["depth", "elevation"])
    pr.add_argument("--model", default="horizons", choices=["horizons", "voxel"])
    pr.add_argument("--dem", help="DEM used as the ground surface")
    pr.add_argument("-o", "--out", default="property")
    pr.add_argument("--title")

    stp = sub.add_parser("strat", help="stratigraphic (layer-cake) model from ordered formations")
    stp.add_argument("data")
    stp.add_argument("--order", nargs="+", required=True, metavar="CODE", help="formations, top to bottom")
    stp.add_argument("--sy", nargs="+", metavar="CODE=SY")
    stp.add_argument("--boundary")
    stp.add_argument("--crs")
    stp.add_argument("-m", "--method", default="idw", choices=["idw", "linear", "kriging"])
    stp.add_argument("-o", "--out", default="strat")
    stp.add_argument("--title")
    stp.add_argument("-l", "--legend")

    ch = sub.add_parser("chem", help="hydrochemistry: Piper, Durov, Stiff, USSL, Wilcox, Gibbs, indices")
    ch.add_argument("file", help="CSV/Excel: Sample, Ca, Mg, Na, K, HCO3, CO3, Cl, SO4, (NO3, EC, TDS, pH, Group)")
    ch.add_argument("-o", "--out", default="chemistry")
    ch.add_argument("--title", default="")

    fr = sub.add_parser("fractures", help="fracture rose diagram, stereonet and frequency")
    fr.add_argument("data")
    fr.add_argument("-b", "--borehole", help="one borehole only (default: all)")
    fr.add_argument("-o", "--out", default="fractures.pdf")
    fr.add_argument("--title")

    cv = sub.add_parser("crossval", help="validate the 3D model: leave-one-out cross-validation, method "
                                         "comparison, volume range and data support")
    cv.add_argument("data")
    cv.add_argument("-u", "--unit", metavar="CODE", help="unit to report in detail, e.g. 4 (default: most common)")
    cv.add_argument("--methods", nargs="+", choices=["horizons_idw", "horizons_kriging", "voxel", "nearest"])
    cv.add_argument("--boundary", help="study-area polygon (.shp, .kml, .kmz, .geojson)")
    cv.add_argument("--crs", help="coordinate system of the borehole X/Y, e.g. EPSG:32643")
    cv.add_argument("--no-volumes", action="store_true", help="skip the volume comparison (faster)")
    cv.add_argument("-o", "--out", default="validation")
    cv.add_argument("--title")
    cv.add_argument("-l", "--legend")

    sub.add_parser("studio", help="open LithoLog Studio, the desktop application")

    ap = sub.add_parser("app", help="open the LithoLog browser app")
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser window")

    lg = sub.add_parser("legend", help="print the lithology codes, or draw them to a file")
    lg.add_argument("data", nargs="?", help="workbook with a custom Legend sheet (optional)")
    lg.add_argument("-o", "--out", help="save a legend chart (pdf/png/svg)")

    a = p.parse_args(argv)
    return {"template": _template, "validate": _validate, "striplog": _striplog,
            "legend": _legend, "convert": _convert, "section": _section, "fence": _fence,
            "map": _map, "model": _model, "app": _app,
            "studio": _studio, "aquifer": _aquifer, "property": _property, "strat": _strat,
            "chem": _chem, "fractures": _fractures, "crossval": _crossval}[a.cmd](a)


def _template(a):
    from .io import write_template

    path = write_template(a.file, example=not a.empty)
    print(f"Wrote {path}. Fill it in, then run:  litholog striplog {path}")
    return 0


def _report(project):
    from .validate import validate

    issues = validate(project)
    for i in issues:
        print(i)
    n_err = sum(i.level == "error" for i in issues)
    print(f"{len(project.ids)} borehole(s) checked: {n_err} error(s), {len(issues) - n_err} warning(s)")
    return n_err


def _validate(a):
    from .io import load_project

    return 1 if _report(load_project(a.data, legend=a.legend)) else 0


def _convert(a):
    from .io import load_project, write_project

    project = load_project(a.data, legend=a.legend)
    out = Path(a.out) if a.out else Path(a.data).with_suffix(".xlsx")
    write_project(project, out)
    print(f"Wrote {out}: {len(project.ids)} borehole(s), {len(project.lithology)} lithology interval(s)")
    return 0


def _striplog(a):
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    from .io import load_project
    from .striplog import Style, save_striplog, striplog_pages

    project = load_project(a.data, legend=a.legend)
    _report(project)
    style = Style(project_name=a.title or project.name)
    ids = a.boreholes or project.ids
    missing = [b for b in ids if b not in project.ids]
    if missing:
        print(f"Unknown borehole ID(s): {', '.join(missing)}", file=sys.stderr)
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for bid in ids:
        files = save_striplog(project.borehole(bid), project.legend, out / f"{_safe(bid)}.{a.format}",
                              style, a.metres_per_page)
        print("  " + ", ".join(str(f) for f in files))
    if len(ids) > 1 and not a.no_combined:
        combined = out / "all_boreholes.pdf"
        with PdfPages(combined) as pdf:
            for bid in ids:
                for fig in striplog_pages(project.borehole(bid), project.legend, style, a.metres_per_page):
                    pdf.savefig(fig)
                    plt.close(fig)
        print(f"  {combined}")
    return 0


def _legend(a):
    from .io import load_project
    from .patterns import Legend

    legend = load_project(a.data).legend if a.data else Legend()
    if not a.out:
        for t in legend:
            print(f"{t.code:8} {t.name:32} {t.color:9} {t.pattern:22} {t.group}")
        return 0
    from .chart import legend_chart

    legend_chart(legend, a.out)
    print(f"Wrote {a.out}")
    return 0


def _read_sections(project, path, buffer):
    """Sections file -> list of SectionLine (by borehole order, or by X/Y vertices)."""
    import pandas as pd

    from .io import _clean_id, normalize
    from .section import along_line, through_boreholes

    p = Path(path)
    df = pd.read_excel(p) if p.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(p, sep=None, engine="python")
    df.columns = [normalize(c) for c in df.columns]
    df = df.rename(columns={"name": "section", "section_name": "section", "line": "section",
                            "borehole": "borehole_id", "bh": "borehole_id", "well": "borehole_id",
                            "hole_id": "borehole_id", "easting": "x", "northing": "y"})
    if "section" not in df.columns:
        raise ValueError(f"{p.name}: needs a 'Section' column")
    lines = []
    for name, g in df.groupby("section", sort=False):
        name = str(name)
        if "borehole_id" in g.columns and g["borehole_id"].notna().any():
            lines.append(through_boreholes(project, [_clean_id(v) for v in g["borehole_id"].dropna()], name))
        else:
            buf = float(g["buffer"].dropna().iloc[0]) if "buffer" in g.columns and g["buffer"].notna().any() else buffer
            lines.append(along_line(project, list(zip(g["x"], g["y"])), buf, name))
    return lines


def _section(a):
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    from .io import load_project
    from .section import along_line, save_section, section_figure, through_boreholes

    project = load_project(a.data, legend=a.legend)
    if a.sections:
        lines = _read_sections(project, a.sections, a.buffer)
    elif a.boreholes:
        lines = [through_boreholes(project, a.boreholes, a.name)]
    elif a.line:
        verts = [tuple(float(v) for v in pt.split(",")) for pt in a.line]
        lines = [along_line(project, verts, a.buffer, a.name)]
    else:
        print("Give the section as -b BH1 BH2 ..., --line X,Y X,Y ..., or -s sections.csv", file=sys.stderr)
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    kw = dict(ve=a.ve, page=a.page, title=a.title or project.name, datum=a.datum, style=a.style, curve=a.curve)
    for line in lines:
        path = save_section(project, line, out / f"section_{_safe(line.name)}.{a.format}", **kw)
        print(f"  {path}  ({len(line.stations)} boreholes, {line.length:,.0f} m)")
    if len(lines) > 1:
        combined = out / "all_sections.pdf"
        with PdfPages(combined) as pdf:
            for line in lines:
                fig = section_figure(project, line, **kw)
                pdf.savefig(fig)
                plt.close(fig)
        print(f"  {combined}")
    return 0


def _fence(a):
    from .fence import network_edges, save_fence
    from .io import load_project

    project = load_project(a.data, legend=a.legend)
    if a.network == "sections":
        if not a.sections:
            print("--network sections needs -s sections.csv", file=sys.stderr)
            return 2
        edges = []
        for line in _read_sections(project, a.sections, 500.0):
            ids = [st.id for st in line.stations]
            edges += list(zip(ids[:-1], ids[1:]))
    else:
        edges = network_edges(project, a.boreholes, a.network)
    views = None
    if a.views:
        views = [a.azim + k * 360.0 / a.views for k in range(a.views)]
    files = save_fence(project, edges, a.out, views=views, ve=a.ve, azim=a.azim, elev=a.elev,
                       title=a.title or project.name, datum=a.datum)
    for f in files:
        print(f"  {f}  ({len(edges)} panels)")
    return 0


def _map(a):
    from .grid import attribute_label, grid_attribute, write_ascii_grid
    from .io import load_project
    from .maps import save_map

    project = load_project(a.data, legend=a.legend)
    boundary = _boundary(a, project)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for attr in a.attributes:
        grid, vals = grid_attribute(project, attr, a.method, a.cell, mask="none" if a.no_mask else "hull",
                                    boundary=boundary)
        stem = out / _safe(attr.replace(":", "_"))
        save_map(grid, vals, attr, stem.with_suffix(f".{a.format}"), legend=project.legend, method=a.method,
                 title=a.title or project.name, page=a.page, all_xy=project.boreholes)
        write_ascii_grid(grid, stem.with_suffix(".asc"))
        vals.to_csv(stem.with_name(stem.name + "_values.csv"), index=False)
        name, unit = attribute_label(attr, project.legend)
        extra = ""
        if attr.startswith("thickness"):
            import numpy as np

            vol = float(np.nansum(np.where(grid.valid, grid.z, np.nan))) * grid.cell ** 2
            extra = f", isopach volume {vol / 1e6:,.1f} MCM"
        print(f"  {stem.with_suffix('.' + a.format)}  ({name}, {vals['value'].notna().sum()} holes{extra})")
    print(f"  grids (.asc, open in QGIS/ArcGIS/Surfer) and values (.csv) in {out}")
    return 0


def _model(a):
    from .io import load_project
    from .model3d import build_model, model_view, slices_figure, write_vtk

    project = load_project(a.data, legend=a.legend)
    sy = {}
    for item in a.sy or []:
        code, _, val = item.partition("=")
        sy[code.strip().upper()] = float(val)
    boundary = _boundary(a, project)
    model = _build(a, project, boundary)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    kw = dict(title=a.title or project.name, sy=sy, ve=a.ve, azim=a.azim, elev=a.elev)
    files = []
    if a.style in ("smooth", "both"):
        from .solid import export_solids

        cut = None if a.cutaway == "none" else a.cutaway
        files += export_solids(model, project.legend, out, views=a.views, cutaway=cut, ve=a.ve,
                               title=kw["title"], sy=sy)
        for code in a.only or []:
            files += export_solids(model, project.legend, out, views=a.views or ["oblique_sw", "top"],
                                   ve=a.ve, title=kw["title"], sy=sy, only=[code.upper()], sheet=False)
    if a.style in ("blocks", "both"):
        files.append(model_view(model, project.legend, out / f"block_model.{a.format}", **kw))
        for code in a.only or []:
            files.append(model_view(model, project.legend, out / f"block_model_{_safe(code)}.{a.format}",
                                    only=[code.upper()], **kw))
    files.append(slices_figure(model, project.legend, out / f"slices.{a.format}", title=kw["title"]))
    vols = model.volumes(sy)
    vols.insert(1, "name", [project.legend.get(c).name for c in vols["code"]])
    vols.to_csv(out / "volumes.csv", index=False)
    files += [out / "volumes.csv", write_vtk(model, out / "model.vtk")]
    if getattr(model, "kind", "") == "horizon":
        from .horizons import horizon_volumes

        hv = horizon_volumes(model)
        hv.to_csv(out / "horizons.csv", index=False)
        files.append(out / "horizons.csv")
        print(f"{len(hv)} horizons correlated between the boreholes (per-horizon volumes in horizons.csv)")
        if model.h_note:
            print("Note: " + model.h_note)
    nz, ny, nx = model.lith.shape
    print(f"Model {nx} x {ny} x {nz} voxels ({model.cell:g} x {model.cell:g} x {model.dz:g} m), datum: {a.datum}")
    if boundary is not None:
        area = (model.lith >= 0).any(0).sum() * model.cell ** 2 / 1e6
        print(f"Clipped to {boundary.name}: polygon {boundary.area / 1e6:,.1f} km², model {area:,.1f} km²"
              + (f"; {100 * (1 - model.coverage):.0f} % beyond the boreholes (extrapolated)"
                 if model.coverage is not None else ""))
    cols = ["code", "name", "volume_mcm", "percent"] + (["specific_yield", "storage_mcm"] if sy else [])
    print(vols[cols].round({"volume_mcm": 1, "percent": 1, "storage_mcm": 2}).to_string(index=False))
    for f in files:
        print(f"  {f}")
    return 0


def _build(a, project, boundary):
    """Lithology model per --method/--model (horizons by default) with optional --dem."""
    dem = None
    if getattr(a, "dem", None):
        from .dem import MODEL_CRS, load_dem, rectify_collars

        dem = load_dem(a.dem)
        MODEL_CRS["crs"] = getattr(a, "crs", None)
        rep = rectify_collars(project, dem, replace=getattr(a, "rectify", False))
        d = rep["difference"].dropna()
        if len(d):
            print(f"DEM {dem.name}: collar - DEM difference mean {d.mean():+.1f} m, max |{d.abs().max():.1f}| m"
                  + (" (collars replaced by DEM)" if getattr(a, "rectify", False) else ""))
    method = getattr(a, "method", None) if getattr(a, "method", None) in ("horizons", "voxel") \
        else getattr(a, "model", "voxel")
    if method == "horizons":
        from .horizons import build_horizon_model

        return build_horizon_model(project, getattr(a, "cell", None), getattr(a, "dz", None),
                                   method=getattr(a, "grid_method", "idw"), boundary=boundary, dem=dem)
    from .model3d import build_model

    return build_model(project, getattr(a, "cell", None), getattr(a, "dz", None), datum=a.datum,
                       boundary=boundary, dem=dem)


def _boundary(a, project):
    """Load --boundary (reprojected to the boreholes' system), reporting what was done."""
    if not getattr(a, "boundary", None):
        return None
    from .boundary import load_boundary

    b = project.boreholes.dropna(subset=["x", "y"])
    near = (b["x"].min(), b["x"].max(), b["y"].min(), b["y"].max()) if len(b) else None
    boundary = load_boundary(a.boundary, crs=a.crs, near=near)
    if boundary.crs_note:
        print(f"Boundary: {boundary.crs_note}")
    if len(b):
        out = b[~boundary.contains(b[["x", "y"]].to_numpy(float))]
        if len(out):
            print(f"Note: {len(out)} borehole(s) lie outside the boundary: {', '.join(out['borehole_id'])}")
    return boundary


def _sy(items):
    sy = {}
    for item in items or []:
        code, _, val = item.partition("=")
        sy[code.strip().upper()] = float(val)
    return sy


def _aquifer(a):
    import numpy as np

    from .aquifer import load_wells, saturated_thickness, saturated_volumes, water_table, wells_from_project
    from .io import load_project
    from .maps import save_map
    from .model3d import build_model

    project = load_project(a.data, legend=a.legend)
    boundary = _boundary(a, project)
    wells = load_wells(a.wells, crs=a.crs) if a.wells else wells_from_project(project)
    if wells is None:
        print("No water levels: give --wells, or fill the WaterLevels sheet.", file=sys.stderr)
        return 2
    if wells.note:
        print(f"Wells: {wells.note}")
    model = _build(a, project, boundary)
    sy = _sy(a.sy)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    title = a.title or project.name
    readings = a.reading or wells.readings
    tables = {}
    for r in readings:
        wt = water_table(model, wells, r, a.method)
        vals = wt.wells.rename(columns={"well_id": "borehole_id"})
        tag = _safe(str(r))
        save_map(wt.grid, vals.assign(value=vals["wt"]), "water", out / f"water_table_{tag}.pdf",
                 method=a.method, title=f"{title} · {r}")
        save_map(wt.dtw, vals.assign(value=vals["dtw"]), "dtw", out / f"depth_to_water_{tag}.pdf",
                 method=a.method, title=f"{title} · {r}")
        v = saturated_volumes(model, wt, sy)
        v.insert(1, "name", [project.legend.get(c).name for c in v["code"]])
        v.to_csv(out / f"saturated_volumes_{tag}.csv", index=False)
        tables[r] = v
        for code in sy:
            th = saturated_thickness(model, wt, code)
            save_map(th, vals.assign(value=np.nan), f"thickness:{code}", out / f"saturated_thickness_{code}_{tag}.pdf",
                     legend=project.legend, title=f"{title} · saturated · {r}")
        print(f"\n{r}: {len(wt.wells)} wells, water table {np.nanmin(wt.grid.z):.1f}–{np.nanmax(wt.grid.z):.1f} m")
        cols = ["code", "name", "volume_mcm", "saturated_mcm", "saturated_pct"] + (["storage_mcm"] if sy else [])
        print(v[cols].round(1).to_string(index=False))
    if len(readings) >= 2 and sy:
        r0, r1 = readings[0], readings[-1]
        d = tables[r1][["code", "name"]].copy()
        d["storage_change_mcm"] = (tables[r1]["storage_mcm"] - tables[r0]["storage_mcm"]).round(3)
        d.to_csv(out / "storage_change.csv", index=False)
        print(f"\nStorage change {r0} → {r1} (MCM):")
        print(d.dropna().to_string(index=False))
    print(f"\nMaps and tables in {out}")
    return 0


def _property(a):
    from .io import load_project
    from .model3d import build_model
    from .property3d import (build_property, parameters, property_html, property_slices,
                             write_property_vtk)

    project = load_project(a.data)
    params = parameters(project)
    if not a.parameter:
        print("Downhole parameters: " + (", ".join(params) if params else "none (fill the Downhole sheet)"))
        return 0
    boundary = _boundary(a, project)
    model = _build(a, project, boundary)
    log = {"auto": None, "log": True, "linear": False}[a.scale]
    pm = build_property(project, model, a.parameter, a.anisotropy, log=log, datum=a.datum)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = _safe(a.parameter)
    files = [property_slices(pm, out / f"{tag}_slices.pdf", title=a.title or project.name),
             property_html(pm, out / f"{tag}_3d.html", title=a.title or project.name),
             write_property_vtk(pm, out / f"{tag}.vtk")]
    st = pm.stats()
    print(f"{a.parameter} ({pm.unit}): min {st['min']:.4g}, mean {st['mean']:.4g}, max {st['max']:.4g}"
          f" from {len(pm.samples)} readings")
    if a.below is not None or a.above is not None:
        vol = pm.volume_between(a.above, a.below)
        rng = " and ".join(x for x in (f"≥ {a.above:g}" if a.above is not None else "",
                                       f"≤ {a.below:g}" if a.below is not None else "") if x)
        print(f"Volume with {a.parameter} {rng}: {vol / 1e6:,.2f} MCM")
    for f in files:
        print(f"  {f}")
    return 0


def _strat(a):
    from .grid import Grid, write_ascii_grid
    from .io import load_project
    from .model3d import slices_figure
    from .solid import export_solids
    from .strat import build_strat_model

    project = load_project(a.data, legend=a.legend)
    boundary = _boundary(a, project)
    model = build_strat_model(project, a.order, method=a.method, boundary=boundary)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sy = _sy(a.sy)
    files = export_solids(model, project.legend, out, title=a.title or project.name, sy=sy)
    files.append(slices_figure(model, project.legend, out / "slices.pdf", title=a.title or project.name))
    for code, surf in model.surfaces.items():
        files.append(write_ascii_grid(Grid(model.x, model.y, surf, model.cell, model.inside), out / f"top_{_safe(code)}.asc"))
    v = model.volumes(sy)
    v.insert(1, "name", [project.legend.get(c).name for c in v["code"]])
    v.to_csv(out / "volumes.csv", index=False)
    print(v[["code", "name", "volume_mcm", "percent"] + (["storage_mcm"] if sy else [])].round(1).to_string(index=False))
    for f in files:
        print(f"  {f}")
    return 0


def _chem(a):
    from .hydrochem import analyse, load_chemistry, report

    df = load_chemistry(a.file)
    files = report(df, a.out, a.title)
    res = analyse(df)
    bad = res[~res["balance_ok_5pct"]]
    print(f"{len(df)} samples; water types: " + ", ".join(f"{k} ({v})" for k, v in res["water_type"].value_counts().items()))
    if len(bad):
        print(f"Ionic balance outside ±5 %: {', '.join(bad['sample'])}")
    for f in files:
        print(f"  {f}")
    return 0


def _crossval(a):
    from .io import load_project
    from .validation import METHODS, validation_report

    project = load_project(a.data, legend=a.legend)
    boundary = _boundary(a, project)
    n = len(project.ids)
    print(f"Cross-validating {n} boreholes (each hidden and predicted from the others) …")
    r = validation_report(project, a.out, a.methods, boundary, a.unit.upper() if a.unit else None,
                          a.title or project.name, volumes=not a.no_volumes)
    s = r["summary"]
    print("\nDepth logged correctly (mean / worst 10 %):")
    for _, row in s.iterrows():
        print(f"  {METHODS[row['method']]:<30} {row['match_mean']:5.1f} %  / {row['match_p10']:5.1f} %")
    u = r["per_unit"]
    print("\nOccurrences found at hidden boreholes (detection %, false alarms, top-depth error):")
    for code, g in u.groupby("code", sort=False):
        print(f"  {project.legend.get(code).name}")
        for _, row in g.iterrows():
            print(f"    {METHODS[row['method']]:<28} {row['detection_pct']:5.0f} %  {int(row['false_alarms']):4d}  "
                  f"{row['top_mae_m']:5.1f} m")
    if r["volumes"] is not None:
        print("\nVolume range across methods (MCM):")
        for _, row in r["volumes"].iterrows():
            print(f"  {row['unit']:<40} {row['min_mcm']:>10,.0f} – {row['max_mcm']:>10,.0f}  "
                  f"({row['spread_pct']:.0f} %)")
    print(f"\nReport and tables in {a.out}/ (validation.pdf, crossval_*.csv, volumes_by_method.csv)")
    return 0


def _fractures(a):
    from .fractures import fracture_report
    from .io import load_project

    project = load_project(a.data)
    print(f"  {fracture_report(project, a.out, a.borehole, a.title or project.name)}")
    return 0


def _studio(a):
    try:
        from .studio import main as studio_main
    except ImportError as e:
        print(f"LithoLog Studio needs the desktop extras: pip install \"litholog[studio]\"  ({e})",
              file=sys.stderr)
        return 2
    return studio_main(["litholog-studio"])


def _app(a):
    import subprocess

    try:
        import streamlit  # noqa: F401
    except ImportError:
        print("The app needs Streamlit:  pip install \"litholog[app]\"  (or pip install streamlit)",
              file=sys.stderr)
        return 2
    script = Path(__file__).with_name("app.py")
    cmd = [sys.executable, "-m", "streamlit", "run", str(script), "--server.port", str(a.port),
           "--browser.gatherUsageStats", "false"]
    if a.no_browser:
        cmd += ["--server.headless", "true"]
    print(f"LithoLog app: http://localhost:{a.port}  (Ctrl+C to stop)")
    return subprocess.call(cmd)


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)


if __name__ == "__main__":
    raise SystemExit(main())
