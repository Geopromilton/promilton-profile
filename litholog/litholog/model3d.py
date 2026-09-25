"""3D lithology block (voxel) model, volumes and views.

Each voxel takes the lithology that wins an inverse-distance-weighted vote
among the boreholes that were logged at that level (indicator IDW). The model
is bounded above by the ground surface and below by the base of drilling, both
interpolated from the boreholes, and laterally by the boreholes' convex hull.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

from . import __version__  # noqa: E402
from .correlate import units  # noqa: E402
from .grid import hull_mask, interpolate, make_axes  # noqa: E402
from .patterns import Legend  # noqa: E402
from .project import Project  # noqa: E402

ACCENT = "#1F3A5F"


@dataclass
class BlockModel:
    x: np.ndarray        # cell centres (nx,)
    y: np.ndarray        # (ny,)
    z: np.ndarray        # (nz,) ascending
    cell: float
    dz: float
    lith: np.ndarray     # (nz, ny, nx) int index into ``codes``; -1 = empty
    codes: list
    expected: np.ndarray | None = None  # (ncodes,) probability-weighted voxel counts
    boundary: object = None             # study-area Boundary, if the model was clipped to one
    coverage: float | None = None       # share of the model area inside the boreholes' hull

    @property
    def voxel_volume(self):
        return self.cell * self.cell * self.dz

    def volumes(self, sy: dict | None = None) -> pd.DataFrame:
        sy = sy or {}
        rows = []
        total = int((self.lith >= 0).sum())
        for k, code in enumerate(self.codes):
            n = int((self.lith == k).sum())
            # Volumes come from the indicator probabilities (unbiased for thin units);
            # the hard classification alone under-counts minority lithologies.
            n_exp = float(self.expected[k]) if self.expected is not None else float(n)
            vol = n_exp * self.voxel_volume
            row = {"code": code, "voxels": n, "volume_m3": vol, "volume_mcm": vol / 1e6,
                   "classified_mcm": n * self.voxel_volume / 1e6,
                   "percent": 100.0 * n_exp / total if total else 0.0}
            if code in sy:
                row["specific_yield"] = sy[code]
                row["storage_m3"] = vol * sy[code]
                row["storage_mcm"] = vol * sy[code] / 1e6
            rows.append(row)
        return pd.DataFrame(rows)

    def code_at(self, x, y, z):
        i = int(np.argmin(abs(self.x - x)))
        j = int(np.argmin(abs(self.y - y)))
        k = int(np.argmin(abs(self.z - z)))
        v = self.lith[k, j, i]
        return None if v < 0 else self.codes[v]


def build_model(project: Project, cell: float | None = None, dz: float | None = None,
                power: float = 2.0, target: int = 70, datum: str = "depth",
                max_voxels: int = 3_000_000, boundary=None) -> BlockModel:
    """Indicator-IDW lithology model.

    ``datum="depth"`` (default) compares holes at the same depth below ground, so
    layers follow the land surface (weathering profile, fracture zones in hard
    rock). ``datum="elevation"`` compares them at the same elevation (flat-lying
    or regionally dipping sediments).
    """
    holes = []
    for bh in project:
        us = units(bh)
        if us and pd.notna(bh.x) and pd.notna(bh.y):
            holes.append((bh, us))
    if len(holes) < 2:
        raise ValueError("A block model needs at least two boreholes with coordinates and lithology")
    hx = np.array([b.x for b, _ in holes], float)
    hy = np.array([b.y for b, _ in holes], float)
    tops = np.array([us[0].top for _, us in holes])
    bots = np.array([us[-1].bot for _, us in holes])
    if boundary is not None:  # model covers the study area (and every borehole)
        bx0, bx1, by0, by1 = boundary.bbox
        gx, gy, cell = make_axes(np.r_[hx, bx0, bx1], np.r_[hy, by0, by1], cell, margin=0.01, target=target)
    else:
        gx, gy, cell = make_axes(hx, hy, cell, target=target)
    zlo, zhi = float(bots.min()), float(tops.max())
    if not dz:  # fine enough to keep thin layers: half the 10th-percentile layer thickness
        thick = np.array([u.thick for _, us in holes for u in us])
        dz = float(np.clip(np.percentile(thick, 10) / 2, 0.5, max((zhi - zlo) / 60, 0.5)))
        dz = round(dz, 2)
    gz = np.arange(zlo + dz / 2, zhi, dz)
    if len(gx) * len(gy) * len(gz) > max_voxels:
        raise ValueError("Model too large; increase --cell or --dz")

    codes = list(dict.fromkeys(u.code for _, us in holes for u in us))
    cidx = {c: k for k, c in enumerate(codes)}
    ground = interpolate(hx, hy, tops, gx, gy, "linear")
    base = interpolate(hx, hy, bots, gx, gy, "linear")
    cov = None
    if boundary is not None:
        from .grid import coverage

        inside = boundary.mask(gx, gy)
        cov = coverage(hx, hy, gx, gy, inside)
    elif len(holes) >= 3:
        inside = hull_mask(hx, hy, gx, gy, cell)
    else:
        inside = np.ones(ground.shape, bool)

    X, Y = np.meshgrid(gx, gy)
    d = np.hypot(X.ravel()[:, None] - hx[None], Y.ravel()[:, None] - hy[None])
    W = 1.0 / np.maximum(d, cell * 1e-3) ** power      # (ncell, nholes)

    # Vertical sample positions: elevations, or depths below ground.
    if datum == "depth":
        samples = np.arange(dz / 2, float((tops - bots).max()) + dz, dz)
        hole_pos = lambda u_top, u_bot, top: (top - samples <= u_top) & (top - samples > u_bot)  # noqa: E731
    else:
        samples = gz
        hole_pos = lambda u_top, u_bot, top: (samples <= u_top) & (samples > u_bot)  # noqa: E731
    hz = np.full((len(samples), len(holes)), -1, int)
    for h, (_, us) in enumerate(holes):
        for u in us:
            hz[hole_pos(u.top, u.bot, us[0].top), h] = cidx[u.code]

    votes = np.full((len(samples),) + X.shape, -1, int)
    probs = np.zeros((len(samples),) + X.shape + (len(codes),), np.float32)
    for k in range(len(samples)):
        row = hz[k]
        valid = row >= 0
        if not valid.any():
            continue
        scores = np.zeros((W.shape[0], len(codes)))
        for c in np.unique(row[valid]):
            scores[:, c] = W[:, row == c].sum(1)
        votes[k] = scores.argmax(1).reshape(X.shape)
        probs[k] = (scores / scores.sum(1, keepdims=True)).reshape(X.shape + (len(codes),))

    lith = np.full((len(gz), len(gy), len(gx)), -1, int)
    expected = np.zeros(len(codes))
    for k, z in enumerate(gz):
        keep = inside & (z <= ground) & (z >= base)
        if datum == "depth":
            kd = np.clip(((ground - z) / dz).astype(int), 0, len(samples) - 1)
            layer = np.take_along_axis(votes, kd[None], 0)[0]
            p = np.take_along_axis(probs, kd[None, :, :, None], 0)[0]
        else:
            layer, p = votes[k], probs[k]
        keep &= layer >= 0
        lith[k] = np.where(keep, layer, -1)
        expected += p[keep].sum(0)
    return BlockModel(gx, gy, gz, cell, dz, lith, codes, expected, boundary, cov)


# ---------------------------------------------------------------------------
# Rendering


def _exposed_faces(model: BlockModel, show, ve):
    """Quads for faces of shown voxels that touch a hidden/empty neighbour."""
    L = np.where(show, model.lith, -1)
    nz, ny, nx = L.shape
    h, hz = model.cell / 2, model.dz / 2 * ve
    polys, cols = [], []
    pad = np.pad(L, 1, constant_values=-1)
    filled = L >= 0
    dirs = {
        "+z": (1, 0, 0), "+x": (0, 0, 1), "-x": (0, 0, -1), "+y": (0, 1, 0), "-y": (0, -1, 0),
    }
    for name, (dk, dj, di) in dirs.items():
        nb = pad[1 + dk:1 + dk + nz, 1 + dj:1 + dj + ny, 1 + di:1 + di + nx]
        ks, js, is_ = np.nonzero(filled & (nb < 0))
        for k, j, i in zip(ks, js, is_):
            cx, cy, cz = model.x[i], model.y[j], model.z[k] * ve
            if name == "+z":
                q = [(cx - h, cy - h, cz + hz), (cx + h, cy - h, cz + hz), (cx + h, cy + h, cz + hz),
                     (cx - h, cy + h, cz + hz)]
            elif name in ("+x", "-x"):
                x = cx + (h if name == "+x" else -h)
                q = [(x, cy - h, cz - hz), (x, cy + h, cz - hz), (x, cy + h, cz + hz), (x, cy - h, cz + hz)]
            else:
                y = cy + (h if name == "+y" else -h)
                q = [(cx - h, y, cz - hz), (cx + h, y, cz - hz), (cx + h, y, cz + hz), (cx - h, y, cz + hz)]
            polys.append(q)
            cols.append((L[k, j, i], name))
    return polys, cols


def model_view(model: BlockModel, legend: Legend, path, only=None, cutaway: bool = True,
               ve: float | None = None, azim: float = -60, elev: float = 30, title: str = "",
               sy: dict | None = None, dpi: int = 200) -> Path:
    """3D view of the block model (cut-away), or of selected codes only."""
    from matplotlib.colors import to_rgb

    xr = model.x[-1] - model.x[0]
    yr = model.y[-1] - model.y[0]
    zr = model.z[-1] - model.z[0] or 1
    if ve is None:
        ve = max(1.0, round(0.35 * max(xr, yr) / zr))
    show = model.lith >= 0
    if only:
        idx = [model.codes.index(c) for c in only if c in model.codes]
        show &= np.isin(model.lith, idx)
    elif cutaway:  # remove the quadrant facing the viewer
        X, Y = np.meshgrid(model.x, model.y)
        xm, ym = np.median(model.x), np.median(model.y)
        ax_ = np.cos(np.radians(azim))
        ay_ = np.sin(np.radians(azim))
        quad = ((X - xm) * np.sign(ax_) > 0) & ((Y - ym) * np.sign(ay_) > 0)
        show &= ~quad[None]
    polys, info = _exposed_faces(model, show, ve)
    shade = {"+z": 1.0, "+x": 0.82, "-x": 0.82, "+y": 0.7, "-y": 0.7}
    colors = [tuple(np.clip(np.array(to_rgb(legend.get(model.codes[c]).color)) * shade[f], 0, 1))
              for c, f in info]

    W, H = 420.0, 297.0
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    ax = fig.add_axes([0.0, 0.04, 0.71, 0.86], projection="3d")
    if polys:
        ax.add_collection3d(Poly3DCollection(polys, facecolors=colors, edgecolors="none", linewidths=0))
    if only:  # faint outline of the whole model for context
        full = model.lith >= 0
        top = np.where(full.any(0), model.z[::-1][np.argmax(full[::-1], axis=0)] if full.size else 0, np.nan)
        X, Y = np.meshgrid(model.x, model.y)
        ax.plot_wireframe(X, Y, top * ve, rstride=max(1, len(model.y) // 12),
                          cstride=max(1, len(model.x) // 12), color="#999999", lw=0.3)
    if model.boundary is not None:
        for r in model.boundary.rings:
            ax.plot(np.r_[r[:, 0], r[0, 0]], np.r_[r[:, 1], r[0, 1]], model.z[0] * ve,
                    color="#8B0000", lw=0.9, zorder=0)
    ax.set_xlim(model.x[0], model.x[-1])
    ax.set_ylim(model.y[0], model.y[-1])
    ax.set_zlim(model.z[0] * ve, model.z[-1] * ve)
    ax.set_box_aspect((xr, yr, zr * ve))
    ax.view_init(elev=elev, azim=azim)
    from .maps import nice_levels

    zt = [v for v in nice_levels(model.z[0], model.z[-1], 6) if model.z[0] <= v <= model.z[-1]]
    ax.set_zticks([v * ve for v in zt])
    ax.set_zticklabels([f"{v:g}" for v in zt])
    ax.tick_params(labelsize=5.5, pad=0)
    ax.ticklabel_format(axis="x", useOffset=False, style="plain")
    ax.ticklabel_format(axis="y", useOffset=False, style="plain")
    ax.set_xlabel("Easting / X (m)", fontsize=7, labelpad=6)
    ax.set_ylabel("Northing / Y (m)", fontsize=7, labelpad=6)
    ax.set_zlabel("Elevation (m)", fontsize=7, labelpad=2)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((0.97, 0.97, 0.97, 1))

    head = "LITHOLOGY BLOCK MODEL" if not only else "BLOCK MODEL – " + ", ".join(
        legend.get(c).name for c in only)
    fig.text(0.02, 0.965, head, fontsize=12, fontweight="bold", color=ACCENT, va="center")
    if title:
        fig.text(0.98, 0.965, title, fontsize=9, color=ACCENT, va="center", ha="right")
    fig.text(0.02, 0.935, f"Voxels {model.cell:g} × {model.cell:g} × {model.dz:g} m · "
                          f"{int((model.lith >= 0).sum()):,} filled · vertical exaggeration ×{ve:g}"
                          + (" · cut-away view" if cutaway and not only else ""),
             fontsize=7, color="#555555", va="center")

    # Legend + volume table
    vols = model.volumes(sy)
    if only:
        vols = vols[vols["code"].isin(only)]
    tax = fig.add_axes([0.715, 0.12, 0.26, 0.76])
    tax.set_axis_off()
    tax.set_xlim(0, 1)
    n = len(vols)
    tax.set_ylim(n + 6, 0)
    tax.text(0, 0.5, "Legend and volumes", fontsize=8, fontweight="bold")
    has_sy = "storage_mcm" in vols.columns
    tax.text(0.62, 1.5, "Volume\n(MCM)", fontsize=6, color="#555555", ha="right", va="center")
    tax.text(0.78, 1.5, "%", fontsize=6, color="#555555", ha="right", va="center")
    if has_sy:
        tax.text(1.0, 1.5, "Storage*\n(MCM)", fontsize=6, color="#555555", ha="right", va="center")
    for r, (_, row) in enumerate(vols.iterrows()):
        yy = r + 2.6
        lt = legend.get(row["code"])
        tax.add_patch(plt.Rectangle((0, yy - 0.3), 0.07, 0.6, facecolor=lt.color, edgecolor="#333333", lw=0.4))
        tax.text(0.09, yy, _wrap(lt.name, 24), fontsize=6, va="center")
        tax.text(0.62, yy, f"{row['volume_mcm']:,.1f}", fontsize=6.3, va="center", ha="right")
        tax.text(0.78, yy, f"{row['percent']:.1f}", fontsize=6.3, va="center", ha="right")
        if has_sy and pd.notna(row.get("storage_mcm")):
            tax.text(1.0, yy, f"{row['storage_mcm']:,.2f}", fontsize=6.3, va="center", ha="right",
                     color="#0B3C5D", fontweight="bold")
    if model.boundary is not None:
        area = (model.lith >= 0).any(0).sum() * model.cell ** 2 / 1e6
        note = (f"MCM = million m³. Volumes are within the study-area boundary ({area:,.1f} km² of voxels; "
                f"polygon {model.boundary.area / 1e6:,.1f} km²), from ground to base of drilling.")
        if model.coverage is not None and model.coverage < 0.999:
            note += (f"\n{100 * (1 - model.coverage):.0f} % of the area lies beyond the boreholes; "
                     "values there are extrapolated.")
    else:
        note = "MCM = million m³. Volumes are within the boreholes' convex hull, from ground to base of drilling."
    if has_sy:
        note += "\n*Storage = volume × specific yield given by the user (an estimate, not a measurement)."
    import textwrap

    note = "\n".join(textwrap.fill(par, 78) for par in note.split("\n"))
    tax.text(0, n + 3.4, note, fontsize=5.5, color="#555555", va="top")
    fig.text(0.02, 0.015, f"LithoLog {__version__} · indicator inverse-distance lithology model; "
                          "interpretive between boreholes", fontsize=6, color="#777777")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path


def _wrap(text, n):
    import textwrap

    return "\n".join(textwrap.wrap(text, n)[:2])


def slices_figure(model: BlockModel, legend: Legend, path, levels=None, title: str = "", dpi=200) -> Path:
    """Plan-view lithology maps at several elevations."""
    from matplotlib.colors import ListedColormap

    if levels is None:
        counts = (model.lith >= 0).sum(axis=(1, 2))
        filled = np.nonzero(counts >= 0.1 * counts.max())[0]  # skip nearly empty top/bottom levels
        ks = np.linspace(filled[0], filled[-1], 6).round().astype(int) if len(filled) else []
    else:
        ks = [int(np.argmin(abs(model.z - lv))) for lv in levels]
    cmap = ListedColormap(["#FFFFFF"] + [legend.get(c).color for c in model.codes])
    n = len(ks)
    cols = 3
    rows = int(np.ceil(n / cols)) or 1
    fig, axes = plt.subplots(rows, cols, figsize=(420 / 25.4, 297 / 25.4))
    axes = np.atleast_1d(axes).ravel()
    ext = (model.x[0] - model.cell / 2, model.x[-1] + model.cell / 2,
           model.y[0] - model.cell / 2, model.y[-1] + model.cell / 2)
    for ax, k in zip(axes, ks[::-1]):
        ax.imshow(model.lith[k] + 1, origin="lower", extent=ext, cmap=cmap, vmin=0,
                  vmax=len(model.codes), interpolation="nearest")
        ax.set_title(f"Elevation {model.z[k]:.0f} m", fontsize=8, fontweight="bold")
        if model.boundary is not None:
            ax.add_patch(model.boundary.patch(ax, facecolor="none", edgecolor="#8B0000", lw=0.8))
        ax.tick_params(labelsize=5)
        ax.ticklabel_format(useOffset=False, style="plain")
        ax.set_aspect("equal")
    for ax in axes[n:]:
        ax.set_axis_off()
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=legend.get(c).color, edgecolor="#333333", lw=0.4)
               for c in model.codes]
    fig.legend(handles, [legend.get(c).name for c in model.codes], loc="lower center",
               ncol=min(6, len(model.codes)), fontsize=7, frameon=False)
    fig.suptitle(f"Horizontal slices through the lithology model{(' – ' + title) if title else ''}",
                 fontsize=11, fontweight="bold", color=ACCENT)
    fig.subplots_adjust(left=0.05, right=0.98, top=0.92, bottom=0.1, wspace=0.25, hspace=0.3)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path


def write_vtk(model: BlockModel, path) -> Path:
    """Legacy VTK structured points (opens in ParaView). -1 = empty voxel."""
    path = Path(path)
    nz, ny, nx = model.lith.shape
    with open(path, "w") as f:
        f.write("# vtk DataFile Version 3.0\nLithoLog lithology model; codes: "
                + " ".join(f"{k}={c}" for k, c in enumerate(model.codes)) + "\nASCII\n")
        f.write("DATASET STRUCTURED_POINTS\n")
        f.write(f"DIMENSIONS {nx} {ny} {nz}\n")
        f.write(f"ORIGIN {model.x[0]:.3f} {model.y[0]:.3f} {model.z[0]:.3f}\n")
        f.write(f"SPACING {model.cell:g} {model.cell:g} {model.dz:g}\n")
        f.write(f"POINT_DATA {nx * ny * nz}\nSCALARS lithology int 1\nLOOKUP_TABLE default\n")
        flat = model.lith.reshape(-1)  # x fastest, then y, then z = VTK order
        for s in range(0, len(flat), 30):
            f.write(" ".join(map(str, flat[s:s + 30])) + "\n")
    return path
