"""Horizon-based layer model (GMS-style "horizons → solids").

Why: an indicator (voxel) model decides each voxel by the lithology most
boreholes have *at that depth*. A thin layer that occurs at different depths in
different holes (e.g. a water-bearing fracture zone) rarely wins that vote and
breaks into isolated lenses, although it is present in almost every hole.

How:
1. Horizons: every layer occurrence is matched across all boreholes by
   progressive multiple-sequence alignment of the borehole logs (the same
   sequence/depth correlation used for cross-sections). Repeated units become
   separate horizons ("Fractured layer · zone 1", "· zone 2", ...).
2. The thickness of each horizon is interpolated as a continuous surface: zero
   where the horizon is absent in a hole (pinch-out), unknown below the drilled
   depth.
3. Horizons are stacked from the ground surface (DEM or collars) downwards, so
   surfaces never cross; the base of drilling truncates the stack.
4. Volumes are integrated exactly from the thickness grids; solids are meshed
   directly from the horizon surfaces (smooth, no voxel steps).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .correlate import Unit, align, units
from .grid import hull_mask, interpolate, make_axes
from .model3d import BlockModel


# ---------------------------------------------------------------------------
# 1. Horizon assignment


def _depth_units(bh):
    """Units with depths (top/bot positive downwards) in the Unit fields as negatives."""
    return units(bh, datum="depth")  # top = -from, bot = -to


def assign_horizons(project, scale: float = 25.0):
    """Master horizon sequence and, per borehole, the horizon index of each unit.

    Returns (horizons, assignment) where horizons is a list of dicts
    {code, top, bot, n} (mean depths, number of holes) ordered top→bottom and
    assignment is {borehole_id: [(horizon_index, Unit), ...]}.
    """
    holes = [(bh.id, _depth_units(bh)) for bh in project if pd.notna(bh.x)]
    holes = [(b, us) for b, us in holes if us]
    if not holes:
        raise ValueError("No boreholes with lithology and coordinates")
    holes.sort(key=lambda h: -len(h[1]))
    master: list[dict] = [{"code": u.code, "top": u.top, "bot": u.bot, "n": 1} for u in holes[0][1]]

    def as_units(ms):
        return [Unit(m["top"], m["bot"], m["code"]) for m in ms]

    for _, us in holes[1:]:
        pairs = align(us, as_units(master), scale)
        new = []
        for i, j in pairs:
            if i is not None and j is not None and us[i].code == master[j]["code"]:
                m = master[j]
                n = m["n"]
                m["top"] = (m["top"] * n + us[i].top) / (n + 1)
                m["bot"] = (m["bot"] * n + us[i].bot) / (n + 1)
                m["n"] = n + 1
                new.append(m)
            else:
                if j is not None:
                    new.append(master[j])
                if i is not None:
                    new.append({"code": us[i].code, "top": us[i].top, "bot": us[i].bot, "n": 1})
        master = new

    # Final pass: assign every hole's units to the finished master sequence.
    assignment = {}
    counts = [0] * len(master)
    mu = as_units(master)
    for bid, us in holes:
        pairs = align(us, mu, scale)
        got = []
        for i, j in pairs:
            if i is None:
                continue
            if j is not None and master[j]["code"] == us[i].code:
                got.append((j, us[i]))
            else:  # fall back to the nearest same-code horizon not yet used by this hole
                used = {g[0] for g in got}
                cands = [k for k, m in enumerate(master) if m["code"] == us[i].code and k not in used
                         and (not got or k > got[-1][0])]
                if cands:
                    k = min(cands, key=lambda k: abs(master[k]["top"] - us[i].top))
                    got.append((k, us[i]))
        for k, _ in got:
            counts[k] += 1
        assignment[bid] = got
    master, assignment = _merge_equivalent(master, assignment)
    return master, assignment


def _merge_equivalent(master, assignment):
    """Merge same-code horizons that never occur together in one hole, when that keeps every
    hole's order (the aligner may have opened two slots for what is one layer)."""
    while True:
        sets = {bid: {k for k, _ in got} for bid, got in assignment.items()}
        merged = False
        for j in range(len(master)):
            for k in range(j + 1, len(master)):
                if master[j]["code"] != master[k]["code"]:
                    continue
                between = set(range(j + 1, k))
                if any(j in s and k in s for s in sets.values()):
                    continue
                if not any(k in s and s & between for s in sets.values()):
                    src, dst = k, j      # move k up into j
                elif not any(j in s and s & between for s in sets.values()):
                    src, dst = j, k      # move j down into k
                else:
                    continue
                for bid, got in assignment.items():
                    assignment[bid] = [(dst if h == src else h, u) for h, u in got]
                merged = True
                break
            if merged:
                break
        if not merged:
            break
        # drop the emptied horizon and renumber
        used = sorted({h for got in assignment.values() for h, _ in got})
        remap = {h: i for i, h in enumerate(used)}
        master = [master[h] for h in used]
        for bid, got in assignment.items():
            assignment[bid] = sorted(((remap[h], u) for h, u in got), key=lambda t: t[0])
    for k, m in enumerate(master):
        us = [u for got in assignment.values() for h, u in got if h == k]
        m["n"] = len(us)
        if us:
            m["top"] = float(np.mean([u.top for u in us]))
            m["bot"] = float(np.mean([u.bot for u in us]))
    return master, assignment


def horizon_labels(horizons, legend):
    """Readable names: repeated codes get 'zone 1, 2, ...' top to bottom."""
    seen, total = {}, {}
    for h in horizons:
        total[h["code"]] = total.get(h["code"], 0) + 1
    out = []
    for h in horizons:
        seen[h["code"]] = seen.get(h["code"], 0) + 1
        name = legend.get(h["code"]).name
        out.append(name if total[h["code"]] == 1 else f"{name} · zone {seen[h['code']]}")
    return out


def horizon_table(project, horizons, assignment) -> pd.DataFrame:
    """Thickness of every horizon in every hole (0 = absent, NaN = below drilled depth)."""
    rows = []
    for bh in project:
        if bh.id not in assignment:
            continue
        got = dict((k, u) for k, u in assignment[bh.id])
        last = max(got) if got else -1
        us = _depth_units(bh)
        row = {"borehole_id": bh.id, "x": bh.x, "y": bh.y,
               "ground": bh.elevation if bh.has_elevation else np.nan,
               "depth": -us[-1].bot if us else np.nan}
        for k in range(len(horizons)):
            if k in got:
                row[f"h{k}"] = got[k].thick
            else:
                row[f"h{k}"] = 0.0 if k < last else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2-4. Surfaces, block model, volumes


def build_horizon_model(project, cell: float | None = None, dz: float | None = None, method: str = "idw",
                        boundary=None, dem=None, target: int = 120, scale: float = 25.0) -> BlockModel:
    horizons, assignment = assign_horizons(project, scale)
    tab = horizon_table(project, horizons, assignment)
    hx, hy = tab["x"].to_numpy(float), tab["y"].to_numpy(float)
    if boundary is not None:
        bx0, bx1, by0, by1 = boundary.bbox
        gx, gy, cell = make_axes(np.r_[hx, bx0, bx1], np.r_[hy, by0, by1], cell, margin=0.01, target=target)
        inside = boundary.mask(gx, gy)
    else:
        gx, gy, cell = make_axes(hx, hy, cell, target=target)
        inside = hull_mask(hx, hy, gx, gy, cell) if len(tab) >= 3 else np.ones((len(gy), len(gx)), bool)

    # Ground: DEM where available, else interpolated collar elevations.
    ground = interpolate(hx, hy, tab["ground"].fillna(0.0), gx, gy, "linear")
    if dem is not None:
        from .dem import sample_on_grid

        g = sample_on_grid(dem, gx, gy)
        ground = np.where(np.isfinite(g), g, ground)
    base_depth = np.clip(interpolate(hx, hy, tab["depth"], gx, gy, "linear"), 0, None)

    thick = []
    for k in range(len(horizons)):
        v = tab[f"h{k}"]
        ok = v.notna().to_numpy()
        if ok.sum() >= 2:
            vv = v[ok].to_numpy(float)
            t = np.clip(interpolate(hx[ok], hy[ok], vv, gx, gy, method), 0, None)
            if (vv <= 0).any():
                # Pinch-out: interpolation of thickness alone never reaches zero, so the layer
                # would spread thinly everywhere. A presence indicator (1 = present) decides
                # where the layer exists; the edge is tapered over the 0.35-0.65 band.
                ind = interpolate(hx[ok], hy[ok], (vv > 0).astype(float), gx, gy, method)
                t = t * np.clip((ind - 0.35) / 0.3, 0, 1)
        elif ok.sum() == 1:
            t = np.full(ground.shape, float(v[ok].iloc[0]))
        else:
            t = np.zeros(ground.shape)
        thick.append(t)
    # Stack from the ground; the deepest horizon fills to the base of drilling.
    tops, bots = [], []
    d = np.zeros(ground.shape)
    for k, t in enumerate(thick):
        top_d = np.minimum(d, base_depth)
        bot_d = base_depth if k == len(thick) - 1 else np.minimum(d + t, base_depth)
        bot_d = np.maximum(bot_d, top_d)
        tops.append(ground - top_d)
        bots.append(ground - bot_d)
        d = d + t
    for arr in tops + bots:
        arr[~inside] = np.nan

    codes = list(dict.fromkeys(h["code"] for h in horizons))
    zlo = float(np.nanmin(bots[-1]))
    zhi = float(np.nanmax(np.where(inside, ground, np.nan)))
    if not dz:
        dz = max(0.5, round((zhi - zlo) / 100, 1))
    gz = np.arange(zlo + dz / 2, zhi, dz)
    lith = np.full((len(gz), len(gy), len(gx)), -1, int)
    for iz, z in enumerate(gz):
        layer = np.full(ground.shape, -1)
        for k, h in enumerate(horizons):
            sel = (z <= tops[k]) & (z > bots[k])
            layer = np.where(sel & (layer < 0), codes.index(h["code"]), layer)
        lith[iz] = np.where(inside, layer, -1)
    prob = np.zeros(lith.shape + (len(codes),), np.float32)
    for c in range(len(codes)):
        prob[..., c] = lith == c

    # Exact volumes from the surfaces (m³), per horizon and per code.
    area = cell * cell
    hvol = [float(np.nansum(np.where(inside, t - b, 0))) * area for t, b in zip(tops, bots)]
    voxel = cell * cell * dz
    expected = np.zeros(len(codes))
    for h, v in zip(horizons, hvol):
        expected[codes.index(h["code"])] += v / voxel

    holes = [(bh.id, bh.x, bh.y, units(bh)) for bh in project if pd.notna(bh.x) and units(bh)]
    from .grid import coverage

    cov = coverage(hx, hy, gx, gy, inside) if boundary is not None else None
    model = BlockModel(gx, gy, gz, cell, dz, lith, codes, expected, boundary, cov, prob, ground,
                       np.where(inside, bots[-1], np.nan), inside, holes)
    model.horizons = horizons
    model.h_labels = horizon_labels(horizons, project.legend)
    model.h_top, model.h_bot, model.h_thick = tops, bots, thick
    model.h_volumes = hvol
    model.h_table = tab
    model.kind = "horizon"
    lone = sum(h["n"] <= 1 for h in horizons)
    model.h_note = (f"{lone} of {len(horizons)} horizons occur in a single borehole only: the layers do not "
                    "continue between holes, so the voxel method may represent this data better."
                    if len(horizons) > 4 and lone > len(horizons) / 2 else "")
    return model


def horizon_volumes(model, legend=None) -> pd.DataFrame:
    rows = []
    for k, (h, lab, v) in enumerate(zip(model.horizons, model.h_labels, model.h_volumes)):
        t = model.h_top[k] - model.h_bot[k]
        present = np.nanmean(np.where(model.inside, t > 0.01, np.nan)) * 100
        rows.append({"horizon": k + 1, "code": h["code"], "layer": lab, "holes_present": h["n"],
                     "mean_thickness_m": float(np.nanmean(np.where(model.inside & (t > 0.01), t, np.nan))),
                     "area_present_pct": float(present), "volume_mcm": v / 1e6})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Solids straight from the horizon surfaces


def _layer_mesh(x, y, top, bot, active_nodes, cell_ok):
    """Closed mesh of the layer between top and bot over active grid cells."""
    ny, nx = top.shape
    X, Y = np.meshgrid(x, y)
    nn = ny * nx
    verts = np.vstack([np.column_stack([X.ravel(), Y.ravel(), np.nan_to_num(top).ravel()]),
                       np.column_stack([X.ravel(), Y.ravel(), np.nan_to_num(bot).ravel()])])
    idx = np.arange(nn).reshape(ny, nx)
    cj, ci = np.nonzero(cell_ok)
    a, b = idx[cj, ci], idx[cj, ci + 1]
    c, d = idx[cj + 1, ci + 1], idx[cj + 1, ci]
    faces = [np.column_stack([a, b, c]), np.column_stack([a, c, d]),                 # top
             np.column_stack([a + nn, c + nn, b + nn]), np.column_stack([a + nn, d + nn, c + nn])]  # bottom
    pad = np.pad(cell_ok, 1, constant_values=False)
    # walls on edges whose neighbouring cell is inactive
    for (dj, di), (p, q) in {(-1, 0): ((0, 0), (0, 1)), (1, 0): ((1, 1), (1, 0)),
                             (0, -1): ((1, 0), (0, 0)), (0, 1): ((0, 1), (1, 1))}.items():
        nb = pad[1 + dj:1 + dj + cell_ok.shape[0], 1 + di:1 + di + cell_ok.shape[1]]
        wj, wi = np.nonzero(cell_ok & ~nb)
        p0 = idx[wj + p[0], wi + p[1]]
        p1 = idx[wj + q[0], wi + q[1]]
        faces += [np.column_stack([p0, p1, p1 + nn]), np.column_stack([p0, p1 + nn, p0 + nn])]
    faces = np.vstack(faces) if faces else np.zeros((0, 3), int)
    del active_nodes
    return verts, faces


def horizon_solids(model, cutaway: str | None = None, only=None, per_horizon: bool = False):
    """Solids meshed from the horizon surfaces: one per lithology code (its horizons merged),
    or with ``per_horizon`` one per horizon (``Solid.horizon`` = its index)."""
    from .solid import Solid

    ny, nx = model.inside.shape
    cells_in = model.inside[:-1, :-1] & model.inside[1:, :-1] & model.inside[:-1, 1:] & model.inside[1:, 1:]
    if cutaway:
        xm, ym = np.median(model.x), np.median(model.y)
        cx = (model.x[:-1] + model.x[1:]) / 2
        cy = (model.y[:-1] + model.y[1:]) / 2
        CX, CY = np.meshgrid(cx, cy)
        quad = ((CX < xm) if "w" in cutaway else (CX > xm)) & ((CY < ym) if "s" in cutaway else (CY > ym))
        cells_in &= ~quad
    per_code = {}
    for k, h in enumerate(model.horizons):
        if only and h["code"] not in only:
            continue
        t, b = model.h_top[k], model.h_bot[k]
        th = np.nan_to_num(t - b)
        cell_ok = cells_in & ((th[:-1, :-1] + th[1:, :-1] + th[:-1, 1:] + th[1:, 1:]) > 0.02)
        if not cell_ok.any():
            continue
        v, f = _layer_mesh(model.x, model.y, t, b, None, cell_ok)
        per_code.setdefault(k if per_horizon else h["code"], []).append((v, f))
    solids = []
    for key, parts in per_code.items():
        code = model.horizons[key]["code"] if per_horizon else key
        vs, fs, off = [], [], 0
        for v, f in parts:
            vs.append(v)
            fs.append(f + off)
            off += len(v)
        V, F = np.vstack(vs), np.vstack(fs)
        used = np.unique(F)  # drop unreferenced vertices
        remap = np.full(len(V), -1)
        remap[used] = np.arange(len(used))
        solids.append(Solid(code, V[used], remap[F].astype(np.int32), key if per_horizon else None))
    return solids
