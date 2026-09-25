"""The LithoLog mark: an isometric block of strata (with a water-bearing layer)
pierced by an amber borehole — a 3D lithology model in one glyph."""

from __future__ import annotations

_BANDS = [  # (fraction of the block height, left-face colour, right-face colour)
    (0.10, "#A67C52", "#8C6642"),   # top soil
    (0.20, "#E8C9A6", "#CDB08E"),   # weathered zone
    (0.26, "#CFC3E6", "#B3A7CB"),   # crystalline rock
    (0.10, "#3F9BE0", "#2F7FBF"),   # fractured, water-bearing
    (0.34, "#B98B80", "#9C7268"),   # basement
]


def svg(size: int = 256, background: bool = True) -> str:
    """Square app icon as SVG text."""
    top = [(128, 44), (212, 92), (128, 140), (44, 92)]
    h = 92.0
    parts = []
    y = 0.0
    for frac, cl, cr in _BANDS:
        a, b = y, y + frac * h
        parts.append(f'<polygon points="44,{92 + a:.1f} 128,{140 + a:.1f} 128,{140 + b:.1f} 44,{92 + b:.1f}" '
                     f'fill="{cl}"/>')
        parts.append(f'<polygon points="128,{140 + a:.1f} 212,{92 + a:.1f} 212,{92 + b:.1f} 128,{140 + b:.1f}" '
                     f'fill="{cr}"/>')
        y = b
    pts = " ".join(f"{x},{yy}" for x, yy in top)
    bg = ('<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
          '<stop offset="0" stop-color="#2E3440"/><stop offset="1" stop-color="#171A20"/></linearGradient></defs>'
          '<rect x="6" y="6" width="244" height="244" rx="52" fill="url(#g)"/>') if background else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 256 256">
{bg}
<g stroke="none">
{''.join(parts)}
<polygon points="{pts}" fill="#D9BE93"/>
<polygon points="128,140 128,{140 + h:.0f}" />
</g>
<g fill="none" stroke="#1B1F26" stroke-opacity="0.35" stroke-width="2" stroke-linejoin="round">
<polygon points="{pts}"/>
<polyline points="44,92 44,{92 + h:.0f} 128,{140 + h:.0f} 212,{92 + h:.0f} 212,92"/>
<line x1="128" y1="140" x2="128" y2="{140 + h:.0f}"/>
</g>
<line x1="128" y1="18" x2="128" y2="92" stroke="#F0A43A" stroke-width="9" stroke-linecap="round"/>
<ellipse cx="128" cy="92" rx="13" ry="7.5" fill="#F0A43A"/>
<ellipse cx="128" cy="92" rx="5.5" ry="3.2" fill="#1B1F26"/>
</svg>"""


def wordmark_svg(dark: bool = True) -> str:
    """Logo with the name, for headers and the README."""
    text, dim = ("#E6E9EE", "#9AA3AF") if dark else ("#1E2530", "#5F6B7A")
    mark = svg(256, background=True).split("\n", 1)[1].rsplit("</svg>", 1)[0]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="820" height="200" viewBox="0 0 820 200">
<g transform="translate(10,10) scale(0.703)">{mark}</g>
<text x="210" y="112" font-family="Segoe UI, Inter, DejaVu Sans, sans-serif" font-size="78" font-weight="700"
 fill="{text}">Litho<tspan fill="#F0A43A">Log</tspan></text>
<text x="214" y="156" font-family="Segoe UI, Inter, DejaVu Sans, sans-serif" font-size="21" letter-spacing="2.5"
 fill="{dim}">GEOLOGY · HYDROGEOLOGY · 3D MODELS</text>
</svg>"""


def pixmap(size: int = 256, background: bool = True):
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer

    r = QSvgRenderer(QByteArray(svg(size, background).encode()))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p)
    p.end()
    return pm


def app_icon():
    from PySide6.QtGui import QIcon

    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(pixmap(s))
    return ic


def write_assets(folder) -> list:
    """litholog.svg / .png / .ico and the wordmarks (needs a QGuiApplication)."""
    from pathlib import Path

    from PIL import Image

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "litholog.svg").write_text(svg())
    (folder / "litholog_wordmark.svg").write_text(wordmark_svg(True))
    (folder / "litholog_wordmark_light.svg").write_text(wordmark_svg(False))
    png = folder / "litholog.png"
    pixmap(256).save(str(png))
    Image.open(png).save(folder / "litholog.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                                          (128, 128), (256, 256)])
    return [folder / n for n in ("litholog.svg", "litholog.png", "litholog.ico", "litholog_wordmark.svg")]
