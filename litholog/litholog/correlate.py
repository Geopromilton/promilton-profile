"""Correlate lithology between two neighbouring boreholes.

The two interval sequences (top to bottom) are aligned with a
Needleman-Wunsch style dynamic programme, the way a geologist would
correlate by hand:

* the same unit at a similar level in both holes -> joined as one layer;
* a unit found in only one hole -> pinches out half-way to the other hole;
* different units at the same position -> lateral change (facies boundary)
  half-way between the holes.

The result is a set of polygons in (distance, elevation) that tile the
panel between the two holes without gaps or overlaps.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


@dataclass
class Unit:
    top: float  # elevation of top (m)
    bot: float  # elevation of base (m)
    code: str

    @property
    def mid(self):
        return (self.top + self.bot) / 2

    @property
    def thick(self):
        return self.top - self.bot


def units(bh, datum: str = "elevation") -> list[Unit]:
    """Lithology of a borehole as elevation units, merging repeated codes.

    With ``datum="depth"`` (or no ground elevation) depths are used as negative
    elevations so holes are hung from a common ground surface.
    """
    base = bh.elevation if (datum == "elevation" and bh.has_elevation) else 0.0
    out: list[Unit] = []
    for _, r in bh.lithology.iterrows():
        f, t = r["from"], r["to"]
        if pd.isna(f) or pd.isna(t) or t <= f:
            continue
        top, bot = base - f, base - t
        if out and out[-1].code == r["code"] and abs(out[-1].bot - top) < 1e-6:
            out[-1].bot = bot
        else:
            out.append(Unit(top, bot, r["code"]))
    return out


def align(a: list[Unit], b: list[Unit], scale: float = 25.0):
    """Return aligned pairs [(i|None, j|None), ...] of unit indices."""
    n, m = len(a), len(b)

    def match(u, v):
        dz = abs(u.mid - v.mid)
        if u.code == v.code:
            return 1.0 + 3.0 * math.exp(-dz / scale)
        return -1.0 - dz / (2 * scale)

    def gap(u):
        return -(0.6 + u.thick / (2 * scale))

    S = [[0.0] * (m + 1) for _ in range(n + 1)]
    T = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        S[i][0], T[i][0] = S[i - 1][0] + gap(a[i - 1]), "u"
    for j in range(1, m + 1):
        S[0][j], T[0][j] = S[0][j - 1] + gap(b[j - 1]), "l"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            opts = (
                (S[i - 1][j - 1] + match(a[i - 1], b[j - 1]), "d"),
                (S[i - 1][j] + gap(a[i - 1]), "u"),
                (S[i][j - 1] + gap(b[j - 1]), "l"),
            )
            S[i][j], T[i][j] = max(opts, key=lambda o: o[0])
    pairs, i, j = [], n, m
    while i or j:
        t = T[i][j]
        if t == "d":
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif t == "u":
            pairs.append((i - 1, None))
            i -= 1
        else:
            pairs.append((None, j - 1))
            j -= 1
    return pairs[::-1]


def panel(a: list[Unit], b: list[Unit], xa: float, xb: float, scale: float = 25.0):
    """Polygons [(code, [(x, z), ...]), ...] filling the panel between two holes."""
    if not a or not b:
        return []
    xm = (xa + xb) / 2
    pairs = align(a, b, scale)
    polys = []
    cur_a, cur_b = a[0].top, b[0].top  # current contact on each side

    # Group consecutive one-sided steps into blocks so they fan to one pinch point.
    steps, k = [], 0
    while k < len(pairs):
        i, j = pairs[k]
        if i is not None and j is not None:
            steps.append(("match", [(i, j)]))
            k += 1
            continue
        side = "a" if j is None else "b"
        block = []
        while k < len(pairs) and ((pairs[k][1] is None) if side == "a" else (pairs[k][0] is None)):
            block.append(pairs[k])
            k += 1
        steps.append((side, block))

    def neighbour_code(idx, direction, fallback):
        """Code of the unit just above (direction=-1) / below (+1) a block, B side preferred."""
        k2 = idx + direction
        if 0 <= k2 < len(steps):
            kind, blk = steps[k2]
            i, j = blk[-1] if direction < 0 else blk[0]
            if j is not None:
                return b[j].code
            return a[i].code
        return fallback

    for idx, (kind, blk) in enumerate(steps):
        if kind == "match":
            i, j = blk[0]
            u, v = a[i], b[j]
            if u.code == v.code:
                polys.append((u.code, [(xa, u.top), (xb, v.top), (xb, v.bot), (xa, u.bot)]))
            else:
                mt, mb = (u.top + v.top) / 2, (u.bot + v.bot) / 2
                polys.append((u.code, [(xa, u.top), (xm, mt), (xm, mb), (xa, u.bot)]))
                polys.append((v.code, [(xm, mt), (xb, v.top), (xb, v.bot), (xm, mb)]))
            cur_a, cur_b = u.bot, v.bot
            continue

        own, x_own, x_far = (a, xa, xb) if kind == "a" else (b, xb, xa)
        idxs = [p[0] if kind == "a" else p[1] for p in blk]
        first, last = own[idxs[0]], own[idxs[-1]]
        far_z = cur_b if kind == "a" else cur_a
        pz = ((first.top + last.bot) / 2 + far_z) / 2
        P = (xm, pz)
        for n_, ii in enumerate(idxs):
            u = own[ii]
            polys.append((u.code, [(x_own, u.top), P, (x_own, u.bot)]))
        above = neighbour_code(idx, -1, first.code)
        below = neighbour_code(idx, +1, last.code)
        polys.append((above, [(x_own, first.top), (x_far, far_z), P]))
        polys.append((below, [(x_own, last.bot), P, (x_far, far_z)]))
        if kind == "a":
            cur_a = last.bot
        else:
            cur_b = last.bot
    return polys
