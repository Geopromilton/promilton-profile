"""Fracture analysis: rose diagram, stereonet (poles + density), frequency and water strikes.

Fractures sheet: Borehole ID, Depth, Dip (0-90°), Dip direction (0-360°),
optional Aperture and Yield (water strike). Stereonets are equal-area (Schmidt),
lower hemisphere; strikes follow the right-hand rule (strike = dip direction − 90°).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

NAVY = "#1F3A5F"


def table(project) -> pd.DataFrame:
    f = project.fractures.dropna(subset=["dip", "dip_direction"]).copy()
    f["dip"] = f["dip"].clip(0, 90)
    f["dip_direction"] = f["dip_direction"] % 360
    return f.reset_index(drop=True)


def rose(ax, dipdir, bin_deg=10, color="#2E6F9E", title="Strike rose (bidirectional)"):
    strike = (np.asarray(dipdir) - 90) % 180
    both = np.concatenate([strike, strike + 180])
    edges = np.arange(0, 361, bin_deg)
    counts, _ = np.histogram(both, edges)
    theta = np.radians(edges[:-1] + bin_deg / 2)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.bar(theta, counts, width=np.radians(bin_deg) * 0.95, color=color, edgecolor="white", lw=0.6, alpha=0.9)
    ax.set_title(title, fontsize=10, fontweight="bold", color=NAVY, pad=14)
    ax.set_yticklabels([])
    ax.tick_params(labelsize=7)
    return ax


def _pole_xy(dip, dipdir):
    """Equal-area (Schmidt) lower-hemisphere position of fracture poles; unit circle."""
    trend = np.radians((np.asarray(dipdir) + 180) % 360)
    plunge = np.radians(90 - np.asarray(dip))
    r = np.sqrt(2) * np.sin((np.pi / 2 - plunge) / 2)
    return r * np.sin(trend), r * np.cos(trend)


def _great_circle(dip, dipdir, n=90):
    """Plane trace on an equal-area lower-hemisphere net."""
    dd, dp = np.radians(dipdir), np.radians(dip)
    # direction vectors of lines in the plane: rotate from strike to down-dip
    strike = dd - np.pi / 2
    t = np.linspace(0, np.pi, n)
    # vector in plane: cos t * strike_dir + sin t * dip_dir_vector (down)
    sx, sy, sz = np.sin(strike), np.cos(strike), 0.0
    dx, dy, dz = np.sin(dd) * np.cos(dp), np.cos(dd) * np.cos(dp), -np.sin(dp)
    vx, vy, vz = np.cos(t) * sx + np.sin(t) * dx, np.cos(t) * sy + np.sin(t) * dy, np.cos(t) * sz + np.sin(t) * dz
    plunge = np.arcsin(np.clip(-vz, -1, 1))
    trend = np.arctan2(vx, vy)
    r = np.sqrt(2) * np.sin((np.pi / 2 - plunge) / 2)
    return r * np.sin(trend), r * np.cos(trend)


def stereonet(ax, dip, dipdir, density=True, planes=True, title="Stereonet (poles, lower hemisphere)"):
    ax.set_aspect("equal")
    R = np.sqrt(2) * np.sin(np.pi / 4)  # primitive circle radius (=1)
    t = np.linspace(0, 2 * np.pi, 361)
    if density and len(dip) >= 5:
        px, py = _pole_xy(dip, dipdir)
        g = np.linspace(-R, R, 121)
        X, Y = np.meshgrid(g, g)
        inside = X ** 2 + Y ** 2 <= R ** 2
        # Gaussian kernel on the net (antipodal wrap for points near the primitive)
        sig = 0.12
        dens = np.zeros_like(X)
        for x0, y0 in zip(px, py):
            dens += np.exp(-((X - x0) ** 2 + (Y - y0) ** 2) / (2 * sig ** 2))
            dens += np.exp(-((X + x0) ** 2 + (Y + y0) ** 2) / (2 * sig ** 2)) * (x0 ** 2 + y0 ** 2 > 0.8)
        dens = dens / dens[inside].mean()  # multiples of uniform density
        dens[~inside] = np.nan
        cf = ax.contourf(X, Y, dens, levels=np.linspace(0, np.nanmax(dens), 9)[1:], cmap="Oranges", alpha=0.85)
        cb = ax.figure.colorbar(cf, ax=ax, shrink=0.6, pad=0.02)
        cb.set_label("Pole density (× uniform)", fontsize=7)
        cb.ax.tick_params(labelsize=6)
    if planes and len(dip) <= 60:
        for d, a in zip(dip, dipdir):
            x, y = _great_circle(d, a)
            ax.plot(x, y, color="#9AA3AF", lw=0.4)
    px, py = _pole_xy(dip, dipdir)
    ax.scatter(px, py, s=14, color=NAVY, edgecolor="white", lw=0.4, zorder=5)
    ax.plot(R * np.cos(t), R * np.sin(t), color="k", lw=1)
    ax.plot([0], [0], "+", color="k", ms=6)
    for lab, (x, y) in {"N": (0, R * 1.07), "E": (R * 1.07, 0), "S": (0, -R * 1.1), "W": (-R * 1.1, 0)}.items():
        ax.text(x, y, lab, ha="center", va="center", fontsize=9, fontweight="bold")
    ax.set_xlim(-R * 1.2, R * 1.2)
    ax.set_ylim(-R * 1.2, R * 1.2)
    ax.set_axis_off()
    ax.set_title(title, fontsize=10, fontweight="bold", color=NAVY)
    return ax


def frequency(ax, f: pd.DataFrame, bin_m=10.0):
    """Fracture count per depth interval with water strikes (yield) marked."""
    depth = f["depth"].dropna()
    if depth.empty:
        return ax
    edges = np.arange(0, depth.max() + bin_m, bin_m)
    counts, _ = np.histogram(depth, edges)
    ax.barh(edges[:-1] + bin_m / 2, counts, height=bin_m * 0.9, color="#7FB3D5", edgecolor=NAVY, lw=0.5)
    ws = f.dropna(subset=["yield"])
    ws = ws[ws["yield"] > 0]
    if len(ws):
        ax2 = ax.twiny()
        ax2.scatter(ws["yield"], ws["depth"], s=22, marker="v", color="#1F77B4", edgecolor="k", lw=0.4, zorder=5)
        ax2.set_xlabel("Water strike yield (lps)", fontsize=7, color="#1F77B4")
        ax2.tick_params(labelsize=6, colors="#1F77B4")
    ax.invert_yaxis()
    ax.set_xlabel(f"Fractures per {bin_m:g} m", fontsize=8)
    ax.set_ylabel("Depth (m bgl)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_title("Fracture frequency with depth", fontsize=10, fontweight="bold", color=NAVY)
    return ax


def fracture_report(project, path, borehole=None, title: str = "") -> Path:
    """One A4-landscape page: rose, stereonet, frequency and summary."""
    import matplotlib.pyplot as plt

    fig = fracture_figure(project, borehole, title)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def fracture_figure(project, borehole=None, title: str = ""):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    f = table(project)
    if borehole:
        f = f[f["borehole_id"] == borehole]
    if f.empty:
        raise ValueError("No fracture measurements (Fractures sheet with Dip and Dip direction)")
    fig = plt.figure(figsize=(297 / 25.4, 210 / 25.4))
    ax1 = fig.add_axes([0.04, 0.12, 0.28, 0.66], projection="polar")
    rose(ax1, f["dip_direction"])
    ax2 = fig.add_axes([0.35, 0.1, 0.33, 0.7])
    stereonet(ax2, f["dip"].to_numpy(), f["dip_direction"].to_numpy())
    ax3 = fig.add_axes([0.76, 0.12, 0.2, 0.62])
    frequency(ax3, f)
    scope = f"borehole {borehole}" if borehole else f"{f['borehole_id'].nunique()} boreholes"
    fig.text(0.04, 0.93, f"FRACTURE ANALYSIS{(' – ' + title) if title else ''}", fontsize=14, fontweight="bold",
             color=NAVY)
    mean_dd = np.degrees(np.arctan2(np.sin(np.radians(f["dip_direction"])).mean(),
                                    np.cos(np.radians(f["dip_direction"])).mean())) % 360
    fig.text(0.04, 0.885, f"{len(f)} fractures from {scope} · mean dip {f['dip'].mean():.0f}° · "
                          f"vector-mean dip direction {mean_dd:.0f}° · "
                          f"water strikes: {int((f['yield'].fillna(0) > 0).sum())}",
             fontsize=9, color="#444444")
    fig.text(0.04, 0.03, "Equal-area (Schmidt) net, lower hemisphere. Strike rose uses the right-hand rule "
                         "(strike = dip direction − 90°), plotted bidirectionally.", fontsize=7, color="#777777")
    return fig
