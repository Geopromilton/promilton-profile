"""Contour maps of gridded borehole attributes (A3/A4 landscape)."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from . import __version__  # noqa: E402
from .grid import Grid, attribute_label  # noqa: E402

ACCENT = "#1F3A5F"
INK = "#1E1E1E"
PAGES = {"A3": (420.0, 297.0), "A4": (297.0, 210.0)}
CMAPS = {"ground": "terrain", "top": "viridis", "base": "viridis", "depth": "YlOrBr",
         "thickness": "Blues", "water": "GnBu_r", "dtw": "YlOrBr", "total_depth": "Greys"}


def nice_levels(lo, hi, target=12):
    span = hi - lo
    if span <= 0 or not np.isfinite(span):
        return np.array([lo - 0.5, lo + 0.5])
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    step = min(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    return np.arange(math.floor(lo / step) * step, hi + step, step)


def map_figure(grid: Grid, vals: pd.DataFrame, attr: str, legend=None, method: str = "idw",
               title: str = "", page: str = "A3", arrows: bool | None = None, all_xy=None):
    W, H = PAGES.get(page.upper(), PAGES["A3"])
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    m, title_h, side_w = 12.0, 14.0, 70.0
    kind = attr.partition(":")[0]
    name, unit = attribute_label(attr, legend)

    def axes_mm(x, y, w, h):
        return fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])

    tax = axes_mm(m, m, W - 2 * m, title_h)
    tax.set_xlim(0, W - 2 * m), tax.set_ylim(title_h, 0), tax.set_axis_off()
    tax.add_patch(Rectangle((0, 0), W - 2 * m, title_h, facecolor=ACCENT))
    tax.text(4, title_h / 2, "CONTOUR MAP", color="white", fontsize=10, fontweight="bold", va="center")
    tax.text((W - 2 * m) / 2, title_h / 2, f"{name} ({unit})", color="white", fontsize=13,
             fontweight="bold", va="center", ha="center")
    if title:
        tax.text(W - 2 * m - 4, title_h / 2, title, color="white", fontsize=8.5, va="center", ha="right")

    by = m + title_h + 6
    bw, bh = W - 2 * m - side_w - 20, H - by - m - 14
    ax = axes_mm(m + 14, by, bw, bh)
    X, Y = grid.mesh()
    Z = np.ma.masked_invalid(grid.z)
    good = vals.dropna(subset=["value"])
    lo, hi = float(np.nanmin(grid.z)), float(np.nanmax(grid.z))
    levels = nice_levels(lo, hi)
    cmap = plt.get_cmap(CMAPS.get(kind, "viridis"))
    cf = ax.contourf(X, Y, Z, levels=levels, cmap=cmap, extend="neither", zorder=1)
    cs = ax.contour(X, Y, Z, levels=levels, colors="#333333", linewidths=0.4, zorder=2)
    major = levels[::2] if len(levels) > 8 else levels
    ax.clabel(cs, levels=[lv for lv in cs.levels if np.isclose(major, lv).any()], fontsize=6,
              fmt=lambda v: f"{v:g}", inline_spacing=2)

    quiver = None
    if arrows is None:
        arrows = kind == "water"
    if arrows:  # groundwater flow: down the hydraulic gradient
        gy_, gx_ = np.gradient(grid.z, grid.cell)
        step = max(1, len(grid.x) // 18)
        sl = (slice(None, None, step), slice(None, None, step))
        u, v = -gx_[sl], -gy_[sl]
        mag = np.hypot(u, v)
        with np.errstate(invalid="ignore", divide="ignore"):
            u, v = u / mag, v / mag
        quiver = ax.quiver(X[sl], Y[sl], u, v, color="#0B3C5D", scale=30, width=0.0022, headwidth=4,
                           zorder=3)

    # Boreholes: data points labelled with values; holes without a value as open circles
    if all_xy is not None:
        ax.scatter(all_xy["x"], all_xy["y"], s=10, facecolors="none", edgecolors="#555555", lw=0.6, zorder=4)
    ax.scatter(good["x"], good["y"], s=11, color=INK, zorder=5, lw=0)
    fs = 5.5 if len(good) <= 80 else 4.5
    for _, r in good.iterrows():
        ax.annotate(f"{r['value']:.1f}", (r["x"], r["y"]), xytext=(2.5, 2.5), textcoords="offset points",
                    fontsize=fs, color=INK, zorder=6,
                    bbox=dict(facecolor="white", edgecolor="none", pad=0.3, alpha=0.7))
    # Smooth map edge: clip the contours to the convex hull of the data boreholes.
    from .grid import _nearly_collinear

    if grid.boundary is not None:  # clip to the study-area boundary
        for artist in (cf, cs, quiver):
            if artist is not None:
                artist.set_clip_path(grid.boundary.patch(ax))
        ax.add_patch(grid.boundary.patch(ax, facecolor="none", edgecolor="#8B0000", lw=1.1, zorder=3.5))
    elif len(good) >= 3 and np.isnan(grid.z).any() and not _nearly_collinear(good["x"], good["y"]):
        from matplotlib.patches import Polygon as MplPolygon
        from scipy.spatial import ConvexHull

        pts = good[["x", "y"]].to_numpy(float)
        hull = pts[ConvexHull(pts).vertices]
        clip = MplPolygon(hull, closed=True, transform=ax.transData)
        for artist in (cf, cs, quiver):
            if artist is not None:
                artist.set_clip_path(clip)
        ax.add_patch(MplPolygon(hull, closed=True, facecolor="none", edgecolor="#555555",
                                lw=0.6, ls=(0, (3, 2)), zorder=3))
    x0, x1, y0, y1 = grid.extent
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal", adjustable="box")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.tick_params(labelsize=6.5)
    ax.set_xlabel("Easting / X (m)", fontsize=8)
    ax.set_ylabel("Northing / Y (m)", fontsize=8)
    ax.grid(True, color="#FFFFFF", lw=0.3, alpha=0.6, zorder=2.5)
    _north_arrow(ax)
    _scale_bar(ax, x1 - x0)

    # Side panel: colour bar + summary
    sx = W - m - side_w
    cax = axes_mm(sx + 6, by + 4, 6, bh * 0.55)
    cb = fig.colorbar(cf, cax=cax)
    cb.ax.tick_params(labelsize=6.5)
    cb.set_label(f"{name} ({unit})", fontsize=7.5)
    if kind in ("depth", "dtw"):
        cax.invert_yaxis()

    info = axes_mm(sx + 2, by + bh * 0.62, side_w - 2, bh * 0.38)
    info.set_axis_off()
    info.set_xlim(0, 1), info.set_ylim(1, 0)
    n_all = len(vals)
    n_ok = len(good)
    lines = [
        ("Boreholes used", f"{n_ok} of {n_all}"),
        ("Minimum", f"{good['value'].min():.2f} {unit}"),
        ("Maximum", f"{good['value'].max():.2f} {unit}"),
        ("Mean", f"{good['value'].mean():.2f} {unit}"),
        ("Gridding", {"idw": "Inverse distance (power 2)", "linear": "Linear (TIN)",
                      "kriging": "Ordinary kriging (spherical)"}.get(method, method)),
        ("Cell size", f"{grid.cell:g} m"),
        ("Contour interval", f"{levels[1] - levels[0]:g} {unit}"),
    ]
    if grid.boundary is not None:
        lines.append(("Study area", f"{grid.boundary.area / 1e6:,.1f} km²"))
        if grid.coverage is not None:
            lines.append(("Beyond borehole cover", f"{100 * (1 - grid.coverage):.0f} % (extrapolated)"))
    if kind == "thickness":  # isopach volume within the mapped area
        vol = float(np.nansum(np.where(grid.valid, grid.z, np.nan))) * grid.cell ** 2
        lines.append(("Volume (isopach)", f"{vol / 1e6:,.1f} MCM"))
    info.text(0, 0.02, "Summary", fontsize=8, fontweight="bold", va="top")
    for i, (k, v) in enumerate(lines):
        yy = 0.12 + i * 0.075
        info.text(0, yy, k, fontsize=6.5, color="#555555", va="top")
        info.text(0.48, yy, v, fontsize=6.5, color=INK, va="top")
    note = "Arrows: groundwater flow direction (down gradient)" if arrows else ""
    if n_ok < n_all:
        note += ("\n" if note else "") + "Open circles: boreholes without this value"
    if grid.boundary is not None:
        note += ("\n" if note else "") + f"Red line: study-area boundary ({grid.boundary.name})"
    info.text(0, 0.15 + len(lines) * 0.075, note, fontsize=6, color="#555555", va="top")

    fax = axes_mm(m, H - m - 5, W - 2 * m, 5)
    fax.set_axis_off()
    limit = ("map clipped to the study-area boundary" if grid.boundary is not None
             else "map limited to the area enclosed by the boreholes")
    fax.text(0, 0.5, f"LithoLog {__version__} · interpolated surface; reliability decreases away from "
                     f"boreholes · {limit}", fontsize=6,
             color="#777777", va="center")
    return fig


def _north_arrow(ax):
    ax.annotate("N", xy=(0.965, 0.96), xytext=(0.965, 0.87), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.0), ha="center", va="center",
                fontsize=9, fontweight="bold", zorder=10)


def _scale_bar(ax, width_m):
    raw = width_m / 5
    mag = 10 ** math.floor(math.log10(raw))
    length = max(m * mag for m in (1, 2, 5) if m * mag <= raw)
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    bx, by = x0 + 0.03 * (x1 - x0), y0 + 0.04 * (y1 - y0)
    h = 0.008 * (y1 - y0)
    for k in range(4):
        ax.add_patch(Rectangle((bx + k * length / 4, by), length / 4, h,
                               facecolor=INK if k % 2 == 0 else "white", edgecolor=INK, lw=0.6, zorder=10))
    label = f"{length / 1000:g} km" if length >= 1000 else f"{length:g} m"
    ax.text(bx + length / 2, by + 2.2 * h, label, ha="center", va="bottom", fontsize=6.5, zorder=10,
            bbox=dict(facecolor="white", edgecolor="none", pad=0.5, alpha=0.8))


def save_map(grid, vals, attr, path, dpi=200, **kw) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = map_figure(grid, vals, attr, **kw)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path
