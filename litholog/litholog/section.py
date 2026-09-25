"""Geological cross-sections through boreholes (A3/A4 landscape PDF/PNG/SVG)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Polygon, Rectangle  # noqa: E402

from . import __version__  # noqa: E402
from .correlate import panel, units  # noqa: E402
from .patterns import Legend, draw_interval, draw_polygon  # noqa: E402
from .project import Project  # noqa: E402

INK = "#1E1E1E"
ACCENT = "#1F3A5F"
WATER = "#1F77B4"
PAGES = {"A3": (420.0, 297.0), "A4": (297.0, 210.0)}


@dataclass
class Station:
    id: str
    s: float        # distance along the section (m)
    offset: float   # perpendicular distance from the line (m); 0 when the line runs through the hole


@dataclass
class SectionLine:
    name: str
    vertices: list  # [(x, y), ...]
    stations: list = field(default_factory=list)

    @property
    def length(self):
        v = np.asarray(self.vertices, float)
        return float(np.sum(np.hypot(*np.diff(v, axis=0).T))) if len(v) > 1 else 0.0


def through_boreholes(project: Project, ids, name: str = "A-A'") -> SectionLine:
    """Section whose line runs from hole to hole in the given order."""
    verts, stations, s = [], [], 0.0
    for bid in ids:
        bh = project.borehole(bid)
        if pd.isna(bh.x) or pd.isna(bh.y):
            raise ValueError(f"Borehole {bid} has no X/Y coordinates")
        if verts:
            s += math.hypot(bh.x - verts[-1][0], bh.y - verts[-1][1])
        verts.append((bh.x, bh.y))
        stations.append(Station(bid, s, 0.0))
    if len(stations) < 2:
        raise ValueError("A section needs at least two boreholes")
    return SectionLine(name, verts, stations)


def along_line(project: Project, vertices, buffer: float, name: str = "A-A'") -> SectionLine:
    """Section along a polyline; boreholes within ``buffer`` m are projected onto it."""
    v = np.asarray(vertices, float)
    seg_len = np.hypot(*np.diff(v, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg_len)])
    stations = []
    for bid in project.ids:
        bh = project.borehole(bid)
        if pd.isna(bh.x) or pd.isna(bh.y):
            continue
        p = np.array([bh.x, bh.y])
        best = None
        for k in range(len(v) - 1):
            a, b = v[k], v[k + 1]
            d = b - a
            t = 0.0 if seg_len[k] == 0 else float(np.clip(np.dot(p - a, d) / seg_len[k] ** 2, 0, 1))
            q = a + t * d
            dist = float(np.hypot(*(p - q)))
            side = np.sign(d[0] * (p - a)[1] - d[1] * (p - a)[0]) or 1.0
            if best is None or dist < best[0]:
                best = (dist, cum[k] + t * seg_len[k], side)
        if best and best[0] <= buffer:
            stations.append(Station(bid, best[1], best[0] * best[2]))
    stations.sort(key=lambda st: st.s)
    if len(stations) < 2:
        raise ValueError(f"Fewer than two boreholes lie within {buffer:g} m of the section line")
    return SectionLine(name, [tuple(x) for x in v], stations)


# ---------------------------------------------------------------------------


def contact_edges(polys, tol=1e-6):
    """Edges between polygons of different lithology (or on the panel boundary)."""
    seen: dict = {}
    for code, verts in polys:
        n = len(verts)
        for k in range(n):
            p, q = verts[k], verts[(k + 1) % n]
            key = tuple(sorted((tuple(np.round(p, 6)), tuple(np.round(q, 6)))))
            seen.setdefault(key, []).append(code)
    out = []
    for (p, q), codes in seen.items():
        if abs(p[0] - q[0]) < tol:  # vertical: hole wall or facies boundary
            if len(codes) == 2 and codes[0] != codes[1]:
                out.append((p, q))
            continue
        if len(codes) == 1 or len(set(codes)) > 1:
            out.append((p, q))
    return out


def section_figure(project: Project, line: SectionLine, legend: Legend | None = None,
                   ve: float | None = None, page: str = "A3", title: str = "",
                   datum: str = "elevation", scale: float = 25.0):
    legend = legend or project.legend
    W, H = PAGES.get(page.upper(), PAGES["A3"])
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    m = 12.0
    side_w = 78.0 if page.upper() == "A3" else 62.0
    title_h = 14.0

    def axes_mm(x, y, w, h):
        ax = fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])
        return ax

    # Title bar
    tax = axes_mm(m, m, W - 2 * m, title_h)
    tax.set_xlim(0, W - 2 * m), tax.set_ylim(title_h, 0), tax.set_axis_off()
    tax.add_patch(Rectangle((0, 0), W - 2 * m, title_h, facecolor=ACCENT))
    tax.text(4, title_h / 2, "GEOLOGICAL CROSS-SECTION", color="white", fontsize=10,
             fontweight="bold", va="center")
    tax.text((W - 2 * m) / 2, title_h / 2, line.name, color="white", fontsize=14,
             fontweight="bold", va="center", ha="center")
    if title:
        tax.text(W - 2 * m - 4, title_h / 2, title, color="white", fontsize=8.5, va="center", ha="right")

    # Main section axes (mm box)
    bx, by = m + 16, m + title_h + 10
    bw, bh_ = W - 2 * m - side_w - 40, H - by - m - 22
    ax = axes_mm(bx, by, bw, bh_)

    holes = [(st, project.borehole(st.id)) for st in line.stations]
    unit_sets = [units(b, datum) for _, b in holes]
    zs = [z for us in unit_sets for u in us for z in (u.top, u.bot)]
    if not zs:
        raise ValueError("None of the section boreholes has lithology data")
    zmin, zmax = min(zs), max(zs)
    s0, s1 = 0.0, max(line.length, line.stations[-1].s)
    pad_s = 0.03 * (s1 - s0 or 1)
    pad_z = 0.06 * (zmax - zmin or 1)
    xlim = [s0 - pad_s, s1 + pad_s]
    ylim = [zmin - pad_z, zmax + 2.2 * pad_z]
    # Vertical exaggeration: page mm per metre vertical / horizontal.
    natural = (bh_ / (ylim[1] - ylim[0])) / (bw / (xlim[1] - xlim[0]))
    if ve is None:
        ve = _nice_ve(natural)
    if ve > natural:  # need more horizontal room
        extra = (bw / (bh_ / (ylim[1] - ylim[0]) / ve)) - (xlim[1] - xlim[0])
        xlim = [xlim[0] - extra / 2, xlim[1] + extra / 2]
    else:  # need more vertical room
        extra = (bh_ / (bw / (xlim[1] - xlim[0]) * ve)) - (ylim[1] - ylim[0])
        ylim = [ylim[0] - extra * 0.35, ylim[1] + extra * 0.65]
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_autoscale_on(False)

    # Correlated panels between neighbouring holes
    for k in range(len(holes) - 1):
        (sa, _), (sb, _) = holes[k], holes[k + 1]
        polys = panel(unit_sets[k], unit_sets[k + 1], sa.s, sb.s, scale)
        for code, verts in polys:
            draw_polygon(ax, verts, legend.get(code), edge=False, lw=0.4)
        for p, q in contact_edges(polys):
            ax.plot([p[0], q[0]], [p[1], q[1]], color="#333333", lw=0.5, zorder=4)

    # Ground surface through collars, blank sky above
    tops = [(st.s, us[0].top) for (st, _), us in zip(holes, unit_sets) if us]
    ts, tz = zip(*tops)
    ax.plot(ts, tz, color="#5A3E1B", lw=1.4, zorder=6, solid_capstyle="round")
    # Base of data
    bots = [(st.s, us[-1].bot) for (st, _), us in zip(holes, unit_sets) if us]
    bs, bz = zip(*bots)
    ax.plot(bs, bz, color="#555555", lw=0.6, ls=(0, (4, 2)), zorder=6)

    # Borehole columns
    ux = (xlim[1] - xlim[0]) / bw  # metres per mm horizontally
    half = 1.6 * ux
    for (st, bh), us in zip(holes, unit_sets):
        if us:  # white halo so the hole column stands out from the panels
            ax.add_patch(Rectangle((st.s - 1.6 * half, us[-1].bot), 3.2 * half, us[0].top - us[-1].bot,
                                   facecolor="white", edgecolor="none", zorder=5))
        for u in us:
            draw_interval(ax, st.s - half, st.s + half, u.bot, u.top, legend.get(u.code), edge=False,
                          lw=0.3, z=5)
            ax.plot([st.s - half, st.s + half], [u.bot, u.bot], color=INK, lw=0.5, zorder=9)
        if us:
            ax.add_patch(Rectangle((st.s - half, us[-1].bot), 2 * half, us[0].top - us[-1].bot,
                                   facecolor="none", edgecolor=INK, lw=0.9, zorder=9))
            label = st.id if abs(st.offset) < 1e-6 else f"{st.id}\n({st.offset:+.0f} m)"
            ax.plot([st.s, st.s], [us[0].top, us[0].top + pad_z * 0.6], color=INK, lw=0.6, zorder=7)
            ax.text(st.s, us[0].top + pad_z * 0.7, label, ha="center", va="bottom", fontsize=6.5,
                    fontweight="bold", color=INK, zorder=8, rotation=90 if len(holes) > 14 else 0)
        wl = bh.water_levels.dropna(subset=["depth"])
        if len(wl) and us:
            z = (bh.elevation if (datum == "elevation" and bh.has_elevation) else 0) - wl.iloc[-1]["depth"]
            ax.plot([st.s - 2.5 * half, st.s + 2.5 * half], [z, z], color=WATER, lw=1.0, zorder=8)
    wl_pts = []
    for (st, bh), us in zip(holes, unit_sets):
        wl = bh.water_levels.dropna(subset=["depth"])
        if len(wl) and us:
            base = bh.elevation if (datum == "elevation" and bh.has_elevation) else 0
            wl_pts.append((st.s, base - wl.iloc[-1]["depth"]))
    if len(wl_pts) >= 2:
        ax.plot(*zip(*wl_pts), color=WATER, lw=0.9, ls=(0, (6, 3)), zorder=7.5)

    # Axes cosmetics
    for sp in ax.spines.values():
        sp.set_linewidth(0.8)
    ax.tick_params(labelsize=7, direction="out", length=3, right=True, labelright=True)
    ax.set_ylabel("Elevation (m amsl)" if datum == "elevation" else "Depth below ground (m)", fontsize=8)
    ax.set_xlabel("Distance along section (m)", fontsize=8)
    ax.grid(True, color="#DDDDDD", lw=0.3, zorder=0)
    ax.set_axisbelow(True)
    ax.text(0, 1.01, line.name.split("-")[0].strip() or "A", transform=ax.transAxes, fontsize=12,
            fontweight="bold", ha="left", va="bottom", color=ACCENT)
    end = line.name.split("-")[-1].strip() if "-" in line.name else "A'"
    ax.text(1, 1.01, end, transform=ax.transAxes, fontsize=12, fontweight="bold", ha="right",
            va="bottom", color=ACCENT)
    ax.text(0.99, 0.015, f"Vertical exaggeration ×{ve:g}", transform=ax.transAxes, fontsize=7,
            ha="right", va="bottom", color="#555555", zorder=10,
            bbox=dict(facecolor="white", edgecolor="none", pad=1.5, alpha=0.9))

    # Side panel: location map + legend
    sx = W - m - side_w
    map_h = side_w * 0.85
    _location_map(project, line, axes_mm(sx + 4, by, side_w - 4, map_h))
    used = list(dict.fromkeys(u.code for us in unit_sets for u in us))
    _section_legend(fig, axes_mm, legend, used, sx + 4, by + map_h + 8, side_w - 4, wl=len(wl_pts) > 0)

    fax = axes_mm(m, H - m - 5, W - 2 * m, 5)
    fax.set_axis_off()
    fax.text(0, 0.5, f"LithoLog {__version__} · correlation between boreholes is interpretive "
                     "(units joined by sequence and elevation; unmatched units pinch out half-way)",
             fontsize=6, color="#777777", va="center")
    return fig


def _nice_ve(v):
    """Largest 'round' exaggeration not above v (so the section fits the box)."""
    nice = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 75, 80, 100,
            120, 150, 200, 250, 300, 400, 500, 750, 1000]
    return float(max([n for n in nice if n <= v] or [1]))


def _location_map(project, line, ax):
    b = project.boreholes.dropna(subset=["x", "y"])
    ax.scatter(b["x"], b["y"], s=5, color="#9A9A9A", zorder=2, lw=0)
    v = np.asarray(line.vertices, float)
    ax.plot(v[:, 0], v[:, 1], color="#C0392B", lw=1.2, zorder=3)
    ids = [st.id for st in line.stations]
    sel = b[b["borehole_id"].isin(ids)]
    ax.scatter(sel["x"], sel["y"], s=12, color="#C0392B", zorder=4, lw=0)
    start = line.name.split("-")[0].strip() or "A"
    end = line.name.split("-")[-1].strip() if "-" in line.name else "A'"
    ax.annotate(start, v[0], xytext=(-4, 3), textcoords="offset points", fontsize=8,
                fontweight="bold", color="#C0392B", ha="right")
    ax.annotate(end, v[-1], xytext=(4, 3), textcoords="offset points", fontsize=8,
                fontweight="bold", color="#C0392B")
    if len(ids) <= 12:
        for _, r in sel.iterrows():
            ax.annotate(r["borehole_id"], (r["x"], r["y"]), xytext=(3, -6), textcoords="offset points",
                        fontsize=5, color="#444444")
    ax.set_aspect("equal", adjustable="datalim")
    ax.tick_params(labelsize=5)
    ax.ticklabel_format(useOffset=False, style="plain")
    for lbl in ax.get_xticklabels():
        lbl.set_rotation(30)
    ax.set_title("Location plan", fontsize=7.5, fontweight="bold", loc="left")
    ax.grid(True, color="#EEEEEE", lw=0.3)
    ax.annotate("N", xy=(0.93, 0.95), xytext=(0.93, 0.8), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=0.8), ha="center", fontsize=7,
                fontweight="bold")


def _section_legend(fig, axes_mm, legend, codes, x, y, w, wl=False):
    rows = len(codes) + (1 if wl else 0) + 2
    h = 6 + rows * 6.2
    ax = axes_mm(x, y, w, h)
    ax.set_xlim(0, w), ax.set_ylim(h, 0), ax.set_axis_off()
    ax.text(0, 2.5, "Legend", fontsize=7.5, fontweight="bold", va="center")
    for i, code in enumerate(codes):
        y0 = 6 + i * 6.2
        sub = axes_mm(x, y + y0, 10, 4.6)
        sub.set_xlim(0, 1), sub.set_ylim(4.6, 0), sub.set_axis_off()
        lt = legend.get(code)
        draw_interval(sub, 0, 1, 0, 4.6, lt, lw=0.35)
        ax.text(12, y0 + 2.3, lt.name, fontsize=6.3, va="center")
    y0 = 6 + len(codes) * 6.2
    ax.plot([0, 10], [y0 + 2.3] * 2, color="#5A3E1B", lw=1.4)
    ax.text(12, y0 + 2.3, "Ground surface (collars)", fontsize=6.3, va="center")
    y0 += 6.2
    ax.plot([0, 10], [y0 + 2.3] * 2, color="#555555", lw=0.6, ls=(0, (4, 2)))
    ax.text(12, y0 + 2.3, "Base of drilling", fontsize=6.3, va="center")
    if wl:
        y0 += 6.2
        ax.plot([0, 10], [y0 + 2.3] * 2, color=WATER, lw=0.9, ls=(0, (6, 3)))
        ax.text(12, y0 + 2.3, "Water level", fontsize=6.3, va="center")


def save_section(project, line, path, dpi=200, **kw) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = section_figure(project, line, **kw)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path
