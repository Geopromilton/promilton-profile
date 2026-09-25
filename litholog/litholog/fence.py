"""3D fence diagrams: correlated panels between boreholes, viewed in perspective."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection  # noqa: E402

from . import __version__  # noqa: E402
from .correlate import panel, units  # noqa: E402
from .patterns import Legend  # noqa: E402
from .project import Project  # noqa: E402

ACCENT = "#1F3A5F"


def network_edges(project: Project, ids=None, method: str = "mst", max_factor: float = 2.5):
    """Pairs of borehole IDs to join with fence panels.

    ``mst``: minimum spanning tree (every hole connected, no crossings, least clutter).
    ``delaunay``: Delaunay triangulation, dropping edges longer than
    ``max_factor`` x the median edge (removes long hull edges).
    """
    b = project.boreholes.dropna(subset=["x", "y"])
    if ids:
        b = b[b["borehole_id"].isin(ids)]
    names = list(b["borehole_id"])
    pts = b[["x", "y"]].to_numpy(float)
    if len(pts) < 2:
        raise ValueError("A fence diagram needs at least two boreholes with coordinates")
    if len(pts) == 2:
        return [(names[0], names[1])]
    from scipy.spatial import Delaunay

    tri = Delaunay(pts)
    edges = set()
    for simplex in tri.simplices:
        for k in range(3):
            i, j = sorted((simplex[k], simplex[(k + 1) % 3]))
            edges.add((i, j))
    lengths = {e: float(np.hypot(*(pts[e[0]] - pts[e[1]]))) for e in edges}
    if method == "delaunay":
        cut = np.median(list(lengths.values())) * max_factor
        keep = [e for e in edges if lengths[e] <= cut]
    else:  # Kruskal minimum spanning tree over the Delaunay edges
        parent = list(range(len(pts)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        keep = []
        for e in sorted(edges, key=lengths.get):
            ra, rb = find(e[0]), find(e[1])
            if ra != rb:
                parent[ra] = rb
                keep.append(e)
    return [(names[i], names[j]) for i, j in sorted(keep)]


def fence_figure(project: Project, edges, legend: Legend | None = None, ve: float | None = None,
                 azim: float = -60, elev: float = 28, title: str = "", datum: str = "elevation",
                 scale: float = 25.0, labels: bool = True):
    legend = legend or project.legend
    W, H = 420.0, 297.0
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    ax = fig.add_axes([0.0, 0.04, 0.8, 0.86], projection="3d")

    ids = list(dict.fromkeys([i for e in edges for i in e]))
    holes = {i: project.borehole(i) for i in ids}
    us = {i: units(holes[i], datum) for i in ids}

    polys, colors = [], []
    for a, b in edges:
        A, B = holes[a], holes[b]
        dx, dy = B.x - A.x, B.y - A.y
        L = math.hypot(dx, dy)
        if L == 0 or not us[a] or not us[b]:
            continue
        for code, verts in panel(us[a], us[b], 0.0, L, scale):
            polys.append([(A.x + s / L * dx, A.y + s / L * dy, z) for s, z in verts])
            colors.append(legend.get(code).color)
    if not polys:
        raise ValueError("No panels to draw (check coordinates and lithology)")
    coll = Poly3DCollection(polys, facecolors=colors, edgecolors=colors, linewidths=0.15, alpha=1.0)
    ax.add_collection3d(coll)

    # Borehole sticks and labels
    sticks, stick_colors = [], []
    for i in ids:
        bh = holes[i]
        for u in us[i]:
            sticks.append([(bh.x, bh.y, u.top), (bh.x, bh.y, u.bot)])
            stick_colors.append("#111111")
    ax.add_collection3d(Line3DCollection(sticks, colors=stick_colors, linewidths=1.2))
    if labels:
        for i in ids:
            bh = holes[i]
            if us[i]:
                ax.text(bh.x, bh.y, us[i][0].top, f" {i}", fontsize=5.5, color="#111111", zorder=10)

    xs = [holes[i].x for i in ids]
    ys = [holes[i].y for i in ids]
    zs = [z for i in ids for u in us[i] for z in (u.top, u.bot)]
    ax.set_xlim(min(xs), max(xs))
    ax.set_ylim(min(ys), max(ys))
    ax.set_zlim(min(zs), max(zs))
    xr, yr, zr = max(xs) - min(xs) or 1, max(ys) - min(ys) or 1, max(zs) - min(zs) or 1
    if ve is None:  # make the vertical ~ 35 % of the larger horizontal extent
        ve = max(1.0, round(0.35 * max(xr, yr) / zr))
    ax.set_box_aspect((xr, yr, zr * ve))
    ax.view_init(elev=elev, azim=azim)
    ax.tick_params(labelsize=5.5, pad=0)
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.set_xlabel("Easting / X (m)", fontsize=7, labelpad=6)
    ax.set_ylabel("Northing / Y (m)", fontsize=7, labelpad=6)
    ax.set_zlabel("Elevation (m)", fontsize=7, labelpad=2)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((0.97, 0.97, 0.97, 1))
        axis._axinfo["grid"]["color"] = (0.85, 0.85, 0.85, 1)

    fig.text(0.02, 0.965, "FENCE DIAGRAM", fontsize=12, fontweight="bold", color=ACCENT, va="center")
    if title:
        fig.text(0.98, 0.965, title, fontsize=9, color=ACCENT, va="center", ha="right")
    fig.text(0.02, 0.935, f"{len(edges)} panels · {len(ids)} boreholes · vertical exaggeration ×{ve:g} · "
                          f"view azimuth {azim:g}°, elevation {elev:g}°",
             fontsize=7, color="#555555", va="center")

    # Legend (colour swatches; 3D panels are plain colour for legibility)
    used = list(dict.fromkeys(u.code for i in ids for u in us[i]))
    row = 0.028  # figure fraction per legend row
    lax = fig.add_axes([0.81, 0.85 - row * (len(used) + 1), 0.18, row * (len(used) + 1)])
    lax.set_axis_off()
    lax.set_xlim(0, 1)
    lax.set_ylim(len(used) + 1, 0)
    lax.text(0, 0.5, "Legend", fontsize=8, fontweight="bold", va="center")
    for k, code in enumerate(used):
        lt = legend.get(code)
        lax.add_patch(plt.Rectangle((0, k + 1.15), 0.12, 0.7, facecolor=lt.color, edgecolor="#333333", lw=0.5))
        lax.text(0.16, k + 1.5, lt.name, fontsize=6.5, va="center")
    fig.text(0.02, 0.015, f"LithoLog {__version__} · panels are interpretive correlations between "
                          "neighbouring boreholes", fontsize=6, color="#777777")
    return fig


def save_fence(project, edges, path, dpi=200, views=None, **kw) -> list[Path]:
    """Save one fence view, or several (``views=[azim, ...]``) as <name>_az<N>.<ext>."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = []
    azim = kw.pop("azim", -60)
    for az in (views or [azim]):
        p = path if not views else path.with_name(f"{path.stem}_az{int(az)}{path.suffix}")
        fig = fence_figure(project, edges, azim=az, **kw)
        fig.savefig(p, dpi=dpi)
        plt.close(fig)
        out.append(p)
    return out
