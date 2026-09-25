"""Model validation: leave-one-out cross-validation, method comparison and model uncertainty.

Each borehole is removed in turn, its log is predicted at its location from the remaining
boreholes, and the prediction is scored against the real log:

* lithology match: share of the drilled depth where the predicted unit is the logged unit;
* per unit: detection rate (logged occurrences that the prediction also shows there), false
  alarms (predicted occurrences the hole does not have), error in the depth of each occurrence's
  top, and error in the total thickness;
* methods compared: horizon model (IDW and kriging), voxel (indicator) model and — as the
  baseline any model must beat — simply copying the nearest borehole.

Model uncertainty: unit volumes from the different methods (their spread is a practical
uncertainty range) and the distance from every point of the study area to the nearest borehole.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .correlate import units

METHODS = {
    "horizons_idw": "Horizons · IDW",
    "horizons_kriging": "Horizons · kriging",
    "voxel": "Voxel · indicator IDW",
    "nearest": "Nearest borehole (baseline)",
}


# ---------------------------------------------------------------------------- predictions
def _log(bh):
    """[(top_depth, bottom_depth, code)] of a borehole."""
    return [(-u.top, -u.bot, u.code) for u in units(bh, datum="depth")]


def _subset(project, drop_id):
    from copy import copy

    p = copy(project)
    p.boreholes = project.boreholes[project.boreholes["borehole_id"] != drop_id]
    p.lithology = project.lithology[project.lithology["borehole_id"] != drop_id]
    return p


def _voxel_log(others, x, y, dz=0.5, power=2.0):
    """Indicator-IDW prediction at a point (depth datum), as in the voxel model."""
    xs = np.array([o[0] for o in others])
    ys = np.array([o[1] for o in others])
    w = 1.0 / np.maximum(np.hypot(xs - x, ys - y), 1e-6) ** power
    depth = np.average([o[2][-1][1] for o in others], weights=w)
    samples = np.arange(dz / 2, depth, dz)
    codes = []
    for s in samples:
        score = {}
        for wi, (_, _, log) in zip(w, others):
            c = next((c for t, b, c in log if t <= s < b), None)
            if c is not None:
                score[c] = score.get(c, 0.0) + wi
        codes.append(max(score, key=score.get) if score else None)
    out = []
    for s, c in zip(samples, codes):
        if c is None:
            continue
        if out and out[-1][2] == c and abs(out[-1][1] - (s - dz / 2)) < 1e-6:
            out[-1] = (out[-1][0], s + dz / 2, c)
        else:
            out.append((s - dz / 2, s + dz / 2, c))
    return out


def predict(project, bid, method):
    bh = project.borehole(bid)
    x, y = float(bh.x), float(bh.y)
    rest = _subset(project, bid)
    if method.startswith("horizons"):
        from .horizons import predict_log

        return predict_log(rest, x, y, "kriging" if method.endswith("kriging") else "idw")
    others = [(float(b.x), float(b.y), _log(b)) for b in rest if pd.notna(b.x) and _log(b)]
    if method == "nearest":
        return min(others, key=lambda o: np.hypot(o[0] - x, o[1] - y))[2]
    return _voxel_log(others, x, y)


# ---------------------------------------------------------------------------- scoring
def _codes_at(log, depths):
    out = np.full(len(depths), "", dtype=object)
    for t, b, c in log:
        out[(depths >= t) & (depths < b)] = c
    return out


def _occurrences(log, code):
    """Contiguous occurrences of a unit (adjacent intervals of the same code merged)."""
    occ = []
    for t, b, c in log:
        if c != code:
            continue
        if occ and abs(occ[-1][1] - t) < 1e-6:
            occ[-1] = (occ[-1][0], b)
        else:
            occ.append((t, b))
    return occ


def score(actual, pred, codes, dz=0.25):
    depth = actual[-1][1]
    d = np.arange(dz / 2, depth, dz)
    a, p = _codes_at(actual, d), _codes_at(pred, d)
    row = {"depth_m": depth, "match_pct": 100 * float((a == p).mean())}
    per = []
    for c in codes:
        ao, po = _occurrences(actual, c), [o for o in _occurrences(pred, c) if o[0] < depth]
        hits, top_err = 0, []
        for t, b in ao:
            ov = [q for q in po if q[0] < b and q[1] > t]
            if ov:
                hits += 1
                top_err.append(min(abs(q[0] - t) for q in ov))
        false = sum(1 for t, b in po if not any(t < bb and b > tt for tt, bb in ao))
        th_a = float((a == c).sum() * dz)
        th_p = float((p == c).sum() * dz)
        per.append({"code": c, "occurrences": len(ao), "detected": hits, "false_alarms": false,
                    "top_error_m": float(np.mean(top_err)) if top_err else np.nan,
                    "thickness_obs_m": th_a, "thickness_pred_m": th_p})
    return row, per


def cross_validate(project, methods=("horizons_idw", "horizons_kriging", "voxel", "nearest"), progress=None):
    """Leave-one-out cross-validation. Returns (per_hole, per_unit) tables."""
    holes = [bh for bh in project if pd.notna(bh.x) and pd.notna(bh.y) and _log(bh)]
    if len(holes) < 4:
        raise ValueError("Cross-validation needs at least four boreholes with coordinates and lithology")
    codes = list(dict.fromkeys(c for bh in holes for _, _, c in _log(bh)))
    xy = np.array([[bh.x, bh.y] for bh in holes], float)
    rows, units_rows = [], []
    n = len(holes) * len(methods)
    for i, bh in enumerate(holes):
        d = np.hypot(*(xy - xy[i]).T)
        d[i] = np.inf
        actual = _log(bh)
        for j, m in enumerate(methods):
            if progress:
                progress(i * len(methods) + j, n)
            try:
                pred = predict(project, bh.id, m)
            except Exception:  # noqa: BLE001 - a failed prediction scores as a miss
                pred = []
            r, per = score(actual, pred, codes)
            rows.append({"borehole_id": bh.id, "x": bh.x, "y": bh.y, "method": m,
                         "nearest_hole_m": float(d.min()), **r})
            units_rows += [{"borehole_id": bh.id, "method": m, **u} for u in per]
    return pd.DataFrame(rows), pd.DataFrame(units_rows)


def summarise(per_hole, per_unit, legend=None):
    s = per_hole.groupby("method").agg(match_mean=("match_pct", "mean"), match_median=("match_pct", "median"),
                                       match_p10=("match_pct", lambda v: np.percentile(v, 10)),
                                       holes=("borehole_id", "nunique")).reset_index()
    g = per_unit.groupby(["method", "code"])
    u = g.agg(occurrences=("occurrences", "sum"), detected=("detected", "sum"),
              false_alarms=("false_alarms", "sum"), top_mae_m=("top_error_m", "mean")).reset_index()
    u["detection_pct"] = 100 * u["detected"] / u["occurrences"].replace(0, np.nan)
    err = per_unit.assign(e=per_unit["thickness_pred_m"] - per_unit["thickness_obs_m"])
    t = err.groupby(["method", "code"]).agg(thickness_mae_m=("e", lambda v: float(np.mean(np.abs(v)))),
                                            thickness_bias_m=("e", "mean")).reset_index()
    u = u.merge(t, on=["method", "code"])
    if legend is not None:
        u.insert(2, "unit", [legend.get(c).name for c in u["code"]])
    order = {m: k for k, m in enumerate(METHODS)}
    s = s.sort_values("method", key=lambda c: c.map(order)).reset_index(drop=True)
    u = u.sort_values(["code", "method"], key=lambda c: c.map(order) if c.name == "method" else c)
    return s, u.reset_index(drop=True)


# ---------------------------------------------------------------------------- uncertainty
def volumes_by_method(project, boundary=None, sy=None):
    from .horizons import build_horizon_model
    from .model3d import build_model

    vols = {}
    for m, fn in (("horizons_idw", lambda: build_horizon_model(project, method="idw", boundary=boundary)),
                  ("horizons_kriging", lambda: build_horizon_model(project, method="kriging", boundary=boundary)),
                  ("voxel", lambda: build_model(project, boundary=boundary))):
        v = fn().volumes(sy or {})
        vols[m] = dict(zip(v["code"], v["volume_mcm"]))
    df = pd.DataFrame(vols)
    df.index.name = "code"
    df["min_mcm"] = df.min(axis=1)
    df["max_mcm"] = df[list(vols)].max(axis=1)
    df["spread_pct"] = 100 * (df["max_mcm"] - df["min_mcm"]) / df[list(vols)].mean(axis=1)
    return df.reset_index()


def distance_grid(project, boundary=None, cell=None):
    from scipy.spatial import cKDTree

    from .grid import hull_mask, make_axes

    b = project.boreholes.dropna(subset=["x", "y"])
    hx, hy = b["x"].to_numpy(float), b["y"].to_numpy(float)
    if boundary is not None:
        x0, x1, y0, y1 = boundary.bbox
        gx, gy, cell = make_axes(np.r_[hx, x0, x1], np.r_[hy, y0, y1], cell, margin=0.01, target=160)
        inside = boundary.mask(gx, gy)
    else:
        gx, gy, cell = make_axes(hx, hy, cell, target=160)
        inside = hull_mask(hx, hy, gx, gy, cell)
    X, Y = np.meshgrid(gx, gy)
    d, _ = cKDTree(np.column_stack([hx, hy])).query(np.column_stack([X.ravel(), Y.ravel()]))
    return gx, gy, np.where(inside, d.reshape(X.shape), np.nan)


# ---------------------------------------------------------------------------- report
def report_figure(per_hole, summary, per_unit, dist, legend, title="", target=None, boundary=None,
                  volumes=None):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from .typeface import use_in_matplotlib

    use_in_matplotlib()
    navy = "#1F3A5F"
    fig = plt.figure(figsize=(420 / 25.4, 297 / 25.4))
    fig.text(0.04, 0.955, f"MODEL VALIDATION{(' – ' + title) if title else ''}", fontsize=16, fontweight="bold",
             color=navy)
    n = per_hole["borehole_id"].nunique()
    fig.text(0.04, 0.925, f"Leave-one-out cross-validation: each of {n} boreholes hidden in turn and predicted "
                          "from the others", fontsize=10, color="#444444")
    ms = list(summary["method"])
    labels = [METHODS.get(m, m) for m in ms]
    colors = ["#2E6F9E", "#5FA8D3", "#E0A458", "#9AA3AF"][:len(ms)]

    ax = fig.add_axes([0.13, 0.56, 0.2, 0.3])
    ax.barh(labels[::-1], summary["match_mean"][::-1], color=colors[::-1])
    for k, (v, lo) in enumerate(zip(summary["match_mean"][::-1], summary["match_p10"][::-1])):
        ax.text(v + 1, k, f"{v:.0f} %  (worst 10 %: {lo:.0f} %)", va="center", fontsize=8)
    ax.set_xlim(0, 125)
    ax.set_xlabel("Depth logged correctly (%)", fontsize=9)
    ax.set_title("a) Lithology match by method", fontsize=11, fontweight="bold", color=navy, loc="left")
    ax.tick_params(labelsize=8)

    tgt = target or per_unit.groupby("code")["occurrences"].sum().idxmax()
    ax = fig.add_axes([0.07, 0.12, 0.24, 0.32])
    pu = per_unit[per_unit["code"] == tgt].set_index("method").reindex(ms)
    x = np.arange(len(ms))
    ax.bar(x - 0.2, pu["detection_pct"], 0.4, color=colors, label="Detected (%)")
    ax2 = ax.twinx()
    ax2.bar(x + 0.2, pu["top_mae_m"], 0.4, color=colors, alpha=0.45, hatch="//", label="Top depth error (m)")
    ax.set_xticks(x, [lb.split(" (")[0].replace(" · ", "\n") for lb in labels], fontsize=7)
    ax.set_ylim(0, 110)
    ax.set_ylabel("Occurrences detected (%)", fontsize=8)
    ax2.set_ylabel("Top depth error when found (m) – hatched bars", fontsize=8)
    ax.set_title(f"b) {legend.get(tgt).name}: detection and depth", fontsize=11, fontweight="bold", color=navy,
                 loc="left")
    ax.tick_params(labelsize=8)
    ax2.tick_params(labelsize=8)

    best = summary.sort_values("match_mean").iloc[-1]["method"]
    ut = per_unit[per_unit["code"] == tgt].set_index("method")
    best_t = ut["detection_pct"].idxmax()
    ph = per_hole[per_hole["method"] == best]
    ax = fig.add_axes([0.38, 0.12, 0.27, 0.74])
    if boundary is not None:
        ax.add_patch(boundary.patch(ax, facecolor="none", edgecolor="#8B0000", lw=1))
    sc = ax.scatter(ph["x"], ph["y"], c=ph["match_pct"], cmap="RdYlGn", vmin=0, vmax=100, s=70,
                    edgecolor="k", lw=0.5, zorder=3)
    for _, r in ph.iterrows():
        ax.annotate(str(r["borehole_id"]), (r["x"], r["y"]), xytext=(4, 4), textcoords="offset points",
                    fontsize=6, color="#333333")
    ax.set_aspect("equal")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.tick_params(labelsize=7)
    cb = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.02)
    cb.set_label("Depth logged correctly (%)", fontsize=8)
    ax.set_title(f"c) Accuracy at each borehole · {METHODS.get(best, best)}", fontsize=11, fontweight="bold",
                 color=navy, loc="left")

    ax = fig.add_axes([0.71, 0.5, 0.23, 0.36])
    gx, gy, d = dist
    im = ax.imshow(d / 1000, origin="lower", extent=(gx[0], gx[-1], gy[0], gy[-1]), cmap="magma_r")
    b = per_hole.drop_duplicates("borehole_id")
    ax.scatter(b["x"], b["y"], s=6, c="#4FA3E0", edgecolor="none")
    if boundary is not None:
        ax.add_patch(boundary.patch(ax, facecolor="none", edgecolor="#8B0000", lw=0.8))
    ax.set_aspect("equal")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.tick_params(labelsize=6)
    cb = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label("Distance to nearest borehole (km)", fontsize=8)
    ax.set_title("d) Distance to nearest borehole", fontsize=11, fontweight="bold", color=navy,
                 loc="left")

    ax = fig.add_axes([0.71, 0.08, 0.26, 0.34])
    ax.set_axis_off()
    s = summary.set_index("method")
    base = s.loc["nearest", "match_mean"] if "nearest" in s.index else np.nan
    dd = d[np.isfinite(d)]
    lines = [f"Overall best: {METHODS.get(best, best)}",
             f"   {s.loc[best, 'match_mean']:.0f} % of drilled depth predicted correctly",
             f"   (nearest-borehole baseline: {base:.0f} %)" if base == base else "",
             f"{legend.get(tgt).name}: best {METHODS.get(best_t, best_t)}",
             f"   {ut.loc[best_t, 'detection_pct']:.0f} % of occurrences found at a hidden borehole,",
             f"   top depth off by {ut.loc[best_t, 'top_mae_m']:.1f} m on average when found",
             f"Data support: {100 * (dd <= 1000).mean():.0f} % of the area within 1 km of a borehole,",
             f"   {100 * (dd > 2000).mean():.0f} % more than 2 km away",
             "",
             "How to read: each borehole was hidden and predicted from",
             "the others. Far from boreholes (dark in d) the model is",
             "extrapolated and less reliable than these scores."]
    if volumes is not None and tgt in set(volumes["code"]):
        v = volumes.set_index("code").loc[tgt]
        lines[8:8] = [f"{legend.get(tgt).name} volume: {v['min_mcm']:,.0f}–{v['max_mcm']:,.0f} MCM",
                      f"   across methods (spread {v['spread_pct']:.0f} %)", ""]
    ax.set_title("e) Summary", fontsize=11, fontweight="bold", color=navy, loc="left")
    ax.text(0, 0.97, "\n".join(lines), va="top", fontsize=9, color="#222222", linespacing=1.55)
    return fig


def validation_report(project, out, methods=None, boundary=None, target=None, title="", volumes=True,
                      progress=None):
    """Run the cross-validation and write tables, a one-page PDF/PNG and a text summary to ``out``."""
    import matplotlib.pyplot as plt

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    per_hole, per_unit = cross_validate(project, methods or tuple(METHODS), progress)
    summary, units_tab = summarise(per_hole, per_unit, project.legend)
    dist = distance_grid(project, boundary)
    per_hole.to_csv(out / "crossval_per_borehole.csv", index=False)
    per_unit.to_csv(out / "crossval_per_unit_per_borehole.csv", index=False)
    summary.to_csv(out / "crossval_summary.csv", index=False)
    units_tab.to_csv(out / "crossval_per_unit.csv", index=False)
    files = [out / f for f in ("crossval_summary.csv", "crossval_per_unit.csv", "crossval_per_borehole.csv")]
    vol = None
    if volumes:
        vol = volumes_by_method(project, boundary)
        vol.insert(1, "unit", [project.legend.get(c).name for c in vol["code"]])
        vol.to_csv(out / "volumes_by_method.csv", index=False)
        files.append(out / "volumes_by_method.csv")
    fig = report_figure(per_hole, summary, units_tab, dist, project.legend, title, target, boundary, vol)
    for ext in ("pdf", "png"):
        fig.savefig(out / f"validation.{ext}", dpi=200)
        files.append(out / f"validation.{ext}")
    plt.close(fig)
    return {"summary": summary, "per_unit": units_tab, "per_hole": per_hole, "volumes": vol, "files": files}
