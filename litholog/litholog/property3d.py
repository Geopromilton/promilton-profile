"""3D models of measured downhole values (geophysics, hydrochemistry, geotechnics).

Downhole readings (Downhole sheet: Borehole ID, Depth, Parameter, Value) are
interpolated onto the block model's voxel grid by anisotropic inverse-distance
weighting: vertical distances are stretched by ``anisotropy`` (horizontal /
vertical range ratio) because properties vary far faster with depth than
laterally. Resistivity-like parameters can be interpolated in log space.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class PropertyModel:
    parameter: str
    unit: str
    values: np.ndarray    # (nz, ny, nx); NaN outside the model
    model: object         # the BlockModel whose grid/limits are used
    samples: pd.DataFrame  # x, y, z, value used

    def stats(self) -> dict:
        v = self.values[np.isfinite(self.values)]
        return {"min": float(v.min()), "max": float(v.max()), "mean": float(v.mean()),
                "p10": float(np.percentile(v, 10)), "p90": float(np.percentile(v, 90))} if v.size else {}

    def volume_between(self, lo=None, hi=None) -> float:
        """Volume (m³) of voxels whose value lies in [lo, hi]."""
        v = self.values
        sel = np.isfinite(v)
        if lo is not None:
            sel &= v >= lo
        if hi is not None:
            sel &= v <= hi
        return float(sel.sum()) * self.model.voxel_volume


def parameters(project) -> list[str]:
    d = project.downhole.dropna(subset=["depth", "value"])
    return list(dict.fromkeys(d["parameter"].astype(str)))


def build_property(project, model, parameter: str, anisotropy: float | None = None, power: float = 2.0,
                   neighbours: int = 16, log: bool | None = None, datum: str = "depth") -> PropertyModel:
    from scipy.spatial import cKDTree

    d = project.downhole
    d = d[d["parameter"].astype(str) == parameter].dropna(subset=["depth", "value"])
    if d.empty:
        raise ValueError(f"No downhole readings for '{parameter}'")
    unit = next((str(u) for u in d["unit"] if isinstance(u, str) and u.strip()), "")
    rows = []
    for bid, g in d.groupby("borehole_id"):
        bh = project.borehole(bid)
        if pd.isna(bh.x) or pd.isna(bh.y):
            continue
        top = bh.elevation if bh.has_elevation else 0.0
        for dep, val in zip(g["depth"], g["value"]):
            rows.append((bh.x, bh.y, top - dep, dep, val))
    s = pd.DataFrame(rows, columns=["x", "y", "z", "depth", "value"])
    if len(s["x"].unique()) < 2:
        raise ValueError(f"'{parameter}' is measured in fewer than two boreholes")
    if log is None:  # resistivity, conductivity, permeability: spread over orders of magnitude
        log = bool((s["value"] > 0).all() and s["value"].max() / max(s["value"].min(), 1e-12) > 50)
    vals = np.log10(s["value"].to_numpy()) if log else s["value"].to_numpy()

    if anisotropy is None:  # typical: ~ lateral hole spacing / vertical sample spacing, capped
        xy = s[["x", "y"]].drop_duplicates().to_numpy()
        spacing = np.median(cKDTree(xy).query(xy, k=2)[0][:, 1]) if len(xy) > 1 else 1.0
        dzs = s.groupby(["x", "y"])["depth"].apply(lambda v: np.median(np.diff(np.sort(v))) if len(v) > 1 else 1)
        anisotropy = float(np.clip(spacing / max(float(dzs.median()), 0.1) / 10, 5, 200))

    vcoord = s["depth"].to_numpy() if datum == "depth" else s["z"].to_numpy()
    tree = cKDTree(np.column_stack([s["x"], s["y"], vcoord * anisotropy]))
    nz, ny, nx = model.lith.shape
    X, Y = np.meshgrid(model.x, model.y)
    out = np.full((nz, ny, nx), np.nan)
    k = min(neighbours, len(s))
    for iz, z in enumerate(model.z):
        inside = model.lith[iz] >= 0
        if not inside.any():
            continue
        v = (model.ground[inside] - z) if datum == "depth" else np.full(inside.sum(), z)
        q = np.column_stack([X[inside], Y[inside], v * anisotropy])
        dist, idx = tree.query(q, k=k)
        dist, idx = np.atleast_2d(dist), np.atleast_2d(idx)
        w = 1.0 / np.maximum(dist, 1e-6) ** power
        est = (w * vals[idx]).sum(1) / w.sum(1)
        exact = dist[:, 0] < 1e-6
        est[exact] = vals[idx[exact, 0]]
        layer = np.full((ny, nx), np.nan)
        layer[inside] = 10 ** est if log else est
        out[iz] = layer
    return PropertyModel(parameter, unit, out, model, s)


def property_slices(pm: PropertyModel, path, levels=None, title: str = "", cmap: str | None = None,
                    dpi: int = 200) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    m = pm.model
    v = pm.values
    if levels is None:
        counts = np.isfinite(v).sum(axis=(1, 2))
        filled = np.nonzero(counts >= 0.1 * counts.max())[0]
        ks = np.linspace(filled[0], filled[-1], 6).round().astype(int) if len(filled) else []
    else:
        ks = [int(np.argmin(abs(m.z - lv))) for lv in levels]
    finite = v[np.isfinite(v)]
    logn = finite.size and finite.min() > 0 and finite.max() / finite.min() > 50
    norm = LogNorm(finite.min(), finite.max()) if logn else None
    cmap = cmap or ("Spectral_r" if logn else "viridis")
    fig, axes = plt.subplots(2, 3, figsize=(420 / 25.4, 297 / 25.4))
    ext = (m.x[0] - m.cell / 2, m.x[-1] + m.cell / 2, m.y[0] - m.cell / 2, m.y[-1] + m.cell / 2)
    im = None
    for ax, k in zip(axes.ravel(), ks[::-1]):
        im = ax.imshow(v[k], origin="lower", extent=ext, cmap=cmap, norm=norm,
                       vmin=None if norm else finite.min(), vmax=None if norm else finite.max())
        ax.set_title(f"Elevation {m.z[k]:.0f} m", fontsize=8, fontweight="bold")
        ax.tick_params(labelsize=5)
        ax.ticklabel_format(useOffset=False, style="plain")
        if m.boundary is not None:
            ax.add_patch(m.boundary.patch(ax, facecolor="none", edgecolor="#8B0000", lw=0.8))
        sx = pm.samples.drop_duplicates(["x", "y"])
        ax.scatter(sx["x"], sx["y"], s=4, c="k")
    for ax in axes.ravel()[len(ks):]:
        ax.set_axis_off()
    if im is not None:
        cb = fig.colorbar(im, ax=axes, shrink=0.8, pad=0.02)
        cb.set_label(f"{pm.parameter}" + (f" ({pm.unit})" if pm.unit else ""), fontsize=9)
    fig.suptitle(f"{pm.parameter}: horizontal slices through the 3D model{(' – ' + title) if title else ''}",
                 fontsize=11, fontweight="bold", color="#1F3A5F")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path


def property_html(pm: PropertyModel, path, ve: float | None = None, iso=None, title: str = "") -> Path:
    """Interactive 3D (Plotly volume rendering + isosurfaces)."""
    import plotly.graph_objects as go

    m = pm.model
    Z, Y, X = np.meshgrid(m.z, m.y, m.x, indexing="ij")
    v = pm.values
    ok = np.isfinite(v)
    xr, yr, zr = m.x[-1] - m.x[0], m.y[-1] - m.y[0], (m.z[-1] - m.z[0]) or 1
    ve = ve or max(1.0, round(0.3 * max(xr, yr) / zr))
    finite = v[ok]
    logv = finite.min() > 0 and finite.max() / finite.min() > 50
    val = np.log10(np.where(ok, v, np.nan)) if logv else v
    lo, hi = np.nanpercentile(val, 5), np.nanpercentile(val, 95)
    fill = np.where(ok, val, lo - 10 * (hi - lo + 1))
    fig = go.Figure(go.Volume(
        x=X.ravel(), y=Y.ravel(), z=(Z * ve).ravel(), value=fill.ravel(), isomin=lo, isomax=hi,
        opacity=0.18, surface_count=12, colorscale="Spectral_r" if logv else "Viridis",
        colorbar=dict(title=("log10 " if logv else "") + pm.parameter + (f" ({pm.unit})" if pm.unit else ""))))
    fig.update_layout(title=f"{title or pm.parameter} — 3D {pm.parameter} model (VE ×{ve:g})",
                      scene=dict(aspectmode="manual", aspectratio=dict(x=1, y=yr / xr, z=zr * ve / xr),
                                 xaxis_title="Easting", yaxis_title="Northing", zaxis_title="Elevation × VE"),
                      margin=dict(l=0, r=0, t=40, b=0))
    path = Path(path)
    fig.write_html(path, include_plotlyjs=True)
    return path


def write_property_vtk(pm: PropertyModel, path) -> Path:
    m = pm.model
    nz, ny, nx = pm.values.shape
    path = Path(path)
    with open(path, "w") as f:
        f.write(f"# vtk DataFile Version 3.0\nLithoLog property model: {pm.parameter}\nASCII\n")
        f.write("DATASET STRUCTURED_POINTS\n")
        f.write(f"DIMENSIONS {nx} {ny} {nz}\nORIGIN {m.x[0]:.3f} {m.y[0]:.3f} {m.z[0]:.3f}\n")
        f.write(f"SPACING {m.cell:g} {m.cell:g} {m.dz:g}\n")
        name = "".join(ch if ch.isalnum() else "_" for ch in pm.parameter) or "value"
        f.write(f"POINT_DATA {nx * ny * nz}\nSCALARS {name} float 1\nLOOKUP_TABLE default\n")
        flat = np.nan_to_num(pm.values.reshape(-1), nan=-9999.0)
        for s in range(0, len(flat), 20):
            f.write(" ".join(f"{v:.4g}" for v in flat[s:s + 20]) + "\n")
    return path
