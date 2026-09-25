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

    lg = sub.add_parser("legend", help="print the lithology codes, or draw them to a file")
    lg.add_argument("data", nargs="?", help="workbook with a custom Legend sheet (optional)")
    lg.add_argument("-o", "--out", help="save a legend chart (pdf/png/svg)")

    a = p.parse_args(argv)
    return {"template": _template, "validate": _validate, "striplog": _striplog,
            "legend": _legend, "convert": _convert}[a.cmd](a)


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


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)


if __name__ == "__main__":
    raise SystemExit(main())
