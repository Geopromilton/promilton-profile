"""Lithology legend and pattern (symbol) rendering.

Every pattern here is drawn from simple geometric primitives defined in
millimetres, so symbols keep the same printed size whatever the depth scale.
Patterns can be combined with ``+`` (e.g. ``"crosses+fractures"``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import to_rgb
from matplotlib.patches import Rectangle


@dataclass(frozen=True)
class LithType:
    code: str
    name: str
    color: str
    pattern: str = "blank"
    group: str = "Other"


# code, name, fill colour, pattern, group
_DEFAULTS = [
    ("TOP", "Topsoil", "#C9AE85", "roots", "Soil & cover"),
    ("RSOIL", "Red soil", "#DE9C7C", "fine_dots", "Soil & cover"),
    ("BCS", "Black cotton soil", "#8D8A80", "dashes", "Soil & cover"),
    ("FILL", "Fill / made ground", "#DADADA", "diag+backdiag", "Soil & cover"),
    ("CLAY", "Clay", "#B3CFA6", "dashes", "Unconsolidated"),
    ("SCLAY", "Sandy clay", "#CAD6A2", "dashes+dots", "Unconsolidated"),
    ("SILT", "Silt", "#DCD6AE", "fine_dots", "Unconsolidated"),
    ("SAND", "Sand", "#F3E196", "dots", "Unconsolidated"),
    ("GRAV", "Gravel", "#E9C685", "circles", "Unconsolidated"),
    ("KANK", "Kankar / calcrete", "#EDE4CB", "blobs+hlines", "Unconsolidated"),
    ("LAT", "Laterite", "#C9694C", "circles+fine_dots", "Weathering profile"),
    ("LITHO", "Lithomarge", "#E9CCBE", "dashes", "Weathering profile"),
    ("SAPR", "Saprolite / weathered zone", "#E6BA8A", "diag+dots", "Weathering profile"),
    ("WGRA", "Weathered granite", "#F2C0BE", "crosses+diag", "Crystalline"),
    ("FGRA", "Fractured granite", "#EAA3A3", "crosses+fractures", "Crystalline"),
    ("GRA", "Granite (massive)", "#F6D0CF", "crosses", "Crystalline"),
    ("WGN", "Weathered gneiss", "#D2C3E5", "waves+diag", "Crystalline"),
    ("FGN", "Fractured gneiss", "#BEAADB", "waves+fractures", "Crystalline"),
    ("GN", "Gneiss", "#DDD3EE", "waves", "Crystalline"),
    ("SCH", "Schist", "#BCD4CC", "schist", "Crystalline"),
    ("PHY", "Phyllite", "#C9DBD4", "hlines", "Crystalline"),
    ("QTZ", "Quartzite", "#F6F0D6", "dots+hlines", "Crystalline"),
    ("BIF", "Banded iron formation", "#A57474", "bands", "Crystalline"),
    ("DOL", "Dolerite dyke", "#7E8B8C", "xmarks", "Crystalline"),
    ("BAS", "Basalt (massive)", "#94A7AA", "vees", "Volcanic"),
    ("VBAS", "Vesicular basalt", "#AEC1C3", "vees+circles", "Volcanic"),
    ("SST", "Sandstone", "#ECD28F", "dots+hlines", "Sedimentary rock"),
    ("SHL", "Shale", "#AAB0B9", "hlines", "Sedimentary rock"),
    ("LST", "Limestone", "#C8DEEC", "brick", "Sedimentary rock"),
    ("NOREC", "No recovery / not logged", "#FFFFFF", "blank", "Other"),
]

DEFAULT_LEGEND = {c: LithType(c, n, col, p, g) for c, n, col, p, g in _DEFAULTS}

PATTERNS = (
    "blank", "dots", "fine_dots", "dashes", "circles", "blobs", "hlines", "diag",
    "backdiag", "fractures", "crosses", "xmarks", "vees", "waves", "schist",
    "brick", "bands", "roots",
)


def unknown_type(code: str) -> LithType:
    return LithType(code, f"{code} (not in legend)", "#EEEEEE", "blank", "Other")


class Legend:
    """Code -> LithType lookup. Codes are case-insensitive."""

    def __init__(self, types: dict[str, LithType] | None = None):
        self._types = {k.upper(): v for k, v in (types or DEFAULT_LEGEND).items()}

    def __contains__(self, code) -> bool:
        return str(code).strip().upper() in self._types

    def __iter__(self):
        return iter(self._types.values())

    def __len__(self):
        return len(self._types)

    def get(self, code) -> LithType:
        key = str(code).strip().upper()
        return self._types.get(key) or unknown_type(key)

    def updated(self, rows) -> "Legend":
        """Return a copy with user rows (dicts with code/name/color/pattern/group) merged in."""
        types = dict(self._types)
        for r in rows:
            code = str(r.get("code", "")).strip().upper()
            if not code:
                continue
            base = types.get(code) or LithType(code, code, "#EEEEEE")
            types[code] = LithType(
                code,
                _str_or(r.get("name"), base.name),
                _str_or(r.get("color"), base.color),
                _str_or(r.get("pattern"), base.pattern),
                _str_or(r.get("group"), base.group),
            )
        return Legend(types)


def _str_or(value, default):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    value = str(value).strip()
    return value or default


def line_color_for(fill: str) -> str:
    """Dark symbols on light fills, light symbols on dark fills."""
    r, g, b = to_rgb(fill)
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#2B2B2B" if luminance > 0.5 else "#F2F2F2"


def mm_per_data(ax) -> tuple[float, float]:
    """Data units per millimetre on the printed page (x, y) for an axes."""
    fig = ax.figure
    pos = ax.get_position()
    w_mm = pos.width * fig.get_figwidth() * 25.4
    h_mm = pos.height * fig.get_figheight() * 25.4
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    return abs(x1 - x0) / w_mm, abs(y1 - y0) / h_mm


def draw_interval(ax, x0, x1, y0, y1, lith: LithType, edge=True, lw=0.45):
    """Fill a rectangle (data coords) with a lithology's colour and pattern."""
    rect = Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=lith.color,
                     edgecolor="none", zorder=1)
    ax.add_patch(rect)
    color = line_color_for(lith.color)
    for name in str(lith.pattern).split("+"):
        _draw_pattern(ax, x0, x1, y0, y1, name.strip().lower(), color, lw)
    if edge:
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor="none",
                               edgecolor="#222222", lw=0.6, zorder=4))


def _grid(lo, hi, step):
    """Integer grid indices covering [lo, hi] for spacing ``step`` anchored at 0."""
    return np.arange(np.floor(lo / step) - 1, np.ceil(hi / step) + 2)


def _draw_pattern(ax, x0, x1, y0, y1, name, color, lw):
    if name in ("", "blank", "none"):
        return
    ux, uy = mm_per_data(ax)  # data units per mm
    X0, X1 = sorted((x0 / ux, x1 / ux))
    Y0, Y1 = sorted((y0 / uy, y1 / uy))
    segs: list = []   # line segments in mm
    pts: list = []    # (x, y, size_pt, filled) point symbols in mm

    def staggered(sx, sy):
        for k in _grid(Y0, Y1, sy):
            off = 0.5 * sx if int(k) % 2 else 0.0
            for j in _grid(X0, X1, sx):
                yield j * sx + off, k * sy, int(j), int(k)

    if name == "dots":
        pts += [(x, y, 1.6, True) for x, y, _, _ in staggered(2.4, 2.0)]
    elif name == "fine_dots":
        pts += [(x, y, 0.8, True) for x, y, _, _ in staggered(1.6, 1.4)]
    elif name == "blobs":
        pts += [(x, y, 5.0, True) for x, y, _, _ in staggered(5.0, 3.5)]
    elif name == "circles":
        pts += [(x, y, 7.0, False) for x, y, _, _ in staggered(3.6, 2.8)]
    elif name == "dashes":
        segs += [[(x - 0.9, y), (x + 0.9, y)] for x, y, _, _ in staggered(3.2, 1.8)]
    elif name == "hlines":
        segs += [[(X0 - 1, k * 2.0), (X1 + 1, k * 2.0)] for k in _grid(Y0, Y1, 2.0)]
    elif name == "bands":
        for k in _grid(Y0, Y1, 1.5):
            w = 1.8 if int(k) % 2 else 0.5
            _clipped([[(X0 - 1, k * 1.5), (X1 + 1, k * 1.5)]], ax, x0, x1, y0, y1, ux, uy, color, w)
    elif name in ("diag", "backdiag"):
        sign = 1 if name == "diag" else -1
        # lines y = sign*x + c; c spans the rectangle's corners
        cs = [y - sign * x for x in (X0, X1) for y in (Y0, Y1)]
        for c in _grid(min(cs), max(cs), 2.5) * 2.5:
            segs.append([(X0 - 2, sign * (X0 - 2) + c), (X1 + 2, sign * (X1 + 2) + c)])
    elif name == "crosses":
        for x, y, _, _ in staggered(3.2, 2.8):
            segs += [[(x - 0.6, y), (x + 0.6, y)], [(x, y - 0.6), (x, y + 0.6)]]
    elif name == "xmarks":
        for x, y, _, _ in staggered(3.0, 2.6):
            segs += [[(x - 0.5, y - 0.5), (x + 0.5, y + 0.5)], [(x - 0.5, y + 0.5), (x + 0.5, y - 0.5)]]
    elif name == "vees":
        for x, y, _, _ in staggered(3.2, 2.8):
            segs.append([(x - 0.6, y - 0.5), (x, y + 0.5), (x + 0.6, y - 0.5)])
    elif name == "roots":
        for x, y, _, _ in staggered(3.0, 3.0):
            segs += [[(x, y - 0.8), (x, y + 0.8)], [(x, y), (x + 0.5, y - 0.6)], [(x, y), (x - 0.5, y - 0.6)]]
    elif name in ("waves", "schist"):
        sy, amp, wl = (2.2, 0.45, 3.0) if name == "waves" else (1.3, 0.3, 1.6)
        xs = np.arange(np.floor(X0) - 1, X1 + 1, 0.25)
        for k in _grid(Y0, Y1, sy):
            ys = k * sy + amp * np.sin(2 * np.pi * xs / wl)
            segs.append(list(zip(xs, ys)))
    elif name == "brick":
        for k in _grid(Y0, Y1, 2.4):
            y = k * 2.4
            segs.append([(X0 - 1, y), (X1 + 1, y)])
            off = 2.0 if int(k) % 2 else 0.0
            for j in _grid(X0, X1, 4.0):
                x = j * 4.0 + off
                segs.append([(x, y), (x, y + 2.4)])
    elif name == "fractures":
        for x, y, j, k in staggered(4.5, 3.6):
            r = _hash01(j, k)
            if r < 0.55:
                continue
            dx = 0.9 if r > 0.78 else -0.9
            segs.append([(x - dx, y - 0.9), (x + dx, y + 0.9)])
    else:
        return  # unknown pattern name: plain colour fill

    if segs:
        _clipped(segs, ax, x0, x1, y0, y1, ux, uy, color, lw)
    if pts:
        clip = _clip_rect(ax, x0, x1, y0, y1)
        arr = np.array([(p[0] * ux, p[1] * uy) for p in pts])
        filled = pts[0][3]
        sc = ax.scatter(arr[:, 0], arr[:, 1], s=pts[0][2],
                        facecolors=color if filled else "none",
                        edgecolors="none" if filled else color,
                        linewidths=lw, zorder=2)
        sc.set_clip_path(clip)


def _hash01(j, k) -> float:
    v = np.sin(j * 12.9898 + k * 78.233) * 43758.5453
    return float(v - np.floor(v))


def _clip_rect(ax, x0, x1, y0, y1):
    return Rectangle((min(x0, x1), min(y0, y1)), abs(x1 - x0), abs(y1 - y0),
                     transform=ax.transData)


def _clipped(segs_mm, ax, x0, x1, y0, y1, ux, uy, color, lw):
    segs = [[(x * ux, y * uy) for x, y in s] for s in segs_mm]
    coll = LineCollection(segs, colors=color, linewidths=lw, zorder=2)
    # Clip after adding: add_collection() would otherwise replace a rectangular clip.
    ax.add_collection(coll, autolim=False)
    coll.set_clip_path(_clip_rect(ax, x0, x1, y0, y1))
    return coll
