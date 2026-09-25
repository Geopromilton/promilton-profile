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

    lg = sub.add_parser("legend", help="print the lithology codes, or draw them to a file")
    lg.add_argument("data", nargs="?", help="workbook with a custom Legend sheet (optional)")
    lg.add_argument("-o", "--out", help="save a legend chart (pdf/png/svg)")

    a = p.parse_args(argv)
    return {"template": _template, "validate": _validate, "striplog": _striplog,
            "legend": _legend, "convert": _convert, "section": _section, "fence": _fence}[a.cmd](a)


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
    kw = dict(ve=a.ve, page=a.page, title=a.title or project.name, datum=a.datum)
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


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)


if __name__ == "__main__":
    raise SystemExit(main())
