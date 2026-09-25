"""Printable borehole strip logs (A4 portrait, PDF/PNG/SVG).

Page layout, top to bottom: header block, track titles, the log body
(depth | elevation | lithology | description | well | downhole curves),
legend, footer. All positions are in millimetres on the page.
"""

from __future__ import annotations

import math
import textwrap
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import Polygon, Rectangle  # noqa: E402

from . import __version__  # noqa: E402
from .patterns import Legend, draw_interval  # noqa: E402
from .project import Borehole  # noqa: E402

PT_MM = 25.4 / 72  # one typographic point in mm
INK = "#1E1E1E"
GRID = "#D5D5D5"
ACCENT = "#1F3A5F"
WATER = "#1F77B4"
CURVE_COLORS = ["#B8433A", "#2E6F9E", "#3C8C4F"]


@dataclass
class Style:
    page_w: float = 210.0
    page_h: float = 297.0
    margin: float = 10.0
    header_h: float = 36.0
    title_h: float = 9.0
    legend_h: float = 27.0
    footer_h: float = 6.0
    depth_w: float = 12.0
    elev_w: float = 14.0
    lith_w: float = 24.0
    well_w: float = 26.0
    curve_w: float = 24.0
    max_curves: int = 3
    font: str = "Inter"
    desc_size: float = 6.3
    project_name: str = ""


def _nice_step(span: float, target: int = 12) -> float:
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


class _Page:
    """Helper that places axes by millimetre coordinates measured from the top-left."""

    def __init__(self, style: Style):
        self.s = style
        self.fig = plt.figure(figsize=(style.page_w / 25.4, style.page_h / 25.4))

    def axes(self, x, y, w, h, xlim=(0, 1), ylim=None):
        s = self.s
        ax = self.fig.add_axes([x / s.page_w, 1 - (y + h) / s.page_h, w / s.page_w, h / s.page_h])
        ax.set_xlim(*xlim)
        ax.set_ylim(*(ylim if ylim is not None else (h, 0)))  # default: mm, y downward
        ax.set_axis_off()
        return ax


def striplog_pages(bh: Borehole, legend: Legend, style: Style | None = None,
                   metres_per_page: float | None = None):
    """Yield one matplotlib Figure per page for a borehole."""
    s = style or Style()
    total = bh.depth or 1.0
    if metres_per_page and metres_per_page > 0:
        n = max(1, math.ceil(total / metres_per_page - 1e-9))
        span = metres_per_page
    else:
        n, span = 1, _nice_top(total)
    for i in range(n):
        yield _draw_page(bh, legend, s, i * span, (i + 1) * span, i + 1, n)


def _nice_top(depth: float) -> float:
    step = _nice_step(depth, 10)
    return math.ceil(depth / step - 1e-9) * step


def save_striplog(bh: Borehole, legend: Legend, path, style: Style | None = None,
                  metres_per_page: float | None = None, dpi: int = 200) -> list[Path]:
    """Save a strip log. PDF gets all pages in one file; PNG/SVG get one file per page."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    figs = list(striplog_pages(bh, legend, style, metres_per_page))
    out = []
    if path.suffix.lower() == ".pdf":
        with PdfPages(path) as pdf:
            for f in figs:
                pdf.savefig(f)
        out.append(path)
    else:
        for i, f in enumerate(figs, 1):
            p = path if len(figs) == 1 else path.with_name(f"{path.stem}_p{i}{path.suffix}")
            f.savefig(p, dpi=dpi)
            out.append(p)
    for f in figs:
        plt.close(f)
    return out


# ---------------------------------------------------------------------------


def _draw_page(bh, legend, s: Style, top, bottom, page_no, n_pages):
    from .typeface import use_in_matplotlib

    use_in_matplotlib()
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [s.font, "Inter", "DejaVu Sans", "Arial"]
    pg = _Page(s)
    fig = pg.fig

    params = []
    if len(bh.downhole):
        dh = bh.downhole.dropna(subset=["depth", "value"])
        params = list(dict.fromkeys(dh["parameter"].astype(str)))[: s.max_curves]

    # Horizontal track layout
    usable = s.page_w - 2 * s.margin
    widths = [("depth", s.depth_w)]
    if bh.has_elevation:
        widths.append(("elev", s.elev_w))
    widths.append(("lith", s.lith_w))
    show_well = len(bh.construction) > 0 or len(bh.water_levels.dropna(subset=["depth"])) > 0
    well_w = s.well_w if show_well else 0.0
    fr = bh.fractures.dropna(subset=["depth", "dip"]) if hasattr(bh, "fractures") else None
    show_fr = fr is not None and len(fr) > 0
    fixed = sum(w for _, w in widths) + well_w + len(params) * s.curve_w + (s.curve_w if show_fr else 0)
    widths.append(("desc", usable - fixed))
    if show_well:
        widths.append(("well", well_w))
    if show_fr:
        widths.append(("fract", s.curve_w))
    widths += [(f"curve:{p}", s.curve_w) for p in params]

    y_title = s.margin + s.header_h + 2
    y_body = y_title + s.title_h
    body_h = s.page_h - s.margin - s.footer_h - s.legend_h - 3 - y_body
    ylim = (bottom, top)

    _header(pg, bh, s, page_no, n_pages)

    x = s.margin
    axes = {}
    for key, w in widths:
        axes[key] = pg.axes(x, y_body, w, body_h, ylim=ylim)
        tax = pg.axes(x, y_title, w, s.title_h)
        tax.add_patch(Rectangle((0, 0), 1, s.title_h, facecolor="#EEF2F7", edgecolor=INK, lw=0.6))
        _track_title(tax, key, bh, s)
        x += w

    step = _nice_step(bottom - top, 12)
    ticks = np.arange(math.ceil(top / step) * step, bottom + 1e-9, step)
    for key, ax in axes.items():
        ax.add_patch(Rectangle((0, 0), 1, 1, transform=ax.transAxes,  # border, independent of track scale
                               facecolor="none", edgecolor=INK, lw=0.6, zorder=6))
        if key not in ("depth", "elev", "lith"):
            for t in ticks:
                ax.axhline(t, color=GRID, lw=0.3, zorder=0)

    _depth_track(axes["depth"], ticks, step, top, bottom, lambda d: d)
    if "elev" in axes:
        _depth_track(axes["elev"], ticks, step, top, bottom, lambda d: bh.elevation - d)
    _lith_track(axes["lith"], bh, legend, top, bottom)
    desc_w = dict(widths)["desc"]
    _desc_track(pg, axes["desc"], bh, legend, top, bottom, s, desc_w, y_body, body_h)
    if "well" in axes:
        _well_track(axes["well"], bh, top, bottom)
    for i, p in enumerate(params):
        _curve_track(axes[f"curve:{p}"], bh, p, CURVE_COLORS[i % len(CURVE_COLORS)])
    if "fract" in axes:
        _fracture_track(axes["fract"], fr, top, bottom)

    _legend(pg, bh, legend, s, y_body + body_h + 3)
    scale = (bottom - top) * 1000 / body_h
    foot = pg.axes(s.margin, s.page_h - s.margin - s.footer_h, usable, s.footer_h)
    foot.text(0, s.footer_h * 0.6, f"LithoLog {__version__} · open-source borehole logging",
              fontsize=5.5, color="#777777", va="center")
    foot.text(0.5, s.footer_h * 0.6, f"Vertical scale ≈ 1:{_round_scale(scale):,}",
              fontsize=5.5, color="#777777", va="center", ha="center")
    foot.text(1, s.footer_h * 0.6, f"Page {page_no} of {n_pages}",
              fontsize=5.5, color="#777777", va="center", ha="right")
    return fig


def _round_scale(v):
    mag = 10 ** max(0, math.floor(math.log10(v)) - 1)
    return int(round(v / mag) * mag)


def _header(pg: _Page, bh: Borehole, s: Style, page_no, n_pages):
    w = s.page_w - 2 * s.margin
    ax = pg.axes(s.margin, s.margin, w, s.header_h, xlim=(0, w))
    ax.add_patch(Rectangle((0, 0), w, s.header_h, facecolor="white", edgecolor=INK, lw=0.8))
    ax.add_patch(Rectangle((0, 0), w, 10, facecolor=ACCENT, edgecolor=INK, lw=0.8))
    ax.text(3, 5, "BOREHOLE LOG", color="white", fontsize=9, fontweight="bold", va="center")
    ax.text(w / 2, 5, bh.id, color="white", fontsize=13, fontweight="bold", va="center", ha="center")
    if s.project_name:
        ax.text(w - 3, 5, s.project_name, color="white", fontsize=7.5, va="center", ha="right")

    fields = []
    if pd.notna(bh.x) and pd.notna(bh.y):
        fields += [("X / Easting", _num(bh.x)), ("Y / Northing", _num(bh.y))]
    if bh.has_elevation:
        fields.append(("Ground elevation", f"{bh.elevation:.2f} m amsl"))
    fields.append(("Total depth", f"{bh.depth:g} m bgl"))
    wl = bh.water_levels.dropna(subset=["depth"])
    if len(wl):
        last = wl.iloc[-1]
        date = f" ({last['date']:%d-%m-%Y})" if pd.notna(last["date"]) else ""
        fields.append(("Water level", f"{last['depth']:g} m bgl{date}"))
    for k, v in bh.info.items():
        if isinstance(v, pd.Timestamp):
            v = f"{v:%d-%m-%Y}"
        fields.append((str(k).replace("_", " ").capitalize(), str(v)))

    cols, rows = 3, 4
    cw = w / cols
    for i, (k, v) in enumerate(fields[: cols * rows]):
        c, r = divmod(i, rows)
        yy = 14 + r * 5.6
        ax.text(3 + c * cw, yy, f"{k}:", fontsize=6, color="#555555", va="center")
        ax.text(3 + c * cw + 25, yy, _clip(v, 34), fontsize=6.6, color=INK, va="center")


def _num(v):
    return f"{v:.6f}" if abs(v) < 400 else f"{v:,.1f}"


def _clip(text, n):
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"


def _fracture_track(ax, fr, top, bottom):
    """Tadpole plot: dot at the dip (x, 0–90°) and depth; tail points in the dip direction
    (map view: north up). Water strikes are blue with their yield."""
    ax.set_xlim(-8, 98)
    for x in (0, 30, 60, 90):
        ax.axvline(x, color=GRID, lw=0.3, zorder=0)
    span = bottom - top
    ymm = span / max(ax.get_position().height * ax.figure.get_figheight() * 25.4, 1)  # m per mm
    xmm = 106 / max(ax.get_position().width * ax.figure.get_figwidth() * 25.4, 1)    # x-units per mm
    for _, r in fr.iterrows():
        d = r["depth"]
        if not top <= d <= bottom:
            continue
        water = pd.notna(r.get("yield")) and r.get("yield", 0) > 0
        col = WATER if water else INK
        ax.scatter([r["dip"]], [d], s=9 if water else 6, color=col, zorder=4, lw=0)
        if pd.notna(r.get("dip_direction")):
            a = np.radians(r["dip_direction"])
            ax.plot([r["dip"], r["dip"] + 2.6 * xmm * np.sin(a)], [d, d - 2.6 * ymm * np.cos(a)],
                    color=col, lw=0.7, zorder=4)
        if water:
            ax.text(96, d, f"{r['yield']:g}", fontsize=4.5, color=WATER, ha="right", va="center")
    for x in (0, 30, 60, 90):
        ax.text(x, bottom, f"{x}", fontsize=4.5, ha="center", va="bottom", color="#777777")


def _track_title(ax, key, bh, s):
    h = s.title_h
    titles = {"depth": "Depth\n(m bgl)", "elev": "Elev.\n(m amsl)", "lith": "Lithology",
              "desc": "Description", "well": "Well\nconstruction", "fract": "Fractures\n(dip 0–90°)"}
    if key.startswith("curve:"):
        p = key.split(":", 1)[1]
        unit = bh.downhole.loc[bh.downhole["parameter"].astype(str) == p, "unit"].dropna()
        label = p + (f"\n({unit.iloc[0]})" if len(unit) else "")
    else:
        label = titles[key]
    ax.text(0.5, h / 2, label, ha="center", va="center", fontsize=6.3, fontweight="bold",
            color=INK, linespacing=1.1)


def _depth_track(ax, ticks, step, top, bottom, label_fn):
    minor = step / 5
    for t in np.arange(math.ceil(top / minor) * minor, bottom + 1e-9, minor):
        ax.plot([0.82, 1], [t, t], color=INK, lw=0.35)
    for t in ticks:
        ax.plot([0.62, 1], [t, t], color=INK, lw=0.6)
        va = "top" if abs(t - top) < 1e-9 else "bottom" if abs(t - bottom) < 1e-9 else "center"
        ax.text(0.57, t, f"{label_fn(t):g}", ha="right", va=va, fontsize=5.6, color=INK)


def _lith_track(ax, bh, legend, top, bottom):
    for _, r in bh.lithology.iterrows():
        f, t = r["from"], r["to"]
        if pd.isna(f) or pd.isna(t) or t <= f or t < top or f > bottom:
            continue
        lt = legend.get(r["code"])
        draw_interval(ax, 0, 1, max(f, top), min(t, bottom), lt)
        if r["code"] not in legend:
            ax.text(0.5, (max(f, top) + min(t, bottom)) / 2, "?", ha="center", va="center",
                    fontsize=8, color="#AA0000", zorder=5)


def _desc_track(pg, ax, bh, legend, top, bottom, s: Style, width_mm, y_body, body_h):
    """Descriptions next to their interval; labels are pushed apart when intervals are thin."""
    # Work in mm inside the description track.
    x0 = ax.get_position().x0 * s.page_w
    mm = pg.axes(x0, y_body, width_mm, body_h, xlim=(0, width_mm))
    to_mm = lambda d: (d - top) / (bottom - top) * body_h  # noqa: E731

    line_h = s.desc_size * PT_MM * 1.22
    chars = max(10, int((width_mm - 7) / (s.desc_size * PT_MM * 0.55)))
    items = []
    for _, r in bh.lithology.iterrows():
        f, t = r["from"], r["to"]
        if pd.isna(f) or pd.isna(t) or t <= f or t < top or f > bottom:
            continue
        lt = legend.get(r["code"])
        desc = r["description"] if isinstance(r["description"], str) and r["description"].strip() else lt.name
        head = f"{f:g}–{t:g} m"
        lines = textwrap.wrap(f"{head}  {desc}", chars)[:4]
        mid = to_mm((max(f, top) + min(t, bottom)) / 2)
        mm.plot([0, 1.2], [to_mm(max(f, top))] * 2, color=INK, lw=0.4)
        items.append([mid, len(lines) * line_h, lines, head])

    # De-overlap: push down, then pull up from the bottom edge.
    gap = 0.6
    tops = []
    for mid, h, _, _ in items:
        t = max(mid - h / 2, (tops[-1][1] + gap) if tops else 0.5)
        tops.append([t, t + h])
    limit = body_h - 0.5
    for i in range(len(tops) - 1, -1, -1):
        over = tops[i][1] - (limit if i == len(tops) - 1 else tops[i + 1][0] - gap)
        if over > 0:
            tops[i][0] -= over
            tops[i][1] -= over

    for (mid, h, lines, head), (t, b) in zip(items, tops):
        cy = (t + b) / 2
        if abs(cy - mid) > 0.3:
            mm.plot([1.2, 3.2, 4.4], [mid, mid, cy], color="#888888", lw=0.35)
        for j, line in enumerate(lines):
            y = t + (j + 0.5) * line_h
            if j == 0 and line.startswith(head):
                h_txt = mm.text(5, y, head, fontsize=s.desc_size, va="center", color=ACCENT,
                                fontweight="bold")
                off = _text_width_mm(h_txt, mm) + s.desc_size * PT_MM * 0.8
                mm.text(5 + off, y, line[len(head):].strip(), fontsize=s.desc_size, va="center", color=INK)
            else:
                mm.text(5, y, line, fontsize=s.desc_size, va="center", color=INK)


def _text_width_mm(text, ax) -> float:
    """Rendered width of a text artist in the axes' x units (mm here)."""
    renderer = ax.figure.canvas.get_renderer()
    bb = text.get_window_extent(renderer).transformed(ax.transData.inverted())
    return abs(bb.x1 - bb.x0)


def _well_track(ax, bh, top, bottom):
    ax.set_xlim(-1, 1)
    con = bh.construction.dropna(subset=["from", "to"])
    diam = [d for d in con["diameter"] if pd.notna(d)]
    # Drawn hole is always wider than the widest pipe so the annulus (seal, pack) shows.
    given = bh.info.get("diameter")
    given = float(given) if isinstance(given, (int, float)) and given > 0 else 0.0
    hole_d = max(given, max(diam) * 1.35 if diam else 0.0) or 200.0
    half = lambda d: 0.78 * (d / hole_d) if pd.notna(d) else 0.5  # noqa: E731
    H = 0.78
    td = bh.depth
    if td <= top:
        return
    b = min(td, bottom)
    # Borehole wall
    ax.add_patch(Rectangle((-H, top), 2 * H, b - top, facecolor="#FAFAF7", edgecolor="none", zorder=1))
    ax.plot([-H, -H], [top, b], color="#6B5B4B", lw=0.8, zorder=3)
    ax.plot([H, H], [top, b], color="#6B5B4B", lw=0.8, zorder=3)
    if td <= bottom:
        ax.plot([-H, H], [td, td], color="#6B5B4B", lw=0.8, zorder=3)

    def clip(r):
        return max(r["from"], top), min(r["to"], bottom)

    for _, r in con.iterrows():  # annulus fills first
        f, t = clip(r)
        if t <= f:
            continue
        if r["element"] == "gravel_pack":
            ax.add_patch(Rectangle((-H, f), 2 * H, t - f, facecolor="#F1DDB0", edgecolor="none", zorder=1.5))
            ys = np.arange(math.floor(f), t, max((bottom - top) / 150, 0.05))
            for k, y in enumerate(ys):
                xs = np.arange(-H + 0.08 + (0.07 if k % 2 else 0), H, 0.16)
                ax.scatter(xs, np.full_like(xs, y), s=0.8, color="#8A6D3B", zorder=1.6, lw=0)
        elif r["element"] == "seal":
            ax.add_patch(Rectangle((-H, f), 2 * H, t - f, facecolor="#9E9E9E", edgecolor="none",
                                   hatch="xxxx", zorder=1.5, lw=0))
    for _, r in con.iterrows():  # then pipes
        f, t = clip(r)
        if t <= f or r["element"] in ("gravel_pack", "seal", "open_hole"):
            continue
        h = half(r["diameter"]) if pd.notna(r["diameter"]) else 0.5
        ax.add_patch(Rectangle((-h, f), 2 * h, t - f, facecolor="white", edgecolor="none", zorder=2))
        if r["element"] == "screen":
            for side in (-h, h):
                ax.plot([side, side], [f, t], color=INK, lw=1.3, ls=(0, (2, 1.2)), zorder=4)
            for y in np.arange(f, t, max((bottom - top) / 110, 0.05)):
                ax.plot([-h + 0.05, -h + 0.25], [y, y], color=INK, lw=0.4, zorder=4)
                ax.plot([h - 0.25, h - 0.05], [y, y], color=INK, lw=0.4, zorder=4)
        else:
            for side in (-h, h):
                ax.plot([side, side], [f, t], color=INK, lw=1.3, zorder=4)
    # Water levels (latest drawn boldest)
    wl = bh.water_levels.dropna(subset=["depth"])
    for i, (_, r) in enumerate(wl.tail(3).iloc[::-1].iterrows()):
        d = r["depth"]
        if not top <= d <= bottom:
            continue
        alpha = 1.0 if i == 0 else 0.45
        ax.plot([-H, H], [d, d], color=WATER, lw=0.9, alpha=alpha, zorder=5)
        tri_h = (bottom - top) * 0.012
        ax.add_patch(Polygon([[-0.12, d - tri_h], [0.12, d - tri_h], [0, d]], closed=True,
                             facecolor=WATER, edgecolor="none", alpha=alpha, zorder=6))
        if i == 0:
            ax.text(0.2, d + tri_h * 0.3, f"{d:g}", fontsize=5.5, color=WATER, ha="left", va="top",
                    zorder=6, bbox=dict(facecolor="white", edgecolor="none", pad=0.4, alpha=0.85))


def _curve_track(ax, bh, param, color):
    d = bh.downhole
    d = d[(d["parameter"].astype(str) == param)].dropna(subset=["depth", "value"]).sort_values("depth")
    if d.empty:
        return
    lo, hi = d["value"].min(), d["value"].max()
    pad = (hi - lo) * 0.08 or max(abs(hi) * 0.1, 1)
    ax.set_xlim(lo - pad, hi + pad)
    for v in np.linspace(lo, hi, 3):
        ax.axvline(v, color=GRID, lw=0.3, zorder=0)
    style = dict(color=color, lw=0.9, zorder=3)
    if len(d) <= 40:
        style.update(marker="o", ms=1.8)
    ax.plot(d["value"], d["depth"], **style)
    ymin, ymax = ax.get_ylim()
    ax.text(lo, ymax, f"{lo:g}", fontsize=5, color=color, ha="left", va="bottom",
            transform=ax.transData, clip_on=False)
    ax.text(hi, ymax, f"{hi:g}", fontsize=5, color=color, ha="right", va="bottom",
            transform=ax.transData, clip_on=False)


def _legend(pg: _Page, bh, legend, s: Style, y):
    """Lithologies used in this log, then well symbols, in a 4 x 4 grid."""
    w = s.page_w - 2 * s.margin
    ax = pg.axes(s.margin, y, w, s.legend_h, xlim=(0, w))
    ax.add_patch(Rectangle((0, 0), w, s.legend_h, facecolor="white", edgecolor=INK, lw=0.6))
    ax.text(2, 3, "Legend", fontsize=6.8, fontweight="bold", va="center", color=INK)

    items = [("lith", c) for c in dict.fromkeys(c for c in bh.lithology["code"] if c)]
    if len(bh.water_levels.dropna(subset=["depth"])):
        items.append(("water", "Water level (m bgl)"))
    elems = set(bh.construction["element"])
    for e, label in (("casing", "Casing"), ("screen", "Screen / slotted pipe"),
                     ("gravel_pack", "Gravel pack"), ("seal", "Seal / grout")):
        if e in elems:
            items.append((e, label))

    cols, rows = 4, 4
    if len(items) > cols * rows:  # keep every lithology; drop well symbols first
        liths = [i for i in items if i[0] == "lith"]
        items = (liths + [i for i in items if i[0] != "lith"])[: cols * rows]
    cw = (w - 4) / cols
    sw, sh = 9.0, 4.2
    for i, (kind, val) in enumerate(items):
        r, c = divmod(i, cols)
        x0, y0 = 2 + c * cw, 6 + r * 5.2
        sx = x0 + sw / 2
        label = val
        if kind == "lith":
            lt = legend.get(val)
            sub = pg.axes(s.margin + x0, y + y0, sw, sh, xlim=(0, 1), ylim=(sh, 0))
            draw_interval(sub, 0, 1, 0, sh, lt, lw=0.4)
            label = f"{lt.name} ({val})"
        elif kind == "water":
            ax.plot([x0, x0 + sw], [y0 + sh / 2] * 2, color=WATER, lw=0.9)
            ax.add_patch(Polygon([[sx - 1, y0 + 0.4], [sx + 1, y0 + 0.4], [sx, y0 + sh / 2]],
                                 facecolor=WATER, edgecolor="none"))
        elif kind in ("casing", "screen"):
            ls = "-" if kind == "casing" else (0, (2, 1.2))
            for dx in (-1.5, 1.5):
                ax.plot([sx + dx, sx + dx], [y0, y0 + sh], color=INK, lw=1.2, ls=ls)
        elif kind == "gravel_pack":
            ax.add_patch(Rectangle((x0, y0), sw, sh, facecolor="#F1DDB0", edgecolor=INK, lw=0.4))
        elif kind == "seal":
            ax.add_patch(Rectangle((x0, y0), sw, sh, facecolor="#9E9E9E", edgecolor=INK,
                                   lw=0.4, hatch="xxxx"))
        ax.text(x0 + sw + 1.5, y0 + sh / 2, _clip(label, 34), fontsize=5.8, va="center", color=INK)
