"""Smooth 3D lithology solids (like GMS solids) with standard views.

Each lithology becomes a closed, smooth triangulated solid: the zero surface
(marching cubes) of a field that is positive where that lithology wins the
smoothed borehole vote *and* the point lies below ground, above the base of
drilling and inside the study area. Because the ground, base and lateral
limits enter as signed distances, the top follows the real ground surface
instead of voxel steps.

Rendered with Plotly (WebGL: real depth buffer and lighting). Output: an
interactive HTML file you can rotate, and PNG views (top, front, back, left,
right, oblique) that need Chrome/Chromium for export.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .model3d import BlockModel
from .patterns import Legend

# Camera presets. Engineering views are orthographic; obliques are perspective.
VIEWS = {
    "oblique_sw": dict(eye=dict(x=-1.05, y=-1.2, z=0.75), ortho=False, title="Oblique from south-west"),
    "oblique_se": dict(eye=dict(x=1.2, y=-1.05, z=0.75), ortho=False, title="Oblique from south-east"),
    "oblique_ne": dict(eye=dict(x=1.05, y=1.2, z=0.75), ortho=False, title="Oblique from north-east"),
    "oblique_nw": dict(eye=dict(x=-1.2, y=1.05, z=0.75), ortho=False, title="Oblique from north-west"),
    "top": dict(eye=dict(x=0, y=-0.0001, z=2.0), up=dict(x=0, y=1, z=0), ortho=True, title="Top (plan)",
                hide="z"),
    "front": dict(eye=dict(x=0, y=-2.0, z=0.0), ortho=True, title="Front (looking north)", hide="y"),
    "back": dict(eye=dict(x=0, y=2.0, z=0.0), ortho=True, title="Back (looking south)", hide="y"),
    "left": dict(eye=dict(x=-2.0, y=0, z=0.0), ortho=True, title="Left (looking east)", hide="x"),
    "right": dict(eye=dict(x=2.0, y=0, z=0.0), ortho=True, title="Right (looking west)", hide="x"),
}
DEFAULT_VIEWS = ["oblique_sw", "oblique_ne", "top", "front", "back", "left", "right"]


@dataclass
class Solid:
    code: str
    verts: np.ndarray  # (n, 3) x, y, z in model units (z unexaggerated)
    faces: np.ndarray  # (m, 3) vertex indices


def _signed_lateral(inside: np.ndarray) -> np.ndarray:
    """Signed distance (cells) to the edge of the model area: + inside, - outside."""
    from scipy.ndimage import distance_transform_edt

    return np.where(inside, distance_transform_edt(inside) - 0.5, -(distance_transform_edt(~inside) - 0.5))


def build_solids(model: BlockModel, smooth: float = 1.0, cutaway: str | None = None,
                 only=None) -> list[Solid]:
    """Smooth closed solids per lithology.

    ``smooth``: Gaussian smoothing of the vote proportions (voxels).
    ``cutaway``: remove a quadrant to show the interior: "sw", "se", "ne" or "nw".
    ``only``: restrict to these codes.
    """
    from scipy.ndimage import gaussian_filter
    from skimage.measure import marching_cubes

    if getattr(model, "kind", "") == "horizon":  # exact solids from the horizon surfaces
        from .horizons import horizon_solids

        return horizon_solids(model, cutaway, only)
    if model.prob is None:
        raise ValueError("Rebuild the model with this version of LithoLog (probabilities missing)")
    nz, ny, nx, nc = model.prob.shape
    Z = model.z[:, None, None]
    geo = np.minimum((model.ground[None] - Z) / model.dz, (Z - model.base[None]) / model.dz)
    geo = np.minimum(geo, _signed_lateral(model.inside)[None])
    if cutaway:
        X, Y = np.meshgrid(model.x, model.y)
        xm, ym = np.median(model.x), np.median(model.y)
        sx = (X - xm) / model.cell if "w" in cutaway else (xm - X) / model.cell
        sy = (Y - ym) / model.cell if "s" in cutaway else (ym - Y) / model.cell
        geo = np.minimum(geo, np.maximum(sx, sy)[None])  # negative inside the removed quadrant
    geo = np.nan_to_num(geo, nan=-1.0)

    P = model.prob.astype(np.float32)
    if smooth > 0:
        P = np.stack([gaussian_filter(P[..., c], sigma=(smooth * 1.5, smooth, smooth)) for c in range(nc)], -1)
    solids = []
    for c, code in enumerate(model.codes):
        if only and code not in only:
            continue
        if only:
            # Unit shown on its own: threshold its vote share so the drawn solid has the
            # same volume as reported (probability-weighted), instead of only the voxels
            # where it wins outright (which under-draws thin units).
            t = _volume_threshold(P[..., c], geo > 0, model.expected[c] if model.expected is not None else None)
            field = np.minimum(2.0 * (P[..., c] - t), geo)
        else:
            others = np.delete(P, c, axis=-1).max(-1) if nc > 1 else np.zeros(P.shape[:3])
            field = np.minimum(2.0 * (P[..., c] - others), geo)
        if field.max() <= 0:
            continue
        field = np.pad(field, 1, constant_values=-1.0)  # close the surfaces at the grid edge
        verts, faces, _, _ = marching_cubes(field, level=0.0)
        k, j, i = verts[:, 0] - 1, verts[:, 1] - 1, verts[:, 2] - 1
        xyz = np.column_stack([
            model.x[0] + i * model.cell,
            model.y[0] + j * model.cell,
            model.z[0] + k * model.dz,
        ])
        solids.append(Solid(code, xyz, faces.astype(np.int32)))
    return solids


def _volume_threshold(p, inside, target_voxels):
    """Vote-share threshold whose enclosed voxel count matches ``target_voxels``."""
    vals = np.sort(p[inside])[::-1]
    if target_voxels is None or not len(vals):
        return 0.5
    n = int(np.clip(round(target_voxels), 1, len(vals)))
    return float(vals[n - 1])


def solid_figure(model: BlockModel, solids, legend: Legend, ve: float | None = None,
                 title: str = "", boreholes: bool = True, sy: dict | None = None,
                 opacity: float = 1.0, labels: bool = True, cutaway: str | None = None):
    import plotly.graph_objects as go

    xr = model.x[-1] - model.x[0]
    yr = model.y[-1] - model.y[0]
    zr = (model.z[-1] - model.z[0]) or 1.0
    if ve is None:
        ve = max(1.0, round(0.3 * max(xr, yr) / zr))
    vols = model.volumes(sy).set_index("code")
    fig = go.Figure()
    for s in solids:
        lt = legend.get(s.code)
        v = vols.loc[s.code, "volume_mcm"] if s.code in vols.index else None
        label = lt.name + (f" · {v:,.0f} MCM" if v is not None else "")
        fig.add_trace(go.Mesh3d(
            x=s.verts[:, 0], y=s.verts[:, 1], z=s.verts[:, 2] * ve,
            i=s.faces[:, 0], j=s.faces[:, 1], k=s.faces[:, 2],
            color=lt.color, opacity=opacity, name=label, showlegend=True, flatshading=False,
            lighting=dict(ambient=0.72, diffuse=0.55, specular=0.05, roughness=0.9, fresnel=0.05),
            lightposition=dict(x=-3000, y=-6000, z=10000),
            hovertemplate=f"{lt.name}<br>x %{{x:.0f}}<br>y %{{y:.0f}}<extra></extra>",
        ))
    holes = list(model.holes or [])
    if cutaway:  # no sticks floating in the removed quadrant
        xm, ym = np.median(model.x), np.median(model.y)
        holes = [h for h in holes if not ((h[1] < xm if "w" in cutaway else h[1] > xm)
                                          and (h[2] < ym if "s" in cutaway else h[2] > ym))]
    if boreholes and holes:
        for bid, x, y, us in holes:
            fig.add_trace(go.Scatter3d(
                x=[x, x], y=[y, y], z=[us[0].top * ve + zr * ve * 0.04, us[-1].bot * ve],
                mode="lines", line=dict(color="#111111", width=3), showlegend=False,
                hovertemplate=f"{bid}<extra></extra>"))
        if labels:
            fig.add_trace(go.Scatter3d(
                x=[h[1] for h in holes], y=[h[2] for h in holes],
                z=[h[3][0].top * ve + zr * ve * 0.06 for h in holes],
                mode="text", text=[h[0] for h in holes], textfont=dict(size=9, color="#111111"),
                showlegend=False, hoverinfo="skip"))
    if model.boundary is not None:
        for r in model.boundary.rings:
            fig.add_trace(go.Scatter3d(
                x=np.r_[r[:, 0], r[0, 0]], y=np.r_[r[:, 1], r[0, 1]],
                z=np.full(len(r) + 1, model.z[0] * ve), mode="lines",
                line=dict(color="#8B0000", width=3), name="Study-area boundary", showlegend=True,
                hoverinfo="skip"))
    zt = _nice_ticks(model.z[0], model.z[-1])
    fig.update_layout(
        title=dict(text=f"<b>{title or 'Lithology model'}</b>  <span style='font-size:12px;color:#555'>"
                        f"vertical exaggeration ×{ve:g}</span>", x=0.01, font=dict(color="#1F3A5F", size=18)),
        scene=dict(
            aspectmode="manual",
            aspectratio=dict(x=1, y=yr / xr, z=zr * ve / xr),
            xaxis=dict(title="Easting / X (m)", tickformat="d", backgroundcolor="#F4F4F4"),
            yaxis=dict(title="Northing / Y (m)", tickformat="d", backgroundcolor="#EEEEEE"),
            zaxis=dict(title="Elevation (m)", tickvals=[v * ve for v in zt], ticktext=[f"{v:g}" for v in zt],
                       backgroundcolor="#F8F8F8"),
        ),
        legend=dict(x=0.99, xanchor="right", y=0.98, bgcolor="rgba(255,255,255,0.85)", font=dict(size=12)),
        margin=dict(l=0, r=0, t=50, b=0), paper_bgcolor="white",
    )
    return fig, ve


def _nice_ticks(lo, hi, n=6):
    from .maps import nice_levels

    return [v for v in nice_levels(lo, hi, n) if lo <= v <= hi]


def set_view(fig, name: str):
    v = VIEWS[name]
    cam = dict(eye=v["eye"], up=v.get("up", dict(x=0, y=0, z=1)), center=dict(x=0, y=0, z=0),
               projection=dict(type="orthographic" if v["ortho"] else "perspective"))
    fig.update_layout(scene_camera=cam)
    if v["ortho"]:
        # Plotly's orthographic zoom ignores camera distance: scale the scene box so the
        # visible face fills the frame (plan: x-y; front/back: x; left/right: y).
        ar = fig.layout.scene.aspectratio
        face = {"top": max(ar.x, ar.y), "front": ar.x, "back": ar.x, "left": ar.y, "right": ar.y}[name]
        k = (1.45 if name == "top" else 1.75) / max(face, 1e-6)
        fig.update_layout(scene_aspectratio=dict(x=ar.x * k, y=ar.y * k, z=ar.z * k),
                          scene_domain=dict(x=[0, 0.8], y=[0, 1]))
    if v.get("hide"):  # the axis pointing at the viewer only clutters the view
        fig.update_layout({f"scene_{v['hide']}axis": dict(showticklabels=False, title="", showgrid=False)})
    return fig


def _ensure_chrome():
    """Point Kaleido at a local Chrome/Chromium if it cannot find one itself."""
    if os.environ.get("BROWSER_PATH"):
        return
    for cand in ("/opt/pw-browsers/chromium-1194/chrome-linux/chrome",):
        if Path(cand).exists():
            os.environ["BROWSER_PATH"] = cand
            return
    import glob

    hits = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    if hits:
        os.environ["BROWSER_PATH"] = hits[-1]


def export_solids(model: BlockModel, legend: Legend, out, views=None, cutaway: str | None = "sw",
                  smooth: float = 1.0, ve: float | None = None, title: str = "", sy: dict | None = None,
                  only=None, width: int = 1600, height: int = 1100, sheet: bool = True):
    """Write model_3d.html (interactive) plus PNG views and a one-page view sheet (PDF)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stem = "solid" + ("_" + "_".join(only) if only else "")
    solids = build_solids(model, smooth, None if only else cutaway, only)
    full = build_solids(model, smooth, None, only) if (cutaway and not only) else solids
    fig, ve = solid_figure(model, full, legend, ve, title, sy=sy)
    html = out / f"{stem}_3d.html"
    fig.write_html(html, include_plotlyjs=True, full_html=True,
                   config={"displaylogo": False, "toImageButtonOptions": {"format": "png", "scale": 2}})
    files = [html]
    views = views or DEFAULT_VIEWS
    _ensure_chrome()
    pngs = []
    try:
        for name in views:
            use = solids if name.startswith("oblique") else full
            f, _ = solid_figure(model, use, legend, ve, f"{title} – {VIEWS[name]['title']}"
                                if title else VIEWS[name]["title"], sy=sy,
                                labels=len(model.holes or []) <= 25 and name.startswith("oblique"),
                                cutaway=cutaway if (use is solids and not only) else None)
            set_view(f, name)
            p = out / f"{stem}_{name}.png"
            f.write_image(p, width=width, height=height, scale=1)
            pngs.append((name, p))
            files.append(p)
    except Exception as e:  # noqa: BLE001 - no Chrome: still deliver the HTML
        print(f"  (PNG views skipped: {e}. Install Chrome, or run `plotly_get_chrome`.)")
    if sheet and pngs:
        files.append(_view_sheet(pngs, out / f"{stem}_views.pdf", title))
    return files


def _view_sheet(pngs, path, title):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(pngs)
    cols = 3 if n > 4 else 2
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(420 / 25.4, 297 / 25.4))
    axes = np.atleast_1d(axes).ravel()
    for ax, (name, p) in zip(axes, pngs):
        ax.imshow(plt.imread(p))
        ax.set_title(VIEWS[name]["title"], fontsize=9, fontweight="bold", color="#1F3A5F")
        ax.set_axis_off()
    for ax in axes[n:]:
        ax.set_axis_off()
    fig.suptitle(f"3D lithology model – standard views{(' – ' + title) if title else ''}",
                 fontsize=12, fontweight="bold", color="#1F3A5F")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.93, bottom=0.01, wspace=0.02, hspace=0.08)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path
