"""Stratigraphic (layer-cake) model: ordered formation surfaces → solids and volumes.

For layered sequences where each formation occurs once, in a known order
(alluvium, sedimentary basins, weathering profiles). Each borehole gives the
top of every formation; a formation missing in a hole has zero thickness there
(its top = the top of the next formation present below). The top surfaces are
gridded, forced into stratigraphic order (no crossing), and the space between
them fills the block model. The result is a normal BlockModel, so volumes,
smooth solids, views and exports all work unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .correlate import units
from .grid import hull_mask, interpolate, make_axes
from .model3d import BlockModel


def formation_tops(project, order) -> pd.DataFrame:
    """Top elevation of each formation in each hole (NaN below the drilled depth)."""
    rows = []
    for bh in project:
        us = units(bh)
        if not us or pd.isna(bh.x):
            continue
        base = us[-1].bot
        row = {"borehole_id": bh.id, "x": bh.x, "y": bh.y, "ground": us[0].top, "base": base}
        first = {}
        for u in us:
            first.setdefault(u.code, u.top)
        # walk upwards from the bottom so a missing formation takes the top of the one below it
        below = None
        tops = {}
        for code in reversed(order):
            if code in first:
                tops[code] = first[code]
                below = first[code]
            else:
                tops[code] = below if below is not None else np.nan  # not reached by drilling
        for code in order:
            row[f"top_{code}"] = tops[code]
        rows.append(row)
    return pd.DataFrame(rows)


def build_strat_model(project, order, cell: float | None = None, dz: float | None = None,
                      method: str = "idw", boundary=None, target: int = 70) -> BlockModel:
    order = [str(c).strip().upper() for c in order]
    t = formation_tops(project, order)
    if len(t) < 2:
        raise ValueError("A stratigraphic model needs at least two boreholes with coordinates")
    hx, hy = t["x"].to_numpy(float), t["y"].to_numpy(float)
    if boundary is not None:
        bx0, bx1, by0, by1 = boundary.bbox
        gx, gy, cell = make_axes(np.r_[hx, bx0, bx1], np.r_[hy, by0, by1], cell, margin=0.01, target=target)
        inside = boundary.mask(gx, gy)
    else:
        gx, gy, cell = make_axes(hx, hy, cell, target=target)
        inside = hull_mask(hx, hy, gx, gy, cell) if len(t) >= 3 else np.ones((len(gy), len(gx)), bool)
    ground = interpolate(hx, hy, t["ground"], gx, gy, "linear")
    base = interpolate(hx, hy, t["base"], gx, gy, "linear")
    surfaces = []
    upper = ground
    for code in order:
        col = t[f"top_{code}"]
        ok = col.notna()
        if ok.sum() >= 2:
            s = interpolate(hx[ok], hy[ok], col[ok], gx, gy, method)
        else:
            s = base.copy()
        s = np.minimum(s, upper)          # stratigraphic order: never above the formation above
        surfaces.append(s)
        upper = s
    zlo, zhi = float(np.nanmin(base[inside])), float(np.nanmax(ground[inside]))
    if not dz:
        dz = max(0.5, round((zhi - zlo) / 80, 1))
    gz = np.arange(zlo + dz / 2, zhi, dz)
    lith = np.full((len(gz), len(gy), len(gx)), -1, int)
    for k, z in enumerate(gz):
        layer = np.full(ground.shape, -1)
        for i in range(len(order)):  # deepest top below z decides; iterate top→down
            layer = np.where(z <= surfaces[i], i, layer)
        keep = inside & (z <= ground) & (z >= base) & (layer >= 0)
        lith[k] = np.where(keep, layer, -1)
    prob = np.zeros(lith.shape + (len(order),), np.float32)
    for i in range(len(order)):
        prob[..., i] = lith == i
    expected = np.array([(lith == i).sum() for i in range(len(order))], float)
    holes = []
    for bh in project:
        us = units(bh)
        if us and pd.notna(bh.x):
            holes.append((bh.id, bh.x, bh.y, us))
    cov = None
    if boundary is not None:
        from .grid import coverage

        cov = coverage(hx, hy, gx, gy, inside)
    m = BlockModel(gx, gy, gz, cell, dz, lith, order, expected, boundary, cov, prob, ground, base, inside, holes)
    m.surfaces = dict(zip(order, surfaces))
    return m
