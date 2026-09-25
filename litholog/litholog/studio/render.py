"""Rendering helpers for the 3D view: colour enhancement, seamless textures, crisp text."""

from __future__ import annotations

import colorsys
from functools import lru_cache

import numpy as np


# ---------------------------------------------------------------------------- colour
def rgb(color: str):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def enhance(color: str, saturation: float = 1.35, value: float = 0.97) -> str:
    """A livelier version of a (often pastel) legend colour for 3D display."""
    h, s, v = colorsys.rgb_to_hsv(*rgb(color))
    s = min(1.0, s * saturation + 0.04)
    v = min(1.0, v * value)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def darker(color: str, f: float = 0.55) -> str:
    r, g, b = (c * f for c in rgb(color))
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


# ---------------------------------------------------------------------------- textures
def _periodic_noise(n: int, seed: int, slope: float = 1.6) -> np.ndarray:
    """Tileable 1/f noise in [-1, 1] (built in the frequency domain, so it wraps seamlessly)."""
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(n)
    k = np.sqrt(f[:, None] ** 2 + f[None, :] ** 2)
    k[0, 0] = 1.0
    spec = (rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))) / k ** slope
    spec[0, 0] = 0
    img = np.real(np.fft.ifft2(spec))
    img -= img.mean()
    return img / (np.abs(img).max() + 1e-12)


@lru_cache(maxsize=64)
def grain_texture(color: str, seed: int = 0, n: int = 256, strength: float = 0.16) -> np.ndarray:
    """Rock-grain texture: the layer colour modulated by seamless coarse + fine noise."""
    base = np.array(rgb(color))
    noise = 0.65 * _periodic_noise(n, seed, 1.9) + 0.35 * _periodic_noise(n, seed + 101, 1.1)
    speck = _periodic_noise(n, seed + 7, 0.3)
    shade = 1 + strength * noise - 0.08 * (speck > 0.72)
    img = np.clip(base[None, None, :] * shade[..., None], 0, 1)
    return (img * 255).astype(np.uint8)


@lru_cache(maxsize=64)
def pattern_texture(code: str, name: str, color: str, pattern: str, n: int = 512) -> np.ndarray:
    """The lithology's log pattern (as printed on strip logs) as a texture tile."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from ..patterns import LithType, draw_interval

    size_in = 60 / 25.4                       # a 60 mm square of pattern per tile
    fig = Figure(figsize=(size_in, size_in), dpi=n / size_in)
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(1, 0)
    ax.set_axis_off()
    draw_interval(ax, 0, 1, 0, 1, LithType(code, name, color, pattern), edge=False)
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., :3].copy()
    # soften the tile seams: cross-fade a thin border with the opposite edge
    b = max(2, n // 64)
    w = np.linspace(0, 1, b)[:, None]
    img = img.astype(float)
    wr = w[:, :, None]                       # (b, 1, 1): blend rows
    img[:b] = img[:b] * wr + img[-b:][::-1] * (1 - wr)
    wc = w.T[:, :, None]                     # (1, b, 1): blend columns
    img[:, :b] = img[:, :b] * wc + img[:, -b:][:, ::-1] * (1 - wc)
    return img.astype(np.uint8)


def triplanar_tcoords(points: np.ndarray, normals: np.ndarray, tile: float, tile_z: float) -> np.ndarray:
    """Texture coordinates projected along each vertex's dominant normal axis."""
    ax = np.abs(normals).argmax(1)
    u = np.where(ax == 0, points[:, 1] / tile, points[:, 0] / tile)
    v = np.where(ax == 2, points[:, 1] / tile, points[:, 2] / tile_z)
    return np.column_stack([u, v]).astype(np.float32)


# ---------------------------------------------------------------------------- text
def style_text(prop, size=None, bold=False, color=None, weight="semibold"):
    """Use the bundled Inter font (sharp, consistent on every PC) for a vtkTextProperty."""
    from ..typeface import available, path

    if prop is None:
        return
    try:
        if available():
            import vtk

            prop.SetFontFamily(vtk.VTK_FONT_FILE)
            prop.SetFontFile(path("bold" if bold else weight))
        if size:
            prop.SetFontSize(int(size))
        if color:
            prop.SetColor(*rgb(color))
        prop.SetBold(False)          # weight comes from the font file
        prop.SetShadow(False)
    except Exception:  # noqa: BLE001 - never fail a render over a font
        pass


# ---------------------------------------------------------------------------- print export
def _text_props(prop):
    """Every vtkTextProperty a view prop draws with (labels, titles, captions)."""
    out = []
    for getter in ("GetTextProperty", "GetCaptionTextProperty", "GetTitleTextProperty", "GetLabelTextProperty"):
        f = getattr(prop, getter, None)
        if f is None:
            continue
        try:
            if getter in ("GetTitleTextProperty", "GetLabelTextProperty") and prop.IsA("vtkCubeAxesActor"):
                out += [f(i) for i in range(3)]
            else:
                out.append(f())
        except TypeError:
            continue
    mapper = prop.GetMapper() if hasattr(prop, "GetMapper") else None
    if mapper is not None and mapper.IsA("vtkLabelPlacementMapper"):
        alg = mapper.GetInputAlgorithm()
        while alg is not None and not hasattr(alg, "GetTextProperty"):
            alg = alg.GetInputAlgorithm() if alg.GetNumberOfInputPorts() else None
        if alg is not None:
            out.append(alg.GetTextProperty())
    return [t for t in out if t is not None]


class ScaledProps:
    """Temporarily multiply font sizes and line widths of the given props by ``f`` (for big renders)."""

    def __init__(self, props, f):
        self.props, self.f, self.undo = list(props), float(f), []

    def __enter__(self):
        f = self.f
        for prop in self.props:
            # vtkWindowToImageFilter already magnifies 2D overlays (axes grid, captions, scalar bars);
            # only 3D-anchored text (billboards) and line widths need scaling here.
            # measured: billboard labels and the axes grid need the full factor, while the N/E/Up
            # captions are magnified by the tiling itself and must be shrunk back
            tf = f if prop.IsA("vtkBillboardTextActor3D") or prop.IsA("vtkCubeAxesActor") else \
                (1 / f if prop.IsA("vtkCaptionActor2D") else None)
            for t in (_text_props(prop) if tf else []):
                s = t.GetFontSize()
                t.SetFontSize(max(1, round(s * tf)))
                self.undo.append(lambda t=t, s=s: t.SetFontSize(s))
            if prop.IsA("vtkCubeAxesActor"):
                for name in ():
                    get, set_ = getattr(prop, "Get" + name, None), getattr(prop, "Set" + name, None)
                    if get and set_:
                        v0 = get()
                        v1 = tuple(x * f for x in v0) if isinstance(v0, (tuple, list)) else v0 * f
                        try:
                            set_(v1)
                        except TypeError:
                            continue
                        self.undo.append(lambda set_=set_, v0=v0: set_(v0))
                for ax in "XYZ":
                    lp = getattr(prop, f"Get{ax}AxesLinesProperty")()
                    w = lp.GetLineWidth()
                    lp.SetLineWidth(w * f)
                    self.undo.append(lambda lp=lp, w=w: lp.SetLineWidth(w))
            elif hasattr(prop, "GetProperty") and prop.IsA("vtkActor"):
                pr = prop.GetProperty()
                w, ps = pr.GetLineWidth(), pr.GetPointSize()
                pr.SetLineWidth(w * f)
                pr.SetPointSize(ps * f)
                self.undo.append(lambda pr=pr, w=w, ps=ps: (pr.SetLineWidth(w), pr.SetPointSize(ps)))
        return self

    def __exit__(self, *exc):
        for u in reversed(self.undo):
            u()
